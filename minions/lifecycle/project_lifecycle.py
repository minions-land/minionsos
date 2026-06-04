"""Project lifecycle management: dormant, close, revive, kill, repair.

Handles state transitions and recovery operations for MinionsOS projects.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.config import is_expert_role
from minions.errors import BackendError, ProjectError
from minions.lifecycle.eacn_identity import identity_map_for_meta
from minions.lifecycle.project_backend import (
    adopt_running_backend,
    register_gru_eacn_agent,
    register_server,
    start_backend,
    stop_backend,
    wait_for_health,
)
from minions.lifecycle.project_metadata import (
    read_meta_raw,
    role_entries_from_meta,
    write_meta,
)
from minions.lifecycle.project_paths import git_tag, migrate_legacy_memory_dirs
from minions.lifecycle.project_worktree import remove_all_worktrees
from minions.paths import (
    project_main_workspace,
    project_meta_json,
    project_session_name,
    project_shared_subdir,
)
from minions.state.store import ProjectEntry, RoleEntry, StateStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def project_dormant(
    port: int,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Transition project *port* to dormant state.

    - Kills each Role's tmux session so the long-lived claude processes
      stop polling. The Claude Code session jsonl files (under
      ~/.claude/projects/<cwd-slug>/) are left intact so project_revive
      can later reattach with --resume <session_name>.
    - Stops the EACN3 backend.
    - Marks every role dismissed in the store.
    - Writes a git tag minionsos/dormant/project-{port}-<ts>.
    - Updates meta.json and projects.json.
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
        raw_dict = read_meta_raw(port)
        raw_pid = raw_dict.get("backend_pid")
        if isinstance(raw_pid, (int, str)):
            backend_pid = int(raw_pid)
    except (ProjectError, Exception):
        pass
    if stop_backend(port, backend_pid) is False:
        raise ProjectError(f"Could not stop backend on port {port}; project left active.")

    now = _now_iso()
    ts = now.replace(":", "-").replace(".", "-")
    tag = f"minionsos/dormant/project-{port}-{ts}"
    git_tag(port, tag)

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
    write_meta(port, updated)
    logger.info("project_dormant done: port=%d tag=%s", port, tag)
    return updated


def project_close(
    port: int,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Transition project *port* to closed state.

    Same as dormant, plus:
    - Writes git tag minionsos/closed/project-{port} in the project's
      bare repo so the seed and final HEADs can be located later.
    - Removes every worktree under project_{port}/branches/ so the bare
      repo's worktree list does not grow unbounded with closed projects.
      Branches themselves are retained for forensic inspection — re-attach
      with git worktree add /tmp/inspect <branch> against
      project_{port}/parent_repo.git/.
    - Permanently retires the port.
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
        if stop_backend(port, backend_pid) is False:
            raise ProjectError(
                f"Could not stop backend on port {port}; project left {entry.status}."
            )

    now = _now_iso()
    ts = now.replace(":", "-").replace(".", "-")
    dormant_tag = f"minionsos/dormant/project-{port}-{ts}"
    closed_tag = f"minionsos/closed/project-{port}"
    if entry.status == "active":
        git_tag(port, dormant_tag)
    git_tag(port, closed_tag)

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
    write_meta(port, updated)
    _store.retire_port(port)
    remove_all_worktrees(port)
    try:
        from minions.lifecycle.role_hermetic import cleanup_hermetic_cwd as _cleanup_hermetic

        removed = _cleanup_hermetic(port)
        if removed:
            logger.info("project_close: cleaned %d hermetic cwd path(s)", len(removed))
    except Exception as exc:
        logger.warning("project_close: hermetic cleanup failed for port=%d: %s", port, exc)
    logger.info("project_close done: port=%d", port)
    return updated


def project_kill(
    port: int,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Hard-stop one project's runtime without deleting its EACN network data."""
    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status == "closed":
        raise ProjectError(f"Project {port} is already closed.")

    logger.info("project_kill port=%d", port)

    backend_pid: int | None = None
    try:
        raw_dict = read_meta_raw(port)
        raw_pid = raw_dict.get("backend_pid")
        if isinstance(raw_pid, (int, str)):
            backend_pid = int(raw_pid)
    except Exception as exc:
        logger.debug("project_kill: backend_pid unavailable port=%d: %s", port, exc)
    if stop_backend(port, backend_pid) is False:
        raise ProjectError(f"Could not stop backend on port {port}; project left {entry.status}.")

    from minions.lifecycle.project_backend import pid_alive

    def _stop_role_process(role_name: str, pid: int | None) -> str:
        if pid is None:
            return "no_pid"
        try:
            import signal
            import time

            if not pid_alive(pid):
                return "already_gone"

            pgid: int | None = None
            try:
                pgid = os.getpgid(pid)
            except ProcessLookupError:
                return "already_gone"
            except Exception as exc:
                logger.debug("project_kill: could not read pgid: %s", exc)

            use_group = bool(pgid and pgid > 0 and pgid != os.getpgrp())

            def _send(sig: int) -> None:
                if use_group and pgid is not None:
                    os.killpg(pgid, sig)
                else:
                    os.kill(pid, sig)

            _send(signal.SIGTERM)
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if not pid_alive(pid):
                    logger.info("Stopped role PID=%d (role=%s port=%d).", pid, role_name, port)
                    return "terminated"
                time.sleep(0.1)

            _send(signal.SIGKILL)
            logger.info("Killed role PID=%d (role=%s port=%d).", pid, role_name, port)
            return "killed"
        except ProcessLookupError:
            return "already_gone"
        except Exception as exc:
            logger.warning("Error stopping role PID=%d: %s", pid, exc)
            return f"error:{exc}"

    role_results: list[dict[str, object]] = []
    for role in entry.active_roles:
        if role.pid is None:
            continue
        status = _stop_role_process(role.name, role.pid)
        role_results.append({"name": role.name, "pid": role.pid, "status": status})

    swept: list[str] = []
    try:
        from minions.lifecycle.role_launcher import kill_project_sessions as _kill_project_sessions

        swept = _kill_project_sessions(port)
        if swept:
            logger.info("project_kill: swept orphan tmux sessions port=%d names=%s", port, swept)
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
    write_meta(port, updated, extras={"backend_pid": None})
    logger.info("project_kill done: port=%d", port)
    return {
        "port": updated.port,
        "status": updated.status,
        "backend_pid": backend_pid,
        "roles": role_results,
        "swept_tmux_sessions": swept,
    }


def normalise_revived_role(role: RoleEntry) -> RoleEntry:
    """Return a schedulable sleeping role."""
    return role.model_copy(
        update={
            "state": "sleeping",
            "pid": None,
            "time_trigger_interval": role.time_trigger_interval,
        }
    )


def roles_for_revive(entry: ProjectEntry, raw_meta: dict[str, object]) -> list[RoleEntry]:
    """Choose role records for revive."""
    from minions.lifecycle.role import FIXED_ROLES

    roles: list[RoleEntry] = []
    for role in entry.active_roles:
        if role.name not in FIXED_ROLES and not is_expert_role(role.name):
            logger.warning(
                "Skipping malformed role name %r from projects.json: "
                "not in FIXED_ROLES and not a valid expert role shape",
                role.name,
            )
            continue
        roles.append(role)
    if not roles:
        roles = role_entries_from_meta(raw_meta)
    return [normalise_revived_role(role) for role in roles]


def project_revive(
    port: int,
    external_feedback: str | None = None,
    feedback_source: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Revive a dormant project."""
    from minions.lifecycle.project_worktree import create_role_worktree, seed_claude_settings

    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise ProjectError(f"Project {port} not found.")
    if entry.status != "dormant":
        raise ProjectError(f"project_revive requires dormant status; got {entry.status!r}.")

    logger.info("project_revive port=%d", port)
    raw_meta = read_meta_raw(port)

    try:
        proc = start_backend(port)
    except BackendError:
        adopted = adopt_running_backend(port)
        if adopted is None:
            raise
        proc = adopted
    else:
        try:
            wait_for_health(port)
        except BackendError:
            proc.terminate()
            raise

    migrate_legacy_memory_dirs(port)

    try:
        server_id, eacn3_server_token = register_server(port)
    except BackendError as exc:
        logger.error("Server re-registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    try:
        gru_agent_id, gru_agent_token = register_gru_eacn_agent(port, server_id)
    except BackendError as exc:
        logger.error("Gru agent re-registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    now = _now_iso()

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

    revived_roles: list[RoleEntry] = []
    try:
        from minions.lifecycle.agent_registry import register_project_role_agent

        for restored in roles_for_revive(entry, raw_meta):
            workspace_branch, workspace_path = create_role_worktree(
                port,
                restored.name,
                base_branch=entry.current_branch or None,
            )
            seed_claude_settings(workspace_path)
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

    try:
        from minions.lifecycle.role_launcher import (
            kill_project_sessions as _kill_project_sessions,
        )
        from minions.lifecycle.role_launcher import launch_role_process as _launch_role
    except Exception as exc:
        logger.warning("project_revive: role_launcher unavailable: %s", exc)
    else:
        try:
            stale = _kill_project_sessions(port)
            if stale:
                logger.info("project_revive: cleaned stale tmux sessions port=%d", port)
        except Exception as exc:
            logger.warning("project_revive: stale tmux sweep failed: %s", exc)

        relaunched: list[RoleEntry] = []
        for role in revived_roles:
            try:
                status = _launch_role(role, port, resume=False)
                logger.info("project_revive: relaunched role=%s port=%d", role.name, port)
                relaunched.append(role.model_copy(update={"state": "sleeping"}))
            except Exception as exc:
                logger.warning("project_revive: launch failed for role=%s: %s", role.name, exc)
                relaunched.append(role)
        revived_roles = relaunched

    updated = _store.update_project(
        port,
        status="active",
        dormant_at=None,
        active_roles=revived_roles,
    )

    write_meta(
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


# END_OF_FILE
