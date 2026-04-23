"""Project lifecycle: create, dormant, close, revive.

Each function is a thin orchestration layer that:
1. Allocates / validates state via ``StateStore``.
2. Manages the EACN3 backend subprocess.
3. Manages the git worktree.
4. Writes ``meta.json`` and updates ``projects.json``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime

import httpx

from minions.errors import BackendError, ProjectError
from minions.lifecycle import eacn_client
from minions.paths import (
    MINIONS_ROOT,
    project_backend_log,
    project_dir,
    project_eacn_db,
    project_logs_dir,
    project_meta_json,
    project_workspace,
)
from minions.state.store import ProjectEntry, StateStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEALTH_TIMEOUT = 20.0  # seconds to wait for backend /health
HEALTH_POLL_INTERVAL = 0.5  # seconds between health probes
EACN_APP = "eacn.network.api.app:create_app"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _write_meta(port: int, entry: ProjectEntry) -> None:
    """Write (or overwrite) ``meta.json`` for *port*."""
    path = project_meta_json(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_meta(port: int) -> ProjectEntry:
    path = project_meta_json(port)
    if not path.exists():
        raise ProjectError(f"meta.json not found for port {port}: {path}")
    return ProjectEntry.model_validate_json(path.read_text(encoding="utf-8"))


def _start_backend(port: int) -> subprocess.Popen:  # type: ignore[type-arg]
    """Start the EACN3 uvicorn backend subprocess for *port*.

    Logs go to ``project_{port}/logs/backend.log``.
    """
    db_path = str(project_eacn_db(port))
    log_path = project_backend_log(port)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure the DB directory exists.
    project_eacn_db(port).parent.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "EACN3_DB_PATH": db_path}
    log_fp = log_path.open("a", encoding="utf-8")

    cmd = [
        "uvicorn",
        EACN_APP,
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    logger.info("Starting EACN3 backend on port %d: %s", port, " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fp,
        stderr=log_fp,
        cwd=str(MINIONS_ROOT),
    )
    logger.debug("Backend PID=%d for port %d", proc.pid, port)
    return proc


def _wait_for_health(port: int, timeout: float = HEALTH_TIMEOUT) -> None:
    """Poll ``/health`` until the backend responds 200 or *timeout* expires.

    Raises ``BackendError`` on timeout.
    """
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                logger.info("Backend on port %d is healthy.", port)
                return
        except Exception as exc:
            last_exc = exc
        time.sleep(HEALTH_POLL_INTERVAL)
    raise BackendError(
        f"Backend on port {port} did not become healthy within {timeout}s. Last error: {last_exc}"
    )


def _register_server(port: int) -> tuple[str, str]:
    """Register a MinionsOS server record with the EACN3 backend."""
    return eacn_client.register_server(port)


def _stop_backend(port: int, pid: int | None) -> None:
    """Terminate the backend process for *port* gracefully."""
    if pid is None:
        return
    try:
        import signal

        os.kill(pid, signal.SIGTERM)
        # Give it a moment to shut down.
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
        logger.info("Stopped backend PID=%d (port %d).", pid, port)
    except ProcessLookupError:
        logger.debug("Backend PID=%d already gone.", pid)
    except Exception as exc:
        logger.warning("Error stopping backend PID=%d: %s", pid, exc)


def _create_worktree(port: int, base_branch: str) -> str:
    """Create a git worktree for *port* inside the parent repo.

    Returns the branch name ``minionsos/project-{port}``.
    """
    branch = f"minionsos/project-{port}"
    workspace = project_workspace(port)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    # The parent repo is the directory that contains MinionsOS_V2.
    parent_repo = MINIONS_ROOT.parent

    # Resolve base_branch: "HEAD" means the current HEAD of the parent repo.
    resolved_base = base_branch if base_branch != "HEAD" else "HEAD"

    cmd = [
        "git",
        "worktree",
        "add",
        "-b",
        branch,
        str(workspace),
        resolved_base,
    ]
    logger.info("Creating worktree: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProjectError(f"git worktree add failed for port {port}: {result.stderr.strip()}")
    return branch


def _git_tag(port: int, tag: str) -> None:
    """Create a git tag in the parent repo."""
    parent_repo = MINIONS_ROOT.parent
    result = subprocess.run(
        ["git", "tag", tag],
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("git tag %s failed: %s", tag, result.stderr.strip())


# ---------------------------------------------------------------------------
# Public lifecycle functions
# ---------------------------------------------------------------------------


def _render_project_claude_md(
    port: int,
    real_name: str,
    venue: str | None,
    branch: str,
    workspace_abs: str,
    brief: str | None,
    topic_doc: str | None,
    template_dir: str | None,
) -> str:
    """Render a default project CLAUDE.md skeleton."""
    lines: list[str] = []
    lines.append(f"# {real_name} — Project CLAUDE.md")
    lines.append("")
    lines.append(
        "> Project-scoped narrative. Authored jointly by the human and Gru; "
        "other Roles read-only."
    )
    lines.append("")
    lines.append("## Facts")
    lines.append("")
    lines.append(f"- **Port:** `{port}`")
    lines.append(f"- **Real name:** {real_name}")
    if venue:
        lines.append(f"- **Venue:** {venue}")
    lines.append(f"- **Git branch:** `{branch}`")
    lines.append(f"- **Workspace (absolute):** `{workspace_abs}`")
    if topic_doc:
        lines.append(f"- **Topic doc:** `{topic_doc}`")
    if template_dir:
        lines.append(f"- **Venue template dir:** `{template_dir}`")
    lines.append("")
    lines.append("## Brief")
    lines.append("")
    lines.append(brief.strip() if brief else "_TODO: write a 1–3 paragraph project brief._")
    lines.append("")
    lines.append("## Working rules")
    lines.append("")
    lines.append("- All inter-Role communication goes through EACN3 on this port.")
    lines.append(
        "- Workspace edits happen on branch above; Noter / Reviewer are read-only "
        "on `workspace/`."
    )
    lines.append(
        "- Root constitution at repo `CLAUDE.md` always wins on conflicts "
        "(see Hard rules)."
    )
    lines.append("")
    return "\n".join(lines)


def project_create(
    real_name: str,
    venue: str | None = None,
    base_branch: str = "HEAD",
    upstream: str | None = None,
    brief: str | None = None,
    topic_doc: str | None = None,
    template_dir: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Create a new project, start its EACN3 backend, and register it.

    Steps:
    1. Allocate a free port.
    2. Create ``project_{port}/`` directory tree.
    3. Create git worktree on branch ``minionsos/project-{port}``.
    4. Start EACN3 backend subprocess; health-probe up to 20 s.
    5. Write ``meta.json``.
    6. Register in ``projects.json``.

    Returns the ``ProjectEntry`` for the new project.
    """
    _store = store or StateStore()
    port = _store.find_next_port()
    logger.info("project_create name=%r port=%d venue=%r", real_name, port, venue)

    # Create directory structure.
    pdir = project_dir(port)
    pdir.mkdir(parents=True, exist_ok=True)
    project_logs_dir(port).mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "notes").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "reports").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "flags" / "open").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "flags" / "resolved").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "investigations").mkdir(parents=True, exist_ok=True)
    (pdir / "memory").mkdir(parents=True, exist_ok=True)
    (pdir / "eacn3_data").mkdir(parents=True, exist_ok=True)

    # Create git worktree.
    try:
        branch = _create_worktree(port, base_branch)
    except ProjectError as exc:
        logger.error("Worktree creation failed: %s", exc)
        raise

    # Start backend.
    proc = _start_backend(port)
    try:
        _wait_for_health(port)
    except BackendError:
        proc.terminate()
        raise

    # Register a server record with EACN3 so roles can register as agents.
    try:
        server_id, eacn3_server_token = _register_server(port)
    except BackendError as exc:
        logger.warning("Server registration failed (non-fatal): %s", exc)
        server_id, eacn3_server_token = "", ""

    now = _now_iso()
    entry = ProjectEntry(
        port=port,
        real_name=real_name,
        status="active",
        created=now,
        venue=venue,
        upstream_branch=upstream or base_branch,
        current_branch=branch,
        active_roles=[],
    )
    # Store backend PID, server_id, and eacn3_server_token in extra fields.
    entry_dict = entry.model_dump()
    entry_dict["backend_pid"] = proc.pid
    entry_dict["eacn3_server_id"] = server_id
    entry_dict["eacn3_server_token"] = eacn3_server_token
    # Persist external resource pointers so revive / downstream tools can see them.
    if topic_doc:
        entry_dict["topic_doc"] = topic_doc
    if template_dir:
        entry_dict["template_dir"] = template_dir

    # Write meta.json with extra fields.
    path = project_meta_json(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    import json as _json

    tmp.write_text(_json.dumps(entry_dict, indent=2), encoding="utf-8")
    os.replace(tmp, path)

    # Auto-generate project CLAUDE.md skeleton if not already present.
    claude_md = pdir / "CLAUDE.md"
    workspace_abs = str(project_workspace(port).resolve())
    if not claude_md.exists():
        claude_md.write_text(
            _render_project_claude_md(
                port=port,
                real_name=real_name,
                venue=venue,
                branch=branch,
                workspace_abs=workspace_abs,
                brief=brief,
                topic_doc=topic_doc,
                template_dir=template_dir,
            ),
            encoding="utf-8",
        )
        logger.info("Wrote project CLAUDE.md skeleton: %s", claude_md)

    # Ensure workspace/experiments/ exists so local experiment target resolves.
    try:
        (project_workspace(port) / "experiments").mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # non-fatal
        logger.warning("Could not create workspace/experiments/: %s", exc)

    # Register in projects.json.
    _store.add_project(entry)

    logger.info("project_create done: port=%d pid=%d", port, proc.pid)
    return entry


def project_dormant(
    port: int,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Transition project *port* to dormant state.

    - Stops the EACN3 backend.
    - Dismisses all roles (updates state only; actual subprocess termination
      is handled by lifecycle/role.py callers before calling this).
    - Writes a git tag ``minionsos/dormant/project-{port}-<ts>``.
    - Updates ``meta.json`` and ``projects.json``.
    """
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status != "active":
        raise ProjectError(f"Project {port} is not active (status={entry.status}).")

    logger.info("project_dormant port=%d", port)

    # Stop backend.
    meta = _read_meta(port)
    backend_pid: int | None = getattr(meta, "backend_pid", None)
    # Try to read from meta.json raw dict for extra fields.
    try:
        raw = project_meta_json(port).read_text(encoding="utf-8")
        raw_dict = json.loads(raw)
        backend_pid = raw_dict.get("backend_pid")
    except Exception:
        pass
    _stop_backend(port, backend_pid)

    now = _now_iso()
    ts = now.replace(":", "-").replace(".", "-")
    tag = f"minionsos/dormant/project-{port}-{ts}"
    _git_tag(port, tag)

    updated = _store.update_project(
        port,
        status="dormant",
        dormant_at=now,
        active_roles=[r.model_copy(update={"state": "dismissed"}) for r in entry.active_roles],
    )
    _write_meta(port, updated)
    logger.info("project_dormant done: port=%d tag=%s", port, tag)
    return updated


def project_close(
    port: int,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Transition project *port* to closed state.

    Same as dormant, plus:
    - Writes git tag ``minionsos/closed/project-{port}``.
    - Permanently retires the port.
    """
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status == "closed":
        raise ProjectError(f"Project {port} is already closed.")

    logger.info("project_close port=%d", port)

    # If still active, stop backend first.
    if entry.status == "active":
        try:
            raw = project_meta_json(port).read_text(encoding="utf-8")
            backend_pid = json.loads(raw).get("backend_pid")
        except Exception:
            backend_pid = None
        _stop_backend(port, backend_pid)

    now = _now_iso()
    ts = now.replace(":", "-").replace(".", "-")
    dormant_tag = f"minionsos/dormant/project-{port}-{ts}"
    closed_tag = f"minionsos/closed/project-{port}"
    if entry.status == "active":
        _git_tag(port, dormant_tag)
    _git_tag(port, closed_tag)

    updated = _store.update_project(
        port,
        status="closed",
        closed_at=now,
        dormant_at=entry.dormant_at or now,
        active_roles=[r.model_copy(update={"state": "dismissed"}) for r in entry.active_roles],
    )
    _write_meta(port, updated)
    _store.retire_port(port)
    logger.info("project_close done: port=%d", port)
    return updated


def project_revive(
    port: int,
    external_feedback: str | None = None,
    feedback_source: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Revive a dormant project.

    - Re-starts the EACN3 backend on the same port.
    - Restores ``active_roles`` from ``meta.json``.
    - If *external_feedback* is provided, archives it to
      ``artifacts/external_feedback/<ts>.md``.
    - Updates ``meta.json`` and ``projects.json``.

    Note: actual role subprocess re-spawning is done by the caller (Gru /
    MCP tool layer) after this function returns.
    """
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status != "dormant":
        raise ProjectError(f"project_revive requires dormant status; got {entry.status!r}.")

    logger.info("project_revive port=%d", port)

    # Re-start backend.
    proc = _start_backend(port)
    try:
        _wait_for_health(port)
    except BackendError:
        proc.terminate()
        raise

    # Re-register server with the fresh EACN3 backend.
    try:
        server_id, eacn3_server_token = _register_server(port)
    except BackendError as exc:
        logger.warning("Server re-registration failed (non-fatal): %s", exc)
        server_id, eacn3_server_token = "", ""

    now = _now_iso()

    # Inject external feedback if provided.
    if external_feedback:
        fb_dir = project_dir(port) / "artifacts" / "external_feedback"
        fb_dir.mkdir(parents=True, exist_ok=True)
        ts_safe = now.replace(":", "-").replace(".", "-")
        fb_path = fb_dir / f"{ts_safe}.md"
        source_line = f"**Source:** {feedback_source}\n\n" if feedback_source else ""
        fb_path.write_text(
            f"# External Feedback — {now}\n\n{source_line}{external_feedback}\n",
            encoding="utf-8",
        )
        logger.info("Archived external feedback to %s", fb_path)

    # Restore roles to sleeping state (caller will re-spawn them).
    revived_roles = [
        r.model_copy(update={"state": "sleeping", "pid": None}) for r in entry.active_roles
    ]

    updated = _store.update_project(
        port,
        status="active",
        dormant_at=None,
    )
    # Manually set active_roles since update_project doesn't deep-merge lists.
    updated = _store.update_project(port, active_roles=revived_roles)

    # Persist backend PID and new server_id in meta.json.
    raw_dict = json.loads(project_meta_json(port).read_text(encoding="utf-8"))
    raw_dict.update(updated.model_dump())
    raw_dict["backend_pid"] = proc.pid
    raw_dict["eacn3_server_id"] = server_id
    raw_dict["eacn3_server_token"] = eacn3_server_token
    tmp = project_meta_json(port).with_suffix(".tmp")
    tmp.write_text(json.dumps(raw_dict, indent=2), encoding="utf-8")
    os.replace(tmp, project_meta_json(port))

    logger.info("project_revive done: port=%d pid=%d", port, proc.pid)
    return updated
