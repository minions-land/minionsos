"""Restart primitives for live MinionsOS processes.

Why this module exists
----------------------
``mos upgrade`` (git pull + ./install.sh) lands new code and prompts on disk
but does NOT refresh anything already running. A live Role froze its
``SYSTEM.md`` (``--append-system-prompt``), its tool whitelist, and its
minionsos MCP stdio child (which carries server-side authz) at launch; the Gru
monitor snapshotted ``gru.yaml`` once in ``GruLoop.__init__``. CPython does not
re-read source mid-process, so the only way to apply an upgrade to a running
fleet is to restart the processes.

This module provides the restart primitives that ``mos restart`` drives:

- :func:`restart_role` / :func:`restart_project_roles` — cold-restart Role
  tmux sessions using the same ``kill_session`` + ``launch_role_process``
  primitives the crash watchdog uses. Cold start (``resume=False``) is
  deliberate: Roles reconstruct context from the Draft (L1), which is cheaper
  than ``--resume`` (a prompt-cache reset costing hundreds of K tokens) and
  matches the dormant→revive semantics. The freshly launched process reads the
  new SYSTEM.md / whitelist / MCP config off disk.
- :func:`restart_gru_monitor` — kill the launcher-managed Gru monitor sidecar
  and respawn it detached, so it re-reads ``gru.yaml`` and reloads
  ``minions.gru.loop`` bytecode.

None of these touch project data, EACN DBs, worktrees, or the Draft — they only
recycle the OS processes so on-disk code/prompts take effect.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time

from minions.paths import MINIONS_ROOT, STATE_DIR
from minions.state.store import StateStore

logger = logging.getLogger(__name__)


def restart_role(
    port: int,
    role_name: str,
    *,
    only_if_alive: bool = False,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Cold-restart a single Role's tmux session so it reloads on-disk code.

    Kills the existing ``mos-{port}-{role}`` session (if any) and relaunches
    the Role from its registry entry with ``resume=False``. The new process
    reads the current SYSTEM.md, tool whitelist, and MCP config from disk and
    reconstructs working context from the Draft.

    When *only_if_alive* is True, a role with no live tmux session is left
    untouched (returns ``started=False, skipped="not running"``) instead of
    being launched. Project- and fleet-wide restarts pass this so they only
    recycle processes that are actually running — a not-running role will pick
    up new code when the watchdog or ``project_revive`` next starts it, and we
    must not mass-spawn into stale ``active`` registry entries.

    Returns a status dict: ``{role, killed, started, session_name}`` (plus
    ``skipped`` when the role was not running and *only_if_alive* was set).
    Raises ``RoleError`` if the project/role is unknown or the role is
    dismissed.
    """
    from minions.errors import RoleError
    from minions.lifecycle.role_launcher import (
        kill_session,
        launch_role_process,
        session_alive,
    )

    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise RoleError(f"Project {port} not found.")

    role_entry = next((r for r in entry.active_roles if r.name == role_name), None)
    if role_entry is None:
        raise RoleError(
            f"Role {role_name!r} not registered for project {port}. See `mos role list {port}`."
        )
    if role_entry.state == "dismissed":
        raise RoleError(
            f"Role {role_name!r} on project {port} is dismissed; refusing to restart. "
            f"Re-spawn it through Gru instead."
        )

    alive = session_alive(port, role_name)
    if only_if_alive and not alive:
        logger.info(
            "restart_role: port=%d role=%s not running; skipped (only_if_alive)",
            port,
            role_name,
        )
        return {
            "role": role_name,
            "killed": False,
            "started": False,
            "skipped": "not running",
            "session_name": None,
        }

    killed = kill_session(port, role_name)
    # Brief settle so tmux fully releases the session name before relaunch.
    if killed:
        time.sleep(0.3)
    status = launch_role_process(role_entry, port, resume=False)
    logger.info(
        "restart_role: port=%d role=%s killed=%s started=%s",
        port,
        role_name,
        killed,
        status.get("started"),
    )
    return {
        "role": role_name,
        "killed": killed,
        "started": bool(status.get("started")),
        "session_name": status.get("session_name"),
    }


def restart_project_roles(
    port: int,
    *,
    roles: list[str] | None = None,
    only_if_alive: bool = True,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Cold-restart a project's running Roles so they reload on-disk code.

    By default (*only_if_alive* True) only roles with a live tmux session are
    recycled — this is what makes a fleet-wide ``mos restart --all`` safe
    against the many stale ``active`` registry entries that accumulate over a
    host's lifetime: a not-running role is reported under ``skipped`` and never
    launched. Dismissed/sleeping roles are always skipped.

    Each role is recycled independently, so one failure does not abort the
    rest. Returns ``{port, restarted: [...], skipped: [...], failed: [...]}``.
    """
    from minions.errors import RoleError

    _store = store or StateStore()
    entry = _store.get_project(port)
    if entry is None:
        raise RoleError(f"Project {port} not found.")

    targets = [r for r in entry.active_roles if r.state == "active"]
    if roles is not None:
        want = set(roles)
        targets = [r for r in targets if r.name in want]

    restarted: list[dict[str, object]] = []
    skipped: list[str] = [
        f"{r.name} ({r.state})" for r in entry.active_roles if r.state != "active"
    ]
    failed: list[dict[str, str]] = []
    for r in targets:
        try:
            res = restart_role(port, r.name, only_if_alive=only_if_alive, store=_store)
            if res.get("skipped"):
                skipped.append(f"{r.name} (not running)")
            else:
                restarted.append(res)
        except Exception as exc:  # one role's failure must not abort the rest
            logger.warning("restart_project_roles: role=%s failed: %s", r.name, exc)
            failed.append({"role": r.name, "error": str(exc)})
    return {
        "port": port,
        "restarted": restarted,
        "skipped": skipped,
        "failed": failed,
    }


def gru_monitor_status() -> dict[str, object]:
    """Return ``{running, pid, host}`` for the launcher-managed Gru monitor.

    ``running`` is True only when ``gru-monitor.pid`` names a live process.
    """
    pid_file = STATE_DIR / "gru-monitor.pid"
    host_file = STATE_DIR / "gru-monitor.host"
    pid: int | None = None
    running = False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        running = True
    except (OSError, ValueError):
        running = False
    host = ""
    try:
        host = host_file.read_text(encoding="utf-8").strip()
    except OSError:
        host = ""
    return {"running": running, "pid": pid, "host": host}


def restart_gru_monitor(*, timeout: float = 5.0) -> dict[str, object]:
    """Kill and respawn the Gru monitor / Role tmux watchdog sidecar.

    The monitor snapshots ``gru.yaml`` and its thresholds once at construction
    and runs ``minions.gru.loop`` bytecode loaded at start, so an upgrade only
    reaches it via a process restart. This mirrors ``ensure_gru_monitor`` in
    ``minions/bin/gru``: kill the recorded PID (TERM, then KILL after
    *timeout*), then relaunch detached with the same ``python -m
    minions.gru.loop`` invocation, refreshing the pid/host stamp files.

    Returns ``{killed_pid, new_pid, host}``.
    """
    pid_file = STATE_DIR / "gru-monitor.pid"
    host_file = STATE_DIR / "gru-monitor.host"
    log_file = STATE_DIR / "logs" / "gru-monitor.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    prior = gru_monitor_status()
    killed_pid: int | None = None
    if prior["running"] and isinstance(prior["pid"], int):
        old_pid = prior["pid"]
        try:
            os.kill(old_pid, 15)  # SIGTERM
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    os.kill(old_pid, 0)
                except OSError:
                    break
                time.sleep(0.2)
            else:
                os.kill(old_pid, 9)  # SIGKILL last resort
            killed_pid = old_pid
        except OSError as exc:
            logger.warning("restart_gru_monitor: kill of pid=%s failed: %s", old_pid, exc)

    host = os.environ.get("MINIONS_AGENT_HOST", "claude").strip() or "claude"
    # Detach into its own session so it survives the parent shell, matching
    # bin/gru's nohup+setsid pattern. uv runs it against the repo project.
    argv = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "python",
        "-m",
        "minions.gru.loop",
    ]
    with open(log_file, "a", encoding="utf-8") as logfh:
        proc = subprocess.Popen(
            argv,
            cwd=str(MINIONS_ROOT),
            stdout=logfh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "MINIONS_AGENT_HOST": host},
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    host_file.write_text(host, encoding="utf-8")
    logger.info(
        "restart_gru_monitor: killed=%s new_pid=%d host=%s",
        killed_pid,
        proc.pid,
        host,
    )
    return {"killed_pid": killed_pid, "new_pid": proc.pid, "host": host}


def list_active_projects(store: StateStore | None = None) -> list[int]:
    """Return ports of all projects in status ``active``."""
    _store = store or StateStore()
    return [p.port for p in _store.list_projects(filter="active")]
