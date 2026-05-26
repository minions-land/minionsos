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
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from minions.config import slugify
from minions.errors import BackendError, ProjectError
from minions.lifecycle import (
    _project_phase,
    _project_templates,
    _project_worktree,
    eacn_client,
)
from minions.lifecycle.eacn_identity import identity_map_for_meta, upsert_agent_identity
from minions.lifecycle.git_utils import (
    find_enclosing_git_work_tree as _gu_find_enclosing_git_work_tree,
)
from minions.lifecycle.git_utils import (
    is_git_work_tree as _gu_is_git_work_tree,
)
from minions.lifecycle.git_utils import (
    run_git as _gu_run_git,
)
from minions.paths import (
    MINIONS_ROOT,
    configured_author_repo,
    project_backend_log,
    project_branch_name,
    project_dir,
    project_eacn_db,
    project_logs_dir,
    project_main_workspace,
    project_meta_json,
    project_parent_repo_dir,
    project_role_workspace,
    project_roles_workspace_dir,
    project_session_ledger,
    project_session_name,
    project_shared_subdir,
    project_shared_workspace,
    project_state_dir,
    project_workspace_root,
)
from minions.state.store import (
    ProjectEntry,
    ProjectPhaseSnapshot,
    RoleEntry,
    StateStore,
)

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
    return _gu_is_git_work_tree(path)


def author_repo() -> Path:
    """Return the author's source git repo used as the seed for new projects.

    Resolution order:
    1. ``MINIONS_AUTHOR_REPO`` env var or ``gru.yaml:author_repo``.
    2. ``MINIONS_ROOT.parent`` if it is **itself** a git work-tree root —
       the directory the user placed MinionsOS inside.
    3. ``MINIONS_ROOT`` itself if it is a git work-tree root.

    The author repo is touched **only at project_create time** to read its
    HEAD; it is never branched into, written to, or pushed against. After
    seeding, project history lives entirely inside
    ``project_{port}/parent_repo.git/``.

    The mental model: the user opens their repo ``B`` and drops
    MinionsOS underneath it (``B/MinionsOS``). MinionsOS only ever
    treats ``B`` as the seed source. If the user instead drops
    MinionsOS into a non-git directory that happens to live under
    *another* git repo ``A`` (layout ``A/B/MinionsOS`` where only ``A``
    is initialized), we refuse rather than silently importing ``A``'s
    HEAD — that would pull in ``A``'s siblings of ``B`` which the user
    never intended to ship into the project. The check is enforced in
    :func:`_ensure_author_repo_is_git_repo`.
    """
    configured = configured_author_repo()
    if configured is not None:
        return configured
    if _is_git_work_tree(MINIONS_ROOT.parent):
        return MINIONS_ROOT.parent
    if _is_git_work_tree(MINIONS_ROOT):
        return MINIONS_ROOT
    return MINIONS_ROOT.parent


def project_parent_repo(port: int) -> Path:
    """Return the per-project bare git repo for *port*.

    All worktrees (main, role, shared) are added against this repo, so each
    project's git history is fully isolated from every other project and
    from the author's own checkout.
    """
    return project_parent_repo_dir(port)


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


def _default_noter_time_trigger_interval() -> str | None:
    """Return Noter's default periodic-wake cadence.

    Noter wakes on this interval to flush the buffered Draft (L1) via
    ``mos_draft_commit_shared`` and to consider whether a fresh staged
    report is due (see ``noter_report_interval``). Defaults to ``5m`` so
    Draft history accumulates with bounded latency without flooding the
    shared branch with one commit per ``mos_draft_append`` call.
    """
    try:
        from minions.config import load_gru_config, parse_duration

        interval = load_gru_config().noter_periodic_interval
        return interval if parse_duration(interval) > 0 else None
    except Exception:
        return "5m"


def _migrate_legacy_memory_dirs(port: int) -> None:
    """Rename legacy memory directories from v11 naming to v12 naming.

    v11: branches/shared/scratchpad/ → v12: branches/shared/draft/
    v11: branches/shared/library/   → v12: branches/shared/book/

    Runs git mv inside the shared worktree so history is preserved.
    Idempotent: skips if old dir doesn't exist or new dir already exists.
    """
    shared = project_shared_workspace(port)
    if not shared.exists():
        return
    migrations = [
        ("scratchpad", "draft"),
        ("library", "book"),
    ]
    for old_name, new_name in migrations:
        old_dir = shared / old_name
        new_dir = shared / new_name
        if old_dir.exists() and not new_dir.exists():
            try:
                result = subprocess.run(
                    ["git", "mv", old_name, new_name],
                    cwd=str(shared),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    subprocess.run(
                        ["git", "commit", "-m", f"migrate: {old_name} → {new_name} (v12 rename)"],
                        cwd=str(shared),
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    logger.info("migrated %s->%s port=%d", old_name, new_name, port)
                else:
                    old_dir.rename(new_dir)
                    logger.info("renamed %s->%s (non-git) port=%d", old_name, new_name, port)
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "migration %s->%s failed port=%d: %s",
                    old_name,
                    new_name,
                    port,
                    exc,
                )
                if old_dir.exists() and not new_dir.exists():
                    old_dir.rename(new_dir)


def _normalise_revived_role(role: RoleEntry) -> RoleEntry:
    """Return a schedulable sleeping role, repairing old Noter records."""
    time_trigger = role.time_trigger_interval
    if role.name == "noter" and not time_trigger:
        time_trigger = _default_noter_time_trigger_interval()

    return role.model_copy(
        update={
            "state": "sleeping",
            "pid": None,
            "time_trigger_interval": time_trigger,
        }
    )


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
        "Drained by Gru's resident agent through mos_await_events."
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

    GitHub Issue #23: when the recorded PID is already dead and the port is
    free, ``_port_is_free`` can briefly return False on the first poll due to
    a TIME_WAIT / closing-socket window. We retry the port check for up to
    1 s in 100 ms increments before falling back to listener discovery, so a
    stale-PID stop is idempotent on the first call.
    """
    if pid is not None:
        _terminate_backend_pid(port, pid)
        for _ in range(10):
            if _port_is_free(port):
                return True
            time.sleep(0.1)

    for _ in range(10):
        if _port_is_free(port):
            return True
        time.sleep(0.1)

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
        for _ in range(10):
            if _port_is_free(port):
                return True
            time.sleep(0.1)

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


_LARGE_FILE_THRESHOLD_BYTES = 500 * 1024 * 1024  # 500 MB
_SEED_SKIP_DIR_NAMES: frozenset[str] = frozenset({".git", "MinionsOS", "minionsos"})


def _ensure_author_repo_is_git_repo() -> Path:
    """Verify that the author seed repo is a git work tree, return its path.

    The seed needs to read a real HEAD off some git work tree. If neither the
    configured ``author_repo`` nor ``MINIONS_ROOT.parent`` is a git repo,
    bail with an actionable message rather than letting ``git rev-parse``
    fail mid-create.

    Special case: if the candidate itself is not a work-tree *root* but is
    nested inside an outer git repo (e.g. ``A/.git`` exists, ``A/B`` does
    not, and MinionsOS is at ``A/B/MinionsOS``), we refuse and tell the
    user. Silently seeding the outer repo would import sibling
    directories of ``B`` that the user never wanted in their project.
    """
    src = author_repo()
    if not _is_git_work_tree(src):
        configured = configured_author_repo()
        enclosing = _gu_find_enclosing_git_work_tree(src) if src.exists() else None
        if enclosing is not None and enclosing != src.resolve():
            raise ProjectError(
                f"The author seed repo ({src}) is not its own git repository, "
                f"but it lives inside an outer git work tree ({enclosing}).\n"
                f"MinionsOS will not silently seed from the outer repo — that "
                f"would pull in everything under {enclosing} that is a "
                f"sibling of {src}, which you almost certainly do not want.\n"
                "Pick one fix:\n"
                f"  - If you meant to seed from {src}, run:\n"
                f"      cd {src} && git init && git add -A && git commit -m 'init'\n"
                f"  - If you meant to seed from {enclosing}, set explicitly:\n"
                f"      export MINIONS_AUTHOR_REPO={enclosing}\n"
                "    (or set ``author_repo`` in gru.yaml).\n"
            )
        config_hint = (
            "Check MINIONS_AUTHOR_REPO or gru.yaml:author_repo.\n"
            if configured is not None
            else "Set gru.yaml:author_repo if the source you want to seed from "
            "lives somewhere other than the directory containing MinionsOS.\n"
        )
        raise ProjectError(
            f"The author seed repo ({src}) is not a git repository. "
            "MinionsOS imports the author's HEAD into each per-project "
            "bare repo at project_create time, so the source must be "
            "git-initialized.\n"
            "Fix with:\n"
            f"    cd {src} && git init && git add -A && git commit -m 'init'\n"
            f"{config_hint}"
        )
    return src


def _seed_per_project_repo(port: int) -> tuple[str, str]:
    """Create the per-project bare repo and seed an initial commit.

    Steps:
    1. ``git init --bare project_{port}/parent_repo.git``.
    2. Build a temp work tree under ``state/.seed-staging-{port}/``.
    3. Resolve the author's HEAD SHA (recorded in meta).
    4. ``git -C author_repo archive HEAD | tar -x`` into the staging tree
       (``git archive`` already excludes ``.git/`` and respects export-ignore
       attributes; we then post-filter to drop the embedded MinionsOS
       directory and any file > 500 MB).
    5. ``git init`` inside the staging tree, add+commit, then push the
       resulting commit into the bare repo as ``minionsos/project-{port}``.

    Returns ``(seed_commit_sha, author_head_sha)``.
    """
    src = _ensure_author_repo_is_git_repo()
    bare = project_parent_repo(port)
    if bare.exists():
        raise ProjectError(
            f"Per-project bare repo already exists for port {port}: {bare}. "
            "project_create should not be called against an existing project tree."
        )

    bare.parent.mkdir(parents=True, exist_ok=True)
    init_bare = subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        capture_output=True,
        text=True,
    )
    if init_bare.returncode != 0:
        raise ProjectError(f"git init --bare failed for port {port}: {init_bare.stderr.strip()}")

    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(src),
        capture_output=True,
        text=True,
    )
    if head_proc.returncode != 0:
        raise ProjectError(f"Could not read author HEAD from {src}: {head_proc.stderr.strip()}")
    author_sha = head_proc.stdout.strip()

    staging = project_state_dir(port) / f".seed-staging-{port}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    archive_proc = subprocess.Popen(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=str(src),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    untar_proc = subprocess.Popen(
        ["tar", "-x", "-C", str(staging)],
        stdin=archive_proc.stdout,
        stderr=subprocess.PIPE,
    )
    if archive_proc.stdout is not None:
        archive_proc.stdout.close()
    untar_err = untar_proc.communicate()[1]
    archive_err = archive_proc.communicate()[1]
    if archive_proc.returncode != 0 or untar_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git archive | tar failed when seeding port {port}: "
            f"archive={archive_err!r} tar={untar_err!r}"
        )

    _seed_postfilter_tree(staging)

    init_proc = subprocess.run(
        ["git", "init", "-q", "-b", f"minionsos/project-{port}"],
        cwd=str(staging),
        capture_output=True,
        text=True,
    )
    if init_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git init in seed staging failed for port {port}: {init_proc.stderr.strip()}"
        )
    # Use a stable identity for the seed commit so projects on hosts without
    # global git config still seed cleanly.
    seed_env = {
        "GIT_AUTHOR_NAME": "MinionsOS",
        "GIT_AUTHOR_EMAIL": "minionsos@localhost",
        "GIT_COMMITTER_NAME": "MinionsOS",
        "GIT_COMMITTER_EMAIL": "minionsos@localhost",
        **os.environ,
    }
    add_proc = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(staging),
        capture_output=True,
        text=True,
        env=seed_env,
    )
    if add_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git add in seed staging failed for port {port}: {add_proc.stderr.strip()}"
        )
    msg = f"seed: import author HEAD {author_sha[:12]} (port {port})"
    commit_proc = subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", msg],
        cwd=str(staging),
        capture_output=True,
        text=True,
        env=seed_env,
    )
    if commit_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"git commit in seed staging failed for port {port}: {commit_proc.stderr.strip()}"
        )
    seed_sha_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(staging),
        capture_output=True,
        text=True,
    )
    seed_sha = seed_sha_proc.stdout.strip()
    push_branch = f"minionsos/project-{port}"
    push_proc = subprocess.run(
        ["git", "push", str(bare), f"HEAD:refs/heads/{push_branch}"],
        cwd=str(staging),
        capture_output=True,
        text=True,
        env=seed_env,
    )
    if push_proc.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProjectError(
            f"Could not push seed commit into per-project bare repo for port {port}: "
            f"{push_proc.stderr.strip()}"
        )
    # Set the bare repo's HEAD to the project's main branch so subsequent
    # ``git worktree add ... HEAD`` resolves cleanly.
    sym_proc = subprocess.run(
        ["git", "symbolic-ref", "HEAD", f"refs/heads/{push_branch}"],
        cwd=str(bare),
        capture_output=True,
        text=True,
    )
    if sym_proc.returncode != 0:
        logger.warning(
            "Could not set HEAD on per-project bare repo for port %d: %s",
            port,
            sym_proc.stderr.strip(),
        )
    shutil.rmtree(staging, ignore_errors=True)
    return seed_sha, author_sha


def _seed_postfilter_tree(staging: Path) -> None:
    """Drop entries that survived ``git archive`` but should not be seeded.

    - Any directory named ``MinionsOS`` / ``minionsos`` (avoid recursive seed).
    - Any regular file larger than 500 MB.

    ``.git`` is already excluded by ``git archive`` so we don't need to
    revisit it here.
    """
    for path in list(staging.rglob("*")):
        if not path.exists():
            continue  # may have been deleted by an earlier iteration
        try:
            if path.is_dir() and path.name in _SEED_SKIP_DIR_NAMES:
                shutil.rmtree(path, ignore_errors=True)
                continue
            if path.is_file():
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > _LARGE_FILE_THRESHOLD_BYTES:
                    logger.info(
                        "seed: skipping large file (%.1f MB): %s",
                        size / (1024 * 1024),
                        path.relative_to(staging),
                    )
                    path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("seed postfilter encountered %s on %s; continuing", exc, path)


def _create_worktree(port: int, base_branch: str) -> str:
    """Re-export of :func:`_project_worktree.create_worktree`."""
    return _project_worktree.create_worktree(port, base_branch)


_SHARED_SUBDIRS = _project_worktree.SHARED_SUBDIRS
_SHARED_README = _project_worktree.SHARED_README


def _create_shared_worktree(port: int) -> str:
    """Re-export of :func:`_project_worktree.create_shared_worktree`."""
    return _project_worktree.create_shared_worktree(port)


def _git_tag(port: int, tag: str) -> None:
    """Create a git tag in the per-project bare repo."""
    result = _gu_run_git(["tag", tag], project_parent_repo(port), check=False)
    if result.returncode != 0:
        logger.warning("git tag %s failed: %s", tag, result.stderr.strip())


def _git_ref_exists(repo: Path, ref: str) -> bool:
    return _project_worktree.git_ref_exists(repo, ref)


def _git_status_porcelain(workspace: Path) -> list[str]:
    """Re-export of :func:`_project_worktree.git_status_porcelain`."""
    return _project_worktree.git_status_porcelain(workspace)


def _is_git_dirty(workspace: Path) -> bool:
    return _project_worktree.is_git_dirty(workspace)


def _git_commit_workspace(workspace: Path, message: str) -> str | None:
    """Re-export of :func:`_project_worktree.git_commit_workspace`."""
    return _project_worktree.git_commit_workspace(workspace, message)


def _git_push_checkpoint(workspace: Path, target: str, remote_branch: str) -> None:
    """Re-export of :func:`_project_worktree.git_push_checkpoint`."""
    _project_worktree.git_push_checkpoint(workspace, target, remote_branch)


def _checkpoint_remote_branch(
    port: int,
    role_name: str | None,
    prefix: str | None,
) -> str:
    role_leaf = "main" if role_name in {None, "", "main"} else slugify(role_name)
    branch_prefix = (prefix or "minionsos").strip("/") or "minionsos"
    return f"{branch_prefix}/p{port}/{role_leaf}"


_SESSION_LEDGER_MAX_CHECKPOINTS = 1000


def _append_session_ledger(port: int, payload: dict[str, object]) -> None:
    path = project_session_ledger(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger: dict[str, object] = {
        "version": 1,
        "project_port": port,
        "checkpoints": [],
    }
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                ledger.update(raw)
        except Exception:
            pass
    checkpoints_obj = ledger.get("checkpoints")
    checkpoints: list[dict[str, object]] = []
    if isinstance(checkpoints_obj, list):
        for entry in checkpoints_obj:
            if isinstance(entry, dict):
                checkpoints.append(cast(dict[str, object], entry))
    checkpoints.append(payload)
    if len(checkpoints) > _SESSION_LEDGER_MAX_CHECKPOINTS:
        checkpoints = checkpoints[-_SESSION_LEDGER_MAX_CHECKPOINTS:]
    ledger["checkpoints"] = checkpoints
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _ensure_workspace_layout(port: int) -> None:
    """Create the non-worktree workspace containers for *port*."""
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_roles_workspace_dir(port).mkdir(parents=True, exist_ok=True)
    project_shared_workspace(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)


def project_checkpoint_workspace(
    port: int,
    role_name: str | None = None,
    message: str | None = None,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Commit one workspace checkpoint locally and optionally push it."""
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")

    is_main = role_name in {None, "", "main"}
    role: RoleEntry | None = None
    if is_main:
        workspace = project_main_workspace(port)
        session_name = project_session_name(port, "main")
        local_branch = entry.current_branch or project_branch_name(port)
        push_target = getattr(entry, "github_push_target", None)
        push_branch_prefix = getattr(entry, "github_push_branch_prefix", None)
    else:
        role = next((r for r in entry.active_roles if r.name == role_name), None)
        if role is None:
            raise ProjectError(f"Role {role_name!r} not found on port {port}.")
        workspace = (
            Path(role.workspace_path)
            if role.workspace_path
            else project_role_workspace(
                port,
                role.name,
            )
        )
        session_name = role.session_name or project_session_name(port, role.name)
        local_branch = role.workspace_branch or project_branch_name(port, role.name)
        push_target = role.github_push_target or getattr(entry, "github_push_target", None)
        push_branch_prefix = getattr(entry, "github_push_branch_prefix", None)

    if not workspace.exists():
        raise ProjectError(f"Workspace does not exist for checkpoint: {workspace}")
    if not _is_git_work_tree(workspace):
        raise ProjectError(f"Workspace is not a git worktree: {workspace}")

    dirty = _is_git_dirty(workspace)
    commit_message = message or f"checkpoint({session_name}): durable workspace checkpoint"
    commit_sha = _git_commit_workspace(workspace, commit_message) if dirty else None
    pushed = False
    remote_branch = None
    if commit_sha and push_target:
        remote_branch = _checkpoint_remote_branch(port, role_name, push_branch_prefix)
        _git_push_checkpoint(workspace, push_target, remote_branch)
        pushed = True

    payload = {
        "ts": _now_iso(),
        "port": port,
        "role_name": role_name or "main",
        "session_name": session_name,
        "workspace": str(workspace.resolve()),
        "local_branch": local_branch,
        "dirty": dirty,
        "commit_sha": commit_sha,
        "push_target": push_target,
        "push_branch": remote_branch,
        "pushed": pushed,
        "message": commit_message,
    }
    _append_session_ledger(port, payload)
    logger.info(
        "project_checkpoint_workspace done: port=%d role=%s dirty=%s committed=%s pushed=%s",
        port,
        role_name or "main",
        dirty,
        bool(commit_sha),
        pushed,
    )
    return payload


def _create_role_worktree(
    port: int,
    role_name: str,
    base_branch: str | None = None,
) -> tuple[str, Path]:
    """Create or verify the git worktree for one role.

    Gru resolves to the project's main worktree and main branch; this
    function treats it like any other role so the main worktree is guaranteed
    to exist before Gru is registered. Any other role gets its own branch
    ``minionsos/project-{port}-{role}`` rooted at the project main branch.
    """
    branch = project_branch_name(port, role_name)
    workspace = project_role_workspace(port, role_name)
    if workspace.exists():
        if _is_git_work_tree(workspace):
            return branch, workspace
        raise ProjectError(f"Role workspace already exists but is not a git worktree: {workspace}")

    workspace.parent.mkdir(parents=True, exist_ok=True)
    parent_repo = project_parent_repo(port)
    resolved_base = base_branch if base_branch not in {None, ""} else project_branch_name(port)
    if resolved_base != "HEAD" and not _git_ref_exists(parent_repo, resolved_base):
        logger.debug(
            "Role base branch %s missing in %s; falling back to HEAD.",
            resolved_base,
            parent_repo,
        )
        resolved_base = "HEAD"
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
    branch, workspace = _create_role_worktree(port, role_name, base_branch=base_branch)
    _seed_claude_settings(workspace)
    if role_name == "coder":
        _bootstrap_coder_graph(workspace)
    return branch, workspace


def _bootstrap_coder_graph(workspace: Path) -> None:
    """One-shot ``codegraph init -i`` over the Coder branch.

    Mechanical bootstrap so the project's codegraph MCP launcher (which
    fail-fasts on a missing index) has something to serve from the first
    Coder wake. Roles autonomously decide *when* to query the graph; the
    lifecycle decides *where* the index lives, identical to how
    ``_seed_claude_settings`` seeds hooks without consulting any LLM.

    Idempotent: skips if ``.codegraph/`` already exists. Non-fatal: a
    failed bootstrap warns and continues — the launcher's bootstrap
    instruction tells the operator how to recover, and Coder can still
    do everything else (write code, run experiments) without the graph.
    """
    if (workspace / ".codegraph").exists():
        return
    cg_bin = MINIONS_ROOT / "mcp-servers" / "codegraph" / "node_modules" / ".bin" / "codegraph"
    if not cg_bin.is_file() or not os.access(cg_bin, os.X_OK):
        logger.warning(
            "codegraph binary missing at %s; skipping Coder graph bootstrap. "
            "Run ./install.sh to populate node_modules.",
            cg_bin,
        )
        return
    logger.info("Bootstrapping Coder graph at %s (codegraph init -i)", workspace)
    result = subprocess.run(
        [str(cg_bin), "init", "-i"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        logger.warning(
            "codegraph init -i failed at %s (exit %d); Coder will see an "
            "index-missing error from the MCP launcher until the operator "
            "runs the bootstrap manually. stderr: %s",
            workspace,
            result.returncode,
            result.stderr.strip()[:500],
        )
        return
    logger.info("Coder graph bootstrapped: %s/.codegraph/", workspace)


def _seed_claude_settings(workspace: Path) -> None:
    """Ensure the role workspace has a .claude/settings.json with project hooks.

    This makes MinionsOS hooks (PreCompact, PostCompact) portable: they live
    inside the project, not in the user's global ~/.claude/settings.json.
    When someone clones MinionsOS, the hooks travel with the repo and apply
    automatically to Role agent sessions without touching global config.

    Hook commands reference MINIONS_ROOT (which role_launcher sets in the
    Role's env) so they resolve correctly regardless of install location.
    The shell expands the env var at hook execution time.
    """
    claude_dir = workspace / ".claude"
    settings_path = claude_dir / "settings.json"
    if settings_path.exists():
        return
    claude_dir.mkdir(parents=True, exist_ok=True)
    minions_root_str = str(MINIONS_ROOT)
    pre_compact_cmd = f"python3 {minions_root_str}/minions/hooks/pre_compact_science.py"
    post_compact_cmd = f"python3 {minions_root_str}/minions/hooks/post_compact_draft.py"
    settings = {
        "hooks": {
            "PreCompact": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": pre_compact_cmd,
                            "timeout": 5,
                        }
                    ]
                }
            ],
            "PostCompact": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": post_compact_cmd,
                            "timeout": 10,
                        }
                    ]
                }
            ],
        }
    }
    tmp = settings_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, settings_path)


def project_phase_allows_role(entry: ProjectEntry, role_name: str) -> bool:
    """Re-export of :func:`_project_phase.project_phase_allows_role`."""
    return _project_phase.project_phase_allows_role(entry, role_name)


def project_phase_online_role_names(entry: ProjectEntry) -> list[str]:
    """Re-export of :func:`_project_phase.project_phase_online_role_names`."""
    return _project_phase.project_phase_online_role_names(entry)


def project_phase_snapshot(entry: ProjectEntry) -> ProjectPhaseSnapshot:
    """Re-export of :func:`_project_phase.project_phase_snapshot`."""
    return _project_phase.project_phase_snapshot(entry)


def project_set_phase(
    port: int,
    phase: str | None,
    *,
    allowed_roles: list[str] | None = None,
    reason: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Re-export of :func:`_project_phase.project_set_phase`."""
    return _project_phase.project_set_phase(
        port,
        phase,
        allowed_roles=allowed_roles,
        reason=reason,
        store=store,
    )


_PROJECT_GITIGNORE = """\
# MinionsOS project workspace hygiene.
# Only structured subdirectories are tracked; stray files are ignored.
*
!.gitignore
!CLAUDE.md
!AGENTS.md
!meta.json
!branches/
!branches/**
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
    """Re-export of :func:`_project_templates.render_project_claude_md`.

    Kept here so ``from minions.lifecycle.project import _render_project_claude_md``
    keeps working for tests and external callers. See the implementation in
    :mod:`minions.lifecycle._project_templates`.
    """
    return _project_templates.render_project_claude_md(
        port=port,
        real_name=real_name,
        venue=venue,
        branch=branch,
        workspace_abs=workspace_abs,
        brief=brief,
        topic_doc=topic_doc,
        template_dir=template_dir,
    )


def _render_project_agents_md(real_name: str) -> str:
    """Re-export of :func:`_project_templates.render_project_agents_md`."""
    return _project_templates.render_project_agents_md(real_name)


def _seed_draft_bootstrap(
    port: int,
    profile_name: str,
    mission_profile: Any,
    real_name: str,
    brief: str | None,
    topic_doc: str | None,
) -> None:
    """Seed the Draft with a bootstrap node (B-000) as the project root.

    The bootstrap node serves as:
    - The cold-start trigger for Roles (they read it on first wake)
    - The L1 memory root (all subsequent nodes derive from this context)
    - A durable record of the project's initial state

    Written to ``branches/shared/draft/draft.json`` immediately after
    shared worktree creation, before any Role spawns.
    """
    from minions.paths import project_shared_draft_json

    draft_path = project_shared_draft_json(port)
    draft_path.parent.mkdir(parents=True, exist_ok=True)

    bootstrap_text = brief or f"Project: {real_name}"
    if topic_doc:
        bootstrap_text += f"\n\nTopic document: {topic_doc}"

    bootstrap_node = {
        "id": "B-000",
        "type": "bootstrap",
        "text": bootstrap_text,
        "support_status": "verified",
        "author_role": "system",
        "created_at": _now_iso(),
        "evidence_tag": "",
        "provenance": "system",
        "confidence": 1.0,
        "metadata": {
            "profile": profile_name,
            "roles_expected": list(mission_profile.roles_active),
            "deliverable": mission_profile.deliverable_schema.get("required", []),
            "topic_doc": topic_doc or "",
            "real_name": real_name,
        },
    }

    draft = {
        "project_port": port,
        "root_question": bootstrap_text,
        "nodes": [bootstrap_node],
        "edges": [],
    }

    tmp = draft_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, draft_path)
    logger.info("Seeded Draft bootstrap node B-000 for port %d", port)


def project_create(
    real_name: str,
    venue: str | None = None,
    base_branch: str = "HEAD",
    upstream: str | None = None,
    brief: str | None = None,
    topic_doc: str | None = None,
    template_dir: str | None = None,
    profile: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Create a new project, start its EACN3 backend, and register it.

    Steps:
    1. Allocate a free port.
    2. Load the mission profile (defaults to "scientific-paper").
    3. Create ``project_{port}/`` directory tree.
    4. Create git worktree on branch ``minionsos/project-{port}``.
    5. Start EACN3 backend subprocess; health-probe up to 20 s.
    6. Write ``meta.json`` with profile metadata.
    7. Register in ``projects.json``.

    Args:
        profile: Mission profile name (e.g., "scientific-paper", "hle-answer").
                 Defaults to "scientific-paper" if not specified.

    Returns the ``ProjectEntry`` for the new project.
    """
    from minions.profiles import get_default_profile, load_profile

    profile_name = profile or get_default_profile()
    mission_profile = load_profile(profile_name)

    _store = store or StateStore()
    port = _store.find_next_port()
    logger.info(
        "project_create name=%r port=%d venue=%r profile=%s",
        real_name,
        port,
        venue,
        profile_name,
    )

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
    (pdir / "eacn3_data").mkdir(parents=True, exist_ok=True)

    # Workspace hygiene: write a .gitignore to prevent unstructured files.
    _write_project_gitignore(pdir)

    # Create per-project bare repo by seeding from the author repo's HEAD,
    # then add the main worktree (Gru's branch) and the shared cross-role
    # worktree. Role worktrees are created lazily by ``register_role`` and
    # branch off the project's main branch.
    try:
        _seed_per_project_repo(port)
        branch = _create_worktree(port, base_branch)
        _create_shared_worktree(port)
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
    # Persist mission profile so revive / role launch / evaluator can read it.
    entry_dict["profile"] = profile_name
    entry_dict["profile_roles_active"] = list(mission_profile.roles_active)
    entry_dict["profile_lightweight"] = mission_profile.lightweight
    entry_dict["profile_phase_schema"] = mission_profile.phase_schema
    entry_dict["profile_on_done"] = mission_profile.on_done
    entry_dict["profile_evaluation"] = dict(mission_profile.evaluation)
    entry_dict["profile_deliverable_schema"] = dict(mission_profile.deliverable_schema)
    entry_dict["profile_role_prompt_overlay"] = dict(mission_profile.role_prompt_overlay)
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

    # Ensure branches/main/experiments/ exists so local experiment target resolves.
    try:
        (project_main_workspace(port) / "experiments").mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # non-fatal
        logger.warning("Could not create branches/main/experiments/: %s", exc)

    # Seed the Draft with a bootstrap node (B-000) as the project root.
    # This gives Roles a shared starting point and unifies cold-start with
    # the L1 memory layer. The bootstrap node contains the project brief,
    # expected roles, deliverable schema, and creation timestamp.
    try:
        _seed_draft_bootstrap(
            port=port,
            profile_name=profile_name,
            mission_profile=mission_profile,
            real_name=real_name,
            brief=brief,
            topic_doc=topic_doc,
        )
    except Exception as exc:  # non-fatal
        logger.warning("Draft bootstrap seed failed (non-fatal): %s", exc)

    # Register in projects.json.
    _store.add_project(entry)

    logger.info("project_create done: port=%d pid=%d", port, proc.pid)
    return entry


def project_dormant(
    port: int,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Transition project *port* to dormant state.

    - Kills each Role's tmux session so the long-lived ``claude`` processes
      stop polling. The Claude Code session jsonl files (under
      ``~/.claude/projects/<cwd-slug>/``) are left intact so ``project_revive``
      can later reattach with ``--resume <session_name>``.
    - Stops the EACN3 backend.
    - Marks every role ``dismissed`` in the store.
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

    # Kill long-lived Role tmux sessions BEFORE stopping the backend so the
    # resident claude processes stop sending HTTP polls into a dying server.
    from minions.lifecycle.role_launcher import kill_session as _kill_session

    for role in entry.active_roles:
        try:
            killed = _kill_session(port, role.name)
            if killed:
                logger.info(
                    "project_dormant: killed tmux session for role=%s port=%d",
                    role.name,
                    port,
                )
        except Exception as exc:
            logger.warning(
                "project_dormant: kill_session failed for role=%s port=%d: %s",
                role.name,
                port,
                exc,
            )

    # Stop backend. Read backend_pid from the on-disk meta (not from the
    # store entry — runtime-only fields live on disk).
    backend_pid: int | None = None
    try:
        raw_dict = _read_meta_raw(port)
        raw_pid = raw_dict.get("backend_pid")
        if isinstance(raw_pid, (int, str)):
            backend_pid = int(raw_pid)
    except (ProjectError, Exception):
        pass
    if _stop_backend(port, backend_pid) is False:
        raise ProjectError(f"Could not stop backend on port {port}; project left active.")

    now = _now_iso()
    ts = now.replace(":", "-").replace(".", "-")
    tag = f"minionsos/dormant/project-{port}-{ts}"
    _git_tag(port, tag)

    try:
        from minions.tools.issues import archive_issues as _archive_issues

        _archive_issues(port, closed_ts=now)
    except Exception as exc:
        logger.warning("project_dormant: issue archive failed for port=%d: %s", port, exc)

    updated = _store.update_project(
        port,
        status="dormant",
        dormant_at=now,
        active_roles=[r.model_copy(update={"state": "dismissed"}) for r in entry.active_roles],
    )
    _write_meta(port, updated)
    logger.info("project_dormant done: port=%d tag=%s", port, tag)
    return updated


def _remove_all_worktrees(port: int) -> None:
    """Remove every worktree registered against the project's bare repo.

    Branches and tags are retained — only the working directories under
    ``project_{port}/branches/`` are removed, plus the bare repo's
    ``.git/worktrees/`` registrations are pruned. Forensic recovery is
    still possible via ``git worktree add /tmp/inspect <branch>`` against
    the per-project bare repo.

    Best-effort: failures on individual worktrees are logged but do not
    abort the close operation, since by the time we get here the project
    is already being retired.
    """
    bare = project_parent_repo(port)
    if not bare.exists():
        return

    list_proc = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(bare),
        capture_output=True,
        text=True,
    )
    if list_proc.returncode != 0:
        logger.warning(
            "project_close: could not list worktrees for port %d: %s",
            port,
            list_proc.stderr.strip(),
        )
        return

    worktree_paths: list[Path] = []
    for line in list_proc.stdout.splitlines():
        if line.startswith("worktree "):
            wt = Path(line[len("worktree ") :].strip())
            # Skip the bare repo's own listing (some git versions include it).
            if wt.resolve() == bare.resolve():
                continue
            worktree_paths.append(wt)

    for wt in worktree_paths:
        rm = subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt)],
            cwd=str(bare),
            capture_output=True,
            text=True,
        )
        if rm.returncode != 0:
            logger.warning(
                "project_close: git worktree remove failed for %s: %s",
                wt,
                rm.stderr.strip(),
            )
        # If the directory still exists (force-remove couldn't clean it
        # because of permission issues, etc.), best-effort rmtree.
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)

    # Prune any stale registrations left over from removed worktrees.
    prune = subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(bare),
        capture_output=True,
        text=True,
    )
    if prune.returncode != 0:
        logger.warning(
            "project_close: git worktree prune failed for port %d: %s",
            port,
            prune.stderr.strip(),
        )


def project_close(
    port: int,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Transition project *port* to closed state.

    Same as dormant, plus:
    - Writes git tag ``minionsos/closed/project-{port}`` in the project's
      bare repo so the seed and final HEADs can be located later.
    - Removes every worktree under ``project_{port}/branches/`` so the bare
      repo's worktree list does not grow unbounded with closed projects.
      Branches themselves are retained for forensic inspection — re-attach
      with ``git worktree add /tmp/inspect <branch>`` against
      ``project_{port}/parent_repo.git/``.
    - Permanently retires the port.

    The session jsonl files left under ``~/.claude/projects/<cwd-slug>/``
    are not removed, so the closed project can be inspected forensically
    via ``claude --resume <session_name>`` from the same cwd if needed.
    """
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status == "closed":
        raise ProjectError(f"Project {port} is already closed.")

    logger.info("project_close port=%d", port)

    # If still active, kill role sessions and stop backend first.
    if entry.status == "active":
        from minions.lifecycle.role_launcher import kill_session as _kill_session

        for role in entry.active_roles:
            try:
                _kill_session(port, role.name)
            except Exception as exc:
                logger.warning(
                    "project_close: kill_session failed for role=%s port=%d: %s",
                    role.name,
                    port,
                    exc,
                )
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

    try:
        from minions.tools.issues import archive_issues as _archive_issues

        _archive_issues(port, closed_ts=now)
    except Exception as exc:
        logger.warning("project_close: issue archive failed for port=%d: %s", port, exc)

    updated = _store.update_project(
        port,
        status="closed",
        closed_at=now,
        dormant_at=entry.dormant_at or now,
        active_roles=[r.model_copy(update={"state": "dismissed"}) for r in entry.active_roles],
    )
    _write_meta(port, updated)
    _store.retire_port(port)
    _remove_all_worktrees(port)
    logger.info("project_close done: port=%d", port)
    return updated


def project_kill(
    port: int,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Hard-stop one project's runtime without deleting its EACN network data.

    This is intentionally narrower than ``project_close`` and ``wipe``:
    it stops the recorded backend and Role subprocesses, marks the project
    dormant so resident Roles stop polling it, and preserves
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
        if isinstance(raw_pid, (int, str)):
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

    # Defensive sweep: kill any surviving ``mos-{port}-*`` tmux session that
    # the recorded ``active_roles`` loop did not catch. This handles the
    # known case where roles are marked ``state="dismissed", pid=None`` in
    # meta.json (e.g. by an earlier project_dormant) yet a subsequent
    # project_revive re-launched their tmux sessions without resetting
    # state — leaving orphan tmux sessions invisible to this loop.
    swept: list[str] = []
    try:
        from minions.lifecycle.role_launcher import (
            kill_project_sessions as _kill_project_sessions,
        )

        swept = _kill_project_sessions(port)
        if swept:
            logger.info(
                "project_kill: swept orphan tmux sessions port=%d names=%s",
                port,
                swept,
            )
    except Exception as exc:
        logger.warning("project_kill: orphan tmux sweep failed for port=%d: %s", port, exc)

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
        "project_kill done: port=%d backend_pid=%s roles=%d swept=%d",
        port,
        backend_pid,
        len(role_results),
        len(swept),
    )
    return {
        "port": updated.port,
        "status": updated.status,
        "backend_pid": backend_pid,
        "roles": role_results,
        "swept_tmux_sessions": swept,
    }


def project_revive(
    port: int,
    external_feedback: str | None = None,
    feedback_source: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Revive a dormant project.

    - Re-starts the EACN3 backend on the same port.
    - Restores ``active_roles`` from ``meta.json`` and re-registers each
      project-local EACN AgentCard.
    - Re-launches each Role's long-lived ``claude`` process inside its
      tmux session as a **cold start** (no ``--resume``). Role context is
      rebuilt from durable artefacts: the Draft (L1), EACN history,
      and ``pending_plan`` nodes. We deliberately do NOT pass ``--resume``
      here because resuming a session forces Claude Code to rebuild its
      prompt cache from scratch (cache TTL is reset), which would erase
      the cache-warmth investment of the prior dormant period and re-pay
      hundreds of thousands of input tokens to replay history that is
      mostly already encoded in the Draft. Cold start + Draft
      read-back is cheaper and matches the dormant→revive semantics
      ("the project restarts; agents reconstruct from durable state").
    - If *external_feedback* is provided, archives it to
      ``branches/shared/handoffs/external-feedback/<ts>.md``.
    - Updates ``meta.json`` and ``projects.json``.
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

    # Migrate legacy directory names (v11→v12 rename).
    _migrate_legacy_memory_dirs(port)

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
        fb_dir = project_shared_subdir(port, "handoffs") / "external-feedback"
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
                    "workspace_path": restored.workspace_path or str(workspace_path.resolve()),
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

    # Re-launch each Role's long-lived claude process as a COLD START
    # (resume=False). Resuming a session would force Claude Code to rebuild
    # its prompt cache from scratch and replay a large conversation history
    # that is largely redundant with the Draft; cold start lets the
    # Role do its own pending_plans drain + Draft summary on first
    # wake. Failures here are logged but not fatal — the role state is
    # already restored, and the operator can re-run mos role spawn /
    # mos project repair to recover.
    try:
        from minions.lifecycle.role_launcher import (
            kill_project_sessions as _kill_project_sessions,
        )
        from minions.lifecycle.role_launcher import launch_role_process as _launch_role
    except Exception as exc:
        logger.warning(
            "project_revive: role_launcher unavailable (port=%d): %s; "
            "Role processes were not relaunched.",
            port,
            exc,
        )
    else:
        # Defensive: kill any pre-existing ``mos-{port}-*`` tmux session
        # before relaunching. ``launch_role_process`` is idempotent in the
        # "session already alive" sense, so a stale tmux from a prior
        # botched lifecycle would be silently re-attached, hiding the
        # fact that the Claude process inside is stuck or dead.
        try:
            stale = _kill_project_sessions(port)
            if stale:
                logger.info(
                    "project_revive: cleaned stale tmux sessions port=%d names=%s",
                    port,
                    stale,
                )
        except Exception as exc:
            logger.warning(
                "project_revive: stale tmux sweep failed for port=%d: %s",
                port,
                exc,
            )

        relaunched: list[RoleEntry] = []
        for role in revived_roles:
            try:
                status = _launch_role(role, port, resume=False)
                logger.info(
                    "project_revive: relaunched role=%s port=%d session=%s started=%s",
                    role.name,
                    port,
                    status.get("session_name"),
                    status.get("started"),
                )
                relaunched.append(role.model_copy(update={"state": "sleeping"}))
            except Exception as exc:
                logger.warning(
                    "project_revive: launch_role_process failed for role=%s port=%d: %s",
                    role.name,
                    port,
                    exc,
                )
                relaunched.append(role)
        revived_roles = relaunched

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
            role_workspace_updates["github_push_target"] = getattr(
                refreshed_entry, "github_push_target", None
            ) or raw.get("github_push_target")
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
