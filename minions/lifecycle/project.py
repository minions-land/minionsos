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
from pathlib import Path

import httpx

from minions.errors import BackendError, ProjectError
from minions.lifecycle import eacn_client
from minions.lifecycle.eacn_identity import identity_map_for_meta, upsert_agent_identity
from minions.paths import (
    MINIONS_ROOT,
    configured_project_parent_repo,
    project_backend_log,
    project_branch_name,
    project_dir,
    project_eacn_db,
    project_logs_dir,
    project_main_workspace,
    project_meta_json,
    project_role_workspace,
    project_roles_workspace_dir,
    project_session_name,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)
from minions.state.store import ProjectEntry, RoleEntry, StateStore

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


def _write_meta(
    port: int,
    entry: ProjectEntry,
    extras: dict[str, object] | None = None,
) -> None:
    """Write ``meta.json`` for *port*, preserving any prior extra fields.

    ``ProjectEntry`` is configured with ``extra="allow"`` but runtime-only
    fields (``backend_pid``, ``eacn3_server_id``, ``eacn3_server_token``,
    ``gru_agent_id``, ``gru_agent_token``, ``topic_doc``, ``template_dir``,
    ...) are generally kept on disk rather than round-tripped through the
    store. To avoid silently dropping them on dormant / revive cycles, we
    read the existing meta.json first, overlay the current entry dump on
    top, and overlay explicit *extras* last.
    """
    path = project_meta_json(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    base: dict[str, object] = {}
    if path.exists():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(base, dict):
                base = {}
        except Exception:
            base = {}
    base.update(entry.model_dump())
    if extras:
        base.update(extras)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(base, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_meta_raw(port: int) -> dict[str, object]:
    """Read raw ``meta.json`` dict for *port*, preserving extras.

    Prefer this over constructing a ``ProjectEntry`` when you only need
    the on-disk dict (e.g. to read runtime-only fields like ``backend_pid``
    that are stored on disk but not in ``projects.json``).
    """
    path = project_meta_json(port)
    if not path.exists():
        raise ProjectError(f"meta.json not found for port {port}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProjectError(f"meta.json for port {port} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ProjectError(f"meta.json for port {port} is not an object.")
    return data


def _port_is_free(port: int) -> bool:
    """Return True if *port* can be bound right now."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _is_git_work_tree(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except FileNotFoundError:
        return False


def project_parent_repo() -> Path:
    """Return the git repository used as the source for project worktrees."""
    configured = configured_project_parent_repo()
    if configured is not None:
        return configured
    if _is_git_work_tree(MINIONS_ROOT.parent):
        return MINIONS_ROOT.parent
    if _is_git_work_tree(MINIONS_ROOT):
        return MINIONS_ROOT
    return MINIONS_ROOT.parent


def _start_backend(port: int) -> subprocess.Popen:  # type: ignore[type-arg]
    """Start the EACN3 uvicorn backend subprocess for *port*.

    Pre-checks port availability. Raises ``BackendError`` if occupied.
    Logs go to ``project_{port}/logs/backend.log``.
    """
    if not _port_is_free(port):
        raise BackendError(f"Port {port} is already occupied. Cannot start backend.")

    db_path = str(project_eacn_db(port))
    log_path = project_backend_log(port)
    log_path.parent.mkdir(parents=True, exist_ok=True)

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


def _ensure_local_balance(port: int, agent_id: str) -> None:
    """Best-effort local EACN credit seeding for MinionsOS project agents."""
    try:
        from minions.config import load_gru_config

        minimum = load_gru_config().local_eacn_initial_balance
        eacn_client.ensure_balance(port, agent_id, minimum)
    except Exception as exc:
        logger.warning(
            "Could not seed local EACN balance for agent=%s port=%d: %s",
            agent_id,
            port,
            exc,
        )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _clear_stale_role_pids(port: int, entry: ProjectEntry, store: StateStore) -> list[str]:
    """Clear persisted ephemeral PIDs that no longer refer to live processes."""
    cleared: list[str] = []
    for role in entry.active_roles:
        if role.state not in {"active", "sleeping"} or role.pid is None:
            continue
        if _pid_alive(int(role.pid)):
            continue
        try:
            updates: dict[str, object | None] = {"pid": None}
            if role.state == "active":
                updates["state"] = "sleeping"
            store.upsert_role(port, role.model_copy(update=updates))
            cleared.append(role.name)
        except Exception as exc:
            logger.debug(
                "project_repair: failed clearing stale pid port=%d role=%s pid=%s: %s",
                port,
                role.name,
                role.pid,
                exc,
            )
    return cleared


def _role_entries_from_meta(raw: dict[str, object]) -> list[RoleEntry]:
    """Best-effort RoleEntry list from raw meta.json."""
    raw_roles = raw.get("active_roles")
    if not isinstance(raw_roles, list):
        return []
    roles: list[RoleEntry] = []
    for item in raw_roles:
        if not isinstance(item, dict):
            continue
        try:
            roles.append(RoleEntry.model_validate(item))
        except Exception as exc:
            logger.debug("Skipping invalid role entry from meta.json: %s", exc)
    return roles


def _default_poll_interval() -> str:
    try:
        from minions.config import load_gru_config

        return load_gru_config().poll_interval_default
    except Exception:
        return "1m"


def _default_noter_time_trigger_interval() -> str | None:
    try:
        from minions.config import load_gru_config, parse_duration

        interval = load_gru_config().noter_report_interval
        return interval if parse_duration(interval) > 0 else None
    except Exception:
        return "30m"


def _normalise_revived_role(role: RoleEntry) -> RoleEntry:
    """Return a schedulable sleeping role, repairing old Noter records."""
    time_trigger = role.time_trigger_interval
    if role.name == "noter" and not time_trigger:
        time_trigger = _default_noter_time_trigger_interval()

    updates: dict[str, object | None] = {
        "state": "sleeping",
        "pid": None,
        "poll_interval": role.poll_interval or _default_poll_interval(),
        "time_trigger_interval": time_trigger,
    }
    if time_trigger:
        updates["wake_policy"] = "any"
    elif role.wake_policy == "time":
        updates["wake_policy"] = "event"
    return role.model_copy(update=updates)


def _roles_for_revive(entry: ProjectEntry, raw_meta: dict[str, object]) -> list[RoleEntry]:
    """Choose role records for revive.

    ``projects.json`` is the normal source of truth. ``meta.json`` is kept as a
    fallback because older lifecycle paths and manual repairs can leave one file
    ahead of the other.
    """
    roles = list(entry.active_roles)
    if not roles:
        roles = _role_entries_from_meta(raw_meta)
    return [_normalise_revived_role(role) for role in roles]


def _gru_agent_spec() -> tuple[str, list[str], str]:
    from minions.config import load_gru_config

    gru_agent_id = load_gru_config().gru_eacn_agent_id
    gru_domains = ["minionsos", "project-local", "role:gru", "coordination"]
    gru_description = (
        "MinionsOS global coordinator EACN queue on this project. "
        "Polled by Gru through the MinionsOS gru_inbox_poll adapter."
    )
    return gru_agent_id, gru_domains, gru_description


def _register_gru_eacn_agent(port: int, server_id: str) -> tuple[str, str]:
    gru_agent_id, gru_domains, gru_description = _gru_agent_spec()
    gru_agent_token, _seeds = eacn_client.register_agent(
        port=port,
        agent_id=gru_agent_id,
        name="gru",
        server_id=server_id,
        domains=gru_domains,
        description=gru_description,
        tier="coordinator",
    )
    _ensure_local_balance(port, gru_agent_id)
    upsert_agent_identity(
        port,
        role_name="gru",
        agent_id=gru_agent_id,
        kind="gru_mailbox",
        server_id=server_id,
        agent_token=gru_agent_token,
        domains=gru_domains,
        tier="coordinator",
        description=gru_description,
        name="gru",
    )
    return gru_agent_id, gru_agent_token


def _backend_listener_pids(port: int) -> list[int]:
    """Return PIDs listening on *port*, best effort.

    This is used only as a fallback when ``meta.json`` has a missing/stale
    backend PID. Keep it conservative: callers still verify the command line
    before killing a discovered process.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if result.returncode not in {0, 1}:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return list(dict.fromkeys(pids))


def _pid_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_minions_backend_pid(pid: int, port: int) -> bool:
    """Return True when process metadata matches this project's EACN backend."""
    command = _pid_command(pid)
    return "uvicorn" in command and EACN_APP in command and str(port) in command


def _terminate_backend_pid(port: int, pid: int) -> None:
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


def _stop_backend(port: int, pid: int | None) -> bool:
    """Terminate the backend process for *port* gracefully.

    Returns True if the backend port is free afterwards. If the recorded PID is
    missing or stale, fall back to the listener on the project port, but only
    kill a discovered process whose command line matches MinionsOS' uvicorn
    backend.
    """
    if pid is not None:
        _terminate_backend_pid(port, pid)
        if _port_is_free(port):
            return True

    if _port_is_free(port):
        return True

    fallback_pids = [p for p in _backend_listener_pids(port) if p != pid]
    for fallback_pid in fallback_pids:
        if not _is_minions_backend_pid(fallback_pid, port):
            logger.warning(
                "Refusing to stop unverified listener PID=%d on port %d; command=%r",
                fallback_pid,
                port,
                _pid_command(fallback_pid),
            )
            continue
        logger.info(
            "Stopping backend listener PID=%d discovered on port %d after stale/missing meta PID.",
            fallback_pid,
            port,
        )
        _terminate_backend_pid(port, fallback_pid)
        if _port_is_free(port):
            return True

    logger.warning("Backend on port %d is still listening after stop attempt.", port)
    return False


class _AdoptedBackend:
    """Small proc-like wrapper for a backend already running on the project port."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def terminate(self) -> None:
        # This process predates revive; leave it running if a later revive step
        # fails so the operator can inspect/repair without another side effect.
        return None


def _adopt_running_backend(port: int) -> _AdoptedBackend | None:
    """Return an existing MinionsOS backend for *port*, if safely identifiable."""
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    for pid in _backend_listener_pids(port):
        if _is_minions_backend_pid(pid, port):
            logger.info("Adopting already-running backend PID=%d on port %d.", pid, port)
            return _AdoptedBackend(pid)
    return None


def _stop_role_process(port: int, role_name: str, pid: int | None) -> str:
    """Terminate a recorded ephemeral Role subprocess without touching EACN data."""
    if pid is None:
        return "no_pid"
    try:
        import signal

        if not _pid_alive(pid):
            return "already_gone"

        pgid: int | None = None
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            return "already_gone"
        except Exception as exc:
            logger.debug(
                "project_kill: could not read pgid port=%d role=%s pid=%d: %s",
                port,
                role_name,
                pid,
                exc,
            )

        use_group = bool(pgid and pgid > 0 and pgid != os.getpgrp())

        def _send(sig: int) -> None:
            if use_group and pgid is not None:
                os.killpg(pgid, sig)
            else:
                os.kill(pid, sig)

        _send(signal.SIGTERM)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not _pid_alive(pid):
                logger.info("Stopped role PID=%d (role=%s port=%d).", pid, role_name, port)
                return "terminated"
            time.sleep(0.1)

        _send(signal.SIGKILL)
        logger.info("Killed role PID=%d (role=%s port=%d).", pid, role_name, port)
        return "killed"
    except ProcessLookupError:
        return "already_gone"
    except Exception as exc:
        logger.warning(
            "Error stopping role PID=%d (role=%s port=%d): %s",
            pid,
            role_name,
            port,
            exc,
        )
        return f"error:{exc}"


def _ensure_parent_is_git_repo() -> None:
    """Verify that MINIONS_ROOT.parent is a git repository.

    The worktree mechanism needs a git repo to branch off of. If no configured
    or inferred project parent repo is usable, we fail fast with an actionable
    message
    instead of letting ``git worktree add`` emit a cryptic
    ``fatal: not a git repository`` error.
    """
    parent_repo = project_parent_repo()
    if not _is_git_work_tree(parent_repo):
        configured = configured_project_parent_repo()
        config_hint = (
            "Check MINIONS_PROJECT_PARENT_REPO or gru.yaml:project_parent_repo.\n"
            if configured is not None
            else "Set gru.yaml:project_parent_repo if your research repo lives elsewhere.\n"
        )
        raise ProjectError(
            f"The project parent repo ({parent_repo}) is not a git "
            "repository. MinionsOS creates project worktrees branched from this "
            "repo, so it must be git-initialized before project_create.\n"
            "Fix with:\n"
            f"    cd {parent_repo} && git init && git add -A && "
            "git commit -m 'init'\n"
            f"{config_hint}"
        )


def _create_worktree(port: int, base_branch: str) -> str:
    """Create a git worktree for *port* inside the parent repo.

    Returns the branch name ``minionsos/project-{port}``.
    """
    branch = f"minionsos/project-{port}"
    workspace = project_main_workspace(port)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    parent_repo = project_parent_repo()

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
    parent_repo = project_parent_repo()
    result = subprocess.run(
        ["git", "tag", tag],
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("git tag %s failed: %s", tag, result.stderr.strip())


def _ensure_workspace_layout(port: int) -> None:
    """Create the non-worktree workspace containers for *port*."""
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_roles_workspace_dir(port).mkdir(parents=True, exist_ok=True)
    project_shared_workspace(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)


def project_workspace(port: int) -> Path:
    """Backward-compatible alias for the canonical main workspace."""
    return project_main_workspace(port)


def _create_role_worktree(
    port: int,
    role_name: str,
    base_branch: str | None = None,
) -> tuple[str, Path]:
    """Create or verify the git worktree for one role."""
    branch = project_branch_name(port, role_name)
    workspace = project_role_workspace(port, role_name)
    if role_name == "gru":
        workspace.mkdir(parents=True, exist_ok=True)
        return branch, workspace
    if workspace.exists():
        if _is_git_work_tree(workspace):
            return branch, workspace
        raise ProjectError(
            f"Role workspace already exists but is not a git worktree: {workspace}"
        )

    workspace.parent.mkdir(parents=True, exist_ok=True)
    parent_repo = project_parent_repo()
    resolved_base = base_branch if base_branch not in {None, ""} else project_branch_name(port)
    cmd = [
        "git",
        "worktree",
        "add",
        "-b",
        branch,
        str(workspace),
        resolved_base,
    ]
    logger.info("Creating role worktree: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(parent_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProjectError(
            f"git worktree add failed for role {role_name!r} on port {port}: "
            f"{result.stderr.strip()}"
        )
    return branch, workspace


def ensure_role_workspace(
    port: int,
    role_name: str,
    base_branch: str | None = None,
) -> tuple[str, Path]:
    """Public wrapper that returns the role branch and workspace path."""
    return _create_role_worktree(port, role_name, base_branch=base_branch)


_PROJECT_GITIGNORE = """\
# MinionsOS project workspace hygiene.
# Only structured subdirectories are tracked; stray files are ignored.
*
!.gitignore
!CLAUDE.md
!AGENTS.md
!meta.json
!workspace/
!workspace/**
!artifacts/
!artifacts/**
!memory/
!memory/**
!logs/
!logs/**
!eacn3_data/
!eacn3_data/**
"""


def _write_project_gitignore(pdir: Path) -> None:
    """Write a restrictive .gitignore into the project directory."""
    gi = pdir / ".gitignore"
    if not gi.exists():
        gi.write_text(_PROJECT_GITIGNORE, encoding="utf-8")


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
        "> Project-scoped narrative. Authored jointly by the human and Gru; other Roles read-only."
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
    lines.append(brief.strip() if brief else "_TODO: write a 1-3 paragraph project brief._")
    lines.append("")
    lines.append("## Working rules")
    lines.append("")
    lines.append("- All inter-Role communication goes through EACN3 on this port.")
    lines.append(
        "- Workspace container: `workspace/main/` is the primary integration tree; "
        "role worktrees live under `workspace/roles/<role>/`; shared handoffs live under "
        "`workspace/shared/`."
    )
    lines.append(
        "- Root constitution at repo `CLAUDE.md` always wins on conflicts (see Hard rules)."
    )
    lines.append("")
    return "\n".join(lines)


def _render_project_agents_md(real_name: str) -> str:
    """Render a Codex-compatible project context shim."""
    return "\n".join(
        [
            f"# {real_name} — Project Agent Context",
            "",
            "This project is managed by MinionsOS.",
            "",
            "Read `CLAUDE.md` in this directory for the project-scoped narrative, facts,",
            "working rules, and current brief. In this repository, `CLAUDE.md` is kept",
            "as the shared project context file for both Claude Code and Codex so the",
            "two agent hosts see the same operating assumptions.",
            "",
        ]
    )


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

    try:
        from minions.config import load_gru_config

        cfg = load_gru_config()
        github_push_target = cfg.github_push_target
        github_push_branch_prefix = cfg.github_push_branch_prefix
    except Exception:
        github_push_target = None
        github_push_branch_prefix = None

    # Create directory structure.
    pdir = project_dir(port)
    pdir.mkdir(parents=True, exist_ok=True)
    _ensure_workspace_layout(port)
    project_logs_dir(port).mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "notes").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "reports").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "flags" / "open").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "flags" / "resolved").mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts" / "ethics" / "investigations").mkdir(parents=True, exist_ok=True)
    (pdir / "memory").mkdir(parents=True, exist_ok=True)
    (pdir / "eacn3_data").mkdir(parents=True, exist_ok=True)

    # Workspace hygiene: write a .gitignore to prevent unstructured files.
    _write_project_gitignore(pdir)

    # Create git worktree.
    try:
        _ensure_parent_is_git_repo()
        branch = _create_worktree(port, base_branch)
    except ProjectError as exc:
        logger.error("Worktree creation failed: %s", exc)
        raise

    # Start backend with port-conflict retry.
    max_retries = 3
    for attempt in range(max_retries):
        try:
            proc = _start_backend(port)
            _wait_for_health(port)
            break
        except BackendError as exc:
            if attempt < max_retries - 1:
                logger.warning(
                    "Port %d unavailable (attempt %d/%d): %s",
                    port,
                    attempt + 1,
                    max_retries,
                    exc,
                )
                port = _store.find_next_port()
                pdir = project_dir(port)
                pdir.mkdir(parents=True, exist_ok=True)
                project_logs_dir(port).mkdir(parents=True, exist_ok=True)
            else:
                raise

    # Register a server record with EACN3 so roles can register as agents.
    # Now FATAL: a silently-absent server breaks downstream role registration
    # and gru-inbox delivery, so fail loud rather than limp along.
    try:
        server_id, eacn3_server_token = _register_server(port)
    except BackendError as exc:
        logger.error("Server registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    # Register the "gru" EACN queue agent on this project's bus so that
    # role -> gru direct messages land in a real EACN inbox.
    # FATAL on failure: without it, every Role -> Gru EACN message is
    # silently dropped.
    try:
        gru_agent_id, gru_agent_token = _register_gru_eacn_agent(port, server_id)
    except BackendError as exc:
        logger.error("Gru agent registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    now = _now_iso()
    entry = ProjectEntry(
        port=port,
        real_name=real_name,
        status="active",
        created=now,
        venue=venue,
        upstream_branch=upstream or base_branch,
        current_branch=branch,
        workspace_root=str(project_workspace_root(port).resolve()),
        workspace_main=str(project_main_workspace(port).resolve()),
        workspace_roles_root=str(project_roles_workspace_dir(port).resolve()),
        workspace_shared=str(project_shared_workspace(port).resolve()),
        github_push_target=github_push_target,
        github_push_branch_prefix=github_push_branch_prefix,
        active_roles=[],
    )
    # Store backend PID, server_id, and eacn3_server_token in extra fields.
    entry_dict = entry.model_dump()
    entry_dict["backend_pid"] = proc.pid
    entry_dict["eacn3_server_id"] = server_id
    entry_dict["eacn3_server_token"] = eacn3_server_token
    entry_dict["gru_agent_id"] = gru_agent_id
    entry_dict["gru_agent_token"] = gru_agent_token
    entry_dict["eacn_agent_map"] = identity_map_for_meta(port)
    entry_dict["workspace_root"] = str(project_workspace_root(port).resolve())
    entry_dict["workspace_main"] = str(project_main_workspace(port).resolve())
    entry_dict["workspace_roles_root"] = str(project_roles_workspace_dir(port).resolve())
    entry_dict["workspace_shared"] = str(project_shared_workspace(port).resolve())
    entry_dict["github_push_target"] = github_push_target
    entry_dict["github_push_branch_prefix"] = github_push_branch_prefix
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
    agents_md = pdir / "AGENTS.md"
    workspace_abs = str(project_main_workspace(port).resolve())
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
    if not agents_md.exists():
        agents_md.write_text(_render_project_agents_md(real_name), encoding="utf-8")
        logger.info("Wrote project AGENTS.md shim: %s", agents_md)

    # Ensure workspace/main/experiments/ exists so local experiment target resolves.
    try:
        (project_main_workspace(port) / "experiments").mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # non-fatal
        logger.warning("Could not create workspace/main/experiments/: %s", exc)

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

    # Stop backend. Read backend_pid from the on-disk meta (not from the
    # store entry — runtime-only fields live on disk).
    backend_pid: int | None = None
    try:
        raw_dict = _read_meta_raw(port)
        backend_pid = raw_dict.get("backend_pid")  # type: ignore[assignment]
    except (ProjectError, Exception):
        pass
    if _stop_backend(port, backend_pid) is False:
        raise ProjectError(f"Could not stop backend on port {port}; project left active.")

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
        if _stop_backend(port, backend_pid) is False:
            raise ProjectError(
                f"Could not stop backend on port {port}; project left {entry.status}."
            )

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


def project_kill(
    port: int,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Hard-stop one project's runtime without deleting its EACN network data.

    This is intentionally narrower than ``project_close`` and ``wipe``:
    it stops the recorded backend and Role subprocesses, marks the project
    dormant so Gru/WakeupScheduler stop polling it, and preserves
    ``project_<port>/eacn3_data`` plus the port reservation for revive.
    """
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status == "closed":
        raise ProjectError(f"Project {port} is already closed.")

    logger.info("project_kill port=%d", port)

    backend_pid: int | None = None
    try:
        raw_dict = _read_meta_raw(port)
        raw_pid = raw_dict.get("backend_pid")
        if raw_pid is not None:
            backend_pid = int(raw_pid)
    except Exception as exc:
        logger.debug("project_kill: backend_pid unavailable port=%d: %s", port, exc)
    if _stop_backend(port, backend_pid) is False:
        raise ProjectError(f"Could not stop backend on port {port}; project left {entry.status}.")

    role_results: list[dict[str, object]] = []
    for role in entry.active_roles:
        if role.pid is None:
            continue
        status = _stop_role_process(port, role.name, role.pid)
        role_results.append({"name": role.name, "pid": role.pid, "status": status})

    now = _now_iso()
    updated = _store.update_project(
        port,
        status="dormant",
        dormant_at=entry.dormant_at or now,
        active_roles=[
            r.model_copy(update={"state": "dismissed", "pid": None}) for r in entry.active_roles
        ],
    )
    _write_meta(port, updated, extras={"backend_pid": None})
    logger.info(
        "project_kill done: port=%d backend_pid=%s roles=%d",
        port,
        backend_pid,
        len(role_results),
    )
    return {
        "port": updated.port,
        "status": updated.status,
        "backend_pid": backend_pid,
        "roles": role_results,
    }


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
    raw_meta = _read_meta_raw(port)

    # Re-start backend. If a previous kill/dormant attempt left the backend
    # running despite marking the project dormant, safely adopt that backend
    # instead of failing forever on "port already occupied".
    try:
        proc = _start_backend(port)
    except BackendError:
        adopted = _adopt_running_backend(port)
        if adopted is None:
            raise
        proc = adopted
    else:
        try:
            _wait_for_health(port)
        except BackendError:
            proc.terminate()
            raise

    # Re-register server with the fresh EACN3 backend (FATAL on failure).
    try:
        server_id, eacn3_server_token = _register_server(port)
    except BackendError as exc:
        logger.error("Server re-registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    # Re-register the "gru" EACN queue agent on the fresh backend.
    try:
        gru_agent_id, gru_agent_token = _register_gru_eacn_agent(port, server_id)
    except BackendError as exc:
        logger.error("Gru agent re-registration failed (fatal): %s", exc)
        proc.terminate()
        raise

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

    # Restore roles to sleeping state and re-register each project-local AgentCard
    # on the fresh EACN3 backend before exposing them in projects.json.
    revived_roles: list[RoleEntry] = []
    try:
        from minions.lifecycle.agent_registry import register_project_role_agent

        for restored in _roles_for_revive(entry, raw_meta):
            workspace_branch, workspace_path = ensure_role_workspace(
                port,
                restored.name,
                base_branch=entry.current_branch or None,
            )
            role_token, _role_seeds = register_project_role_agent(
                port,
                restored.name,
                server_id=server_id,
            )
            restored = restored.model_copy(
                update={
                    "eacn_agent_id": restored.name,
                    "eacn_agent_token": role_token,
                    "eacn_registered_at": now,
                    "session_name": restored.session_name
                    or project_session_name(port, restored.name),
                    "workspace_path": restored.workspace_path
                    or str(workspace_path.resolve()),
                    "workspace_branch": restored.workspace_branch or workspace_branch,
                    "github_push_target": restored.github_push_target
                    or getattr(entry, "github_push_target", None)
                    or raw_meta.get("github_push_target"),
                }
            )
            revived_roles.append(restored)
    except (BackendError, ProjectError) as exc:
        logger.error("Role workspace/EACN restore failed during revive (fatal): %s", exc)
        proc.terminate()
        raise

    updated = _store.update_project(
        port,
        status="active",
        dormant_at=None,
        active_roles=revived_roles,
    )

    # Persist backend PID and new server_id in meta.json (preserving extras).
    _write_meta(
        port,
        updated,
        extras={
            "backend_pid": proc.pid,
            "eacn3_server_id": server_id,
            "eacn3_server_token": eacn3_server_token,
            "gru_agent_id": gru_agent_id,
            "gru_agent_token": gru_agent_token,
            "eacn_agent_map": identity_map_for_meta(port),
        },
    )

    logger.info("project_revive done: port=%d pid=%d", port, proc.pid)
    return updated


def project_repair_eacn_agents(
    port: int,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Repair project-local EACN registrations for Gru and active Roles.

    Idempotent repair for projects whose EACN3 backend was restarted without
    going through ``project_revive`` or whose Gru process restarted with stale
    ephemeral Role PIDs in ``projects.json``. This function only uses MinionsOS
    adapters around EACN3; it does not require EACN3 code changes.

    Returns a structured summary with registered/already Role agents and stale
    PIDs cleared.
    Raises ``ProjectError`` / ``BackendError`` on failure.
    """
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")

    meta_path = project_meta_json(port)
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    server_id = raw.get("eacn3_server_id") or ""
    if not server_id:
        raise ProjectError(
            f"Project {port} has no eacn3_server_id in meta.json; "
            "cannot repair without re-creating the project."
        )
    server_token = str(raw.get("eacn3_server_token", ""))
    if eacn_client.get_server_card(port, str(server_id)) is None:
        logger.info(
            "project_repair: server_id=%s missing on port %d; registering a fresh server.",
            server_id,
            port,
        )
        server_id, server_token = _register_server(port)
        raw["eacn3_server_id"] = server_id
        raw["eacn3_server_token"] = server_token
    else:
        eacn_client.server_heartbeat(port, str(server_id))

    gru_agent_id, _gru_domains, _gru_description = _gru_agent_spec()

    # Probe first — if already registered, no-op.
    snap = eacn_client.probe_backend(port)
    if snap.get("health") is False and not snap.get("agents"):
        raise BackendError(f"Project {port} EACN backend is not healthy; cannot repair agents.")
    existing_ids = {
        str(a.get("agent_id"))
        for a in snap.get("agents", [])
        if isinstance(a, dict) and a.get("agent_id")
    }

    gru_status = "already"
    gru_agent_token = str(raw.get("gru_agent_token", ""))
    if gru_agent_id not in existing_ids:
        gru_agent_id, gru_agent_token = _register_gru_eacn_agent(port, str(server_id))
        gru_status = "registered"
        existing_ids.add(gru_agent_id)
    else:
        _ensure_local_balance(port, gru_agent_id)

    from minions.lifecycle.agent_registry import register_project_role_agent

    registered_roles: list[str] = []
    already_roles: list[str] = []
    refreshed_entry = _store.get_project(port) or entry
    cleared_pids = _clear_stale_role_pids(port, refreshed_entry, _store)
    refreshed_entry = _store.get_project(port) or refreshed_entry
    now = _now_iso()

    for role in refreshed_entry.active_roles:
        if role.state not in {"active", "sleeping"}:
            continue
        workspace_branch, workspace_path = ensure_role_workspace(
            port,
            role.name,
            base_branch=refreshed_entry.current_branch or None,
        )
        role_workspace_updates: dict[str, object | None] = {}
        if not role.session_name:
            role_workspace_updates["session_name"] = project_session_name(port, role.name)
        if not role.workspace_path:
            role_workspace_updates["workspace_path"] = str(workspace_path.resolve())
        if not role.workspace_branch:
            role_workspace_updates["workspace_branch"] = workspace_branch
        if not role.github_push_target:
            role_workspace_updates["github_push_target"] = (
                getattr(refreshed_entry, "github_push_target", None)
                or raw.get("github_push_target")
            )
        if role_workspace_updates:
            role = role.model_copy(update=role_workspace_updates)
        agent_id = role.eacn_agent_id or role.name
        if agent_id in existing_ids:
            already_roles.append(role.name)
            _ensure_local_balance(port, agent_id)
            if role_workspace_updates:
                _store.upsert_role(port, role)
            continue
        role_token, _role_seeds = register_project_role_agent(
            port,
            role.name,
            server_id=str(server_id),
        )
        registered_roles.append(role.name)
        existing_ids.add(role.name)
        _store.upsert_role(
            port,
            role.model_copy(
                update={
                    "pid": None,
                    "eacn_agent_id": role.name,
                    "eacn_agent_token": role_token,
                    "eacn_registered_at": now,
                    **role_workspace_updates,
                }
            ),
        )

    raw["gru_agent_id"] = gru_agent_id
    raw["gru_agent_token"] = gru_agent_token
    raw["eacn3_server_id"] = server_id
    raw["eacn3_server_token"] = server_token
    raw["eacn_agent_map"] = identity_map_for_meta(port)
    tmp = meta_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    os.replace(tmp, meta_path)

    status = (
        "already"
        if gru_status == "already" and not registered_roles and not cleared_pids
        else "repaired"
    )
    logger.info(
        "project_repair: port=%d status=%s gru=%s registered_roles=%s cleared_pids=%s",
        port,
        status,
        gru_status,
        registered_roles,
        cleared_pids,
    )
    return {
        "status": status,
        "gru_status": gru_status,
        "gru_agent_id": gru_agent_id,
        "gru_agent_token": gru_agent_token,
        "role_agents_registered": registered_roles,
        "role_agents_already": already_roles,
        "stale_pids_cleared": cleared_pids,
    }


def project_repair_gru_agent(
    port: int,
    store: StateStore | None = None,
) -> dict[str, str]:
    """Backward-compatible repair for only the project-local ``gru`` queue agent."""
    result = project_repair_eacn_agents(port, store=store)
    gru_status = str(result.get("gru_status") or "already")
    return {
        "status": "registered" if gru_status == "registered" else "already",
        "gru_agent_id": str(result.get("gru_agent_id") or ""),
        "gru_agent_token": str(result.get("gru_agent_token") or ""),
    }
