"""Role lifecycle: register, wake, dismiss, list.

Current V5 transition model:

- ``register_role`` / ``register_expert`` register a project-local EACN3
  AgentCard, prepare the Role's workspace, and record a named host session in
  ``projects.json``. No agent-host subprocess is launched at registration time.
- ``invoke_role_ephemeral`` is retained as a compatibility name, but wake-ups
  now run in the Role's canonical workspace and keep host session persistence
  enabled so later wake-ups can resume the same logical Claude/Codex session.
- ``dismiss_role`` / ``list_roles`` operate on the registry.

The public ``spawn_role`` / ``spawn_expert`` names are retained as
backwards-compatible aliases for ``register_role`` / ``register_expert`` so
existing MCP tool callers and tests keep working.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from minions.config import (
    ROLE_CLASSIFICATION,
    ROLE_WRITE_BOUNDARIES,
    RoleType,
    load_gru_config,
    parse_duration,
    slugify,
    whitelist_csv,
)
from minions.errors import AlreadyActive, BackendError, RoleError
from minions.lifecycle import eacn_client
from minions.lifecycle.agent_host import build_role_invocation
from minions.lifecycle.agent_registry import register_project_role_agent, role_agent_domains
from minions.lifecycle.eacn_identity import plugin_state_dir, resolve_agent_id
from minions.lifecycle.project import ensure_role_workspace
from minions.lifecycle.skills import list_skills
from minions.lifecycle.wake_signals import (
    direct_message_signal,
    is_wake_signal,
    summarize_signal,
    task_signal,
)
from minions.paths import (
    MINIONS_ROOT,
    common_role_system_md,
    project_branch_name,
    project_memory_dir,
    project_role_log,
    project_role_workspace,
    project_scratchpad,
    project_session_name,
    project_workspace,
    project_workspace_root,
    role_system_md,
)
from minions.state.store import RoleEntry, StateStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXED_ROLES = {"noter", "coder", "experimenter", "writer", "reviewer", "ethics"}

# ---------------------------------------------------------------------------
# In-flight tracking / reaper
# ---------------------------------------------------------------------------

# (port, role) -> (Popen, log_fp). Guarded by _INFLIGHT_LOCK.
_INFLIGHT: dict[tuple[int, str], tuple[subprocess.Popen[bytes], IO[Any]]] = {}
_STARTING: set[tuple[int, str]] = set()
_INFLIGHT_LOCK = threading.Lock()
_CODEX_STARTUP_FAILURE_GRACE_SECONDS = 1.0


def _clear_persisted_pid_if_matches(
    store: StateStore,
    port: int,
    role_name: str,
    pid: int,
) -> None:
    """Clear a role PID only when it still points at the expected process."""
    entry = store.get_project(port)
    if entry is None:
        return
    role = next((r for r in entry.active_roles if r.name == role_name), None)
    if role is None or role.state not in {"active", "sleeping"}:
        return
    if role.pid != pid:
        return
    store.upsert_role(port, role.model_copy(update={"state": "sleeping", "pid": None}))


def _terminate_spawned_proc(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort cleanup for a subprocess that failed during launch handoff."""
    if proc.poll() is not None:
        return
    with contextlib.suppress(Exception):
        proc.terminate()
    with contextlib.suppress(Exception):
        proc.wait(timeout=2)
    if proc.poll() is None:
        with contextlib.suppress(Exception):
            proc.kill()
        with contextlib.suppress(Exception):
            proc.wait(timeout=2)


def is_inflight(project_port: int, role_name: str) -> bool:
    """Return True if an ephemeral subprocess for (port, role) is still running.

    Opportunistically reaps any exited processes before answering.
    """
    reap_finished()
    with _INFLIGHT_LOCK:
        key = (project_port, role_name)
        return key in _INFLIGHT or key in _STARTING


def reap_finished(store: StateStore | None = None) -> list[tuple[int, str, int]]:
    """Reap any exited in-flight ephemeral subprocesses.

    Closes their log file handles, clears PID from the registry, and records
    the exit status. Returns a list of ``(port, role, returncode)`` tuples
    for the processes that were reaped in this call.
    """
    reaped: list[tuple[int, str, int]] = []
    reaped_details: list[tuple[int, str, int, int]] = []
    with _INFLIGHT_LOCK:
        keys = list(_INFLIGHT.keys())
        for key in keys:
            proc, log_fp = _INFLIGHT[key]
            rc = proc.poll()
            if rc is None:
                continue
            pid = proc.pid
            with contextlib.suppress(Exception):
                log_fp.close()
            del _INFLIGHT[key]
            reaped.append((key[0], key[1], rc))
            reaped_details.append((key[0], key[1], pid, rc))

    if reaped:
        _store = store or StateStore()
        for port, role_name, pid, _rc in reaped_details:
            try:
                entry = _store.get_project(port)
                if entry is None:
                    continue
                # A finished ephemeral process leaves the registered Role
                # schedulable but idle. Clear pid so liveness checks do not
                # misfire on a reused PID. Match the exact PID so a stale
                # reaper cannot clear a newer invocation's state.
                _clear_persisted_pid_if_matches(_store, port, role_name, pid)
            except Exception as exc:
                logger.debug("reap: clear pid failed port=%d role=%r: %s", port, role_name, exc)
    return reaped


def _tail_log(path: Path, lines: int = 20) -> str:
    """Return a short best-effort tail for failure diagnostics."""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def _wait_for_immediate_exit(proc: subprocess.Popen[bytes], timeout: float) -> int | None:
    """Return rc if the process exits within timeout, else None."""
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    return rc if isinstance(rc, int) else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _build_system_prompt(role: str) -> Path | None:
    role_path = role_system_md(role if not role.startswith("expert") else "expert")
    common_path = common_role_system_md()
    paths = [path for path in (common_path, role_path) if path.exists()]
    if not paths:
        logger.debug("SYSTEM.md not found for role %r at %s", role, role_path)
        return None
    if paths == [role_path]:
        return role_path

    parts: list[str] = []
    for path in paths:
        label = "Common Role System" if path == common_path else f"{role} Role System"
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.debug("SYSTEM.md read failed for role %r at %s: %s", role, path, exc)
            continue
        parts.append(f"# {label}\n\n{text.strip()}\n")
    if not parts:
        return None

    combined = "\n\n---\n\n".join(parts) + "\n"
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
    safe_role = role.replace("/", "_").replace("..", "_")
    out_dir = Path(tempfile.gettempdir()) / "minionsos-role-prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_role}-{digest}.md"
    if not out_path.exists() or out_path.read_text(encoding="utf-8") != combined:
        out_path.write_text(combined, encoding="utf-8")
    return out_path


def _resolve_poll_interval(poll_interval: str | None) -> str:
    if poll_interval is None:
        poll_interval = os.environ.get("MINIONS_POLL_INTERVAL")
    if poll_interval is None:
        try:
            from minions.config import load_gru_config

            poll_interval = load_gru_config().poll_interval_default
        except Exception:
            poll_interval = "1m"
    if poll_interval not in {"1m", "3m", "5m"}:
        raise RoleError(f"Invalid poll_interval {poll_interval!r}; allowed values: 1m / 3m / 5m.")
    return poll_interval


def _resolve_time_trigger_interval(role_name: str, interval: str | None) -> str | None:
    """Resolve optional periodic wakeups for a role.

    Noter gets a default timer because status summaries are part of its core
    contract. Other roles remain event-driven unless explicitly configured.
    """
    if interval is None and role_name == "noter":
        try:
            interval = load_gru_config().noter_report_interval
        except Exception:
            interval = "30m"
    if not interval:
        return None
    try:
        seconds = parse_duration(interval)
    except Exception as exc:
        raise RoleError(f"Invalid time_trigger_interval {interval!r}: {exc}") from exc
    if seconds <= 0:
        return None
    return interval


_BOUNDARY_TEXT: dict[str, str] = {
    "gru": (
        "[Role boundary: human-side agent]\n"
        "You receive and interpret human instructions, recommend workflow options, "
        "drive project progress, dispatch tasks through EACN3, and inspect health/status. "
        "You do NOT implement code, run experiments, write final paper text, or "
        "participate in Review.\n"
        "Write boundaries: workspace/, artifacts/, memory/.\n"
    ),
    "noter": (
        "[Role boundary: human-side agent]\n"
        "You provide staged reports so humans can observe the system: periodic summaries, "
        "pending tasks, risks, evidence chains, artifact indexes, concise status. "
        "You reduce Gru context pressure rather than add to it.\n"
        "Write boundaries: artifacts/notes/, memory/ only. Do NOT write to workspace/.\n"
    ),
    "coder": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Delegate complex execution to subagents; summarize and write back results.\n"
        "Write boundaries: workspace/, memory/ by default. Conditional "
        "system-maintenance boundary: MinionsOS repository runtime code only when "
        "Gru or the author explicitly assigns that implementation work through EACN "
        "and names the scope, allowed paths, and verification target.\n"
    ),
    "experimenter": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Delegate complex execution to subagents; summarize and write back results.\n"
        "Write boundaries: workspace/, artifacts/, memory/.\n"
    ),
    "writer": (
        "[Role boundary: EACN-visible agent]\n"
        "Do NOT invent claims. Output must be based on available evidence, expert feedback, "
        "experiment results, and competitor positioning. "
        "Claims must be supported by evidence, experiment, derivation, citation, "
        "or explicit speculation markers.\n"
        "Write boundaries: workspace/, memory/.\n"
    ),
    "reviewer": (
        "[Role boundary: EACN-visible agent — ISOLATED]\n"
        "You see ONLY the paper PDF and submitted/open-source-ready repository code. "
        "You must NOT access internal experiment artifacts, evidence/claim maps, "
        "Ethics reports, Noter reports, internal discussions, known limitations files, "
        "or unresolved risk lists unless they are visible in the submitted PDF or repository. "
        "Each review round produces at least three independent opinions. "
        "Gru does not participate in Review.\n"
        "Write boundaries: artifacts/reviews/ only. Do NOT write to workspace/.\n"
    ),
    "ethics": (
        "[Role boundary: EACN-visible agent — continuous evidence validation]\n"
        "You continuously check whether agent behavior, communication, theory, code, "
        "and claims have real evidence support. You MAY inspect internal materials: "
        "experiment artifacts, evidence/claim maps, appendix plans, known limitations, "
        "unresolved risks, agent communications, and all claim types.\n"
        "Write boundaries: artifacts/ethics/ only. Do NOT write to workspace/.\n"
    ),
    "expert": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Preferably read-mostly; write to workspace/ and memory/ only when necessary.\n"
        "Write boundaries: workspace/ (sparingly), memory/.\n"
    ),
}


def _boundary_context(role_name: str, project_port: int) -> str:
    """Return boundary enforcement text for injection into the role prompt."""
    normalised = "expert" if role_name.startswith("expert") else role_name
    if normalised in _BOUNDARY_TEXT:
        return _BOUNDARY_TEXT[normalised]
    role_type = ROLE_CLASSIFICATION.get(normalised, RoleType.eacn_visible)
    label = "human-side" if role_type == RoleType.human_side else "EACN-visible"
    dirs = ROLE_WRITE_BOUNDARIES.get(normalised, ["memory/"])
    return f"[Role boundary: {label} agent]\nWrite boundaries: {', '.join(dirs)}.\n"


def register_role(
    project_port: int,
    role: str,
    init_brief: str | None = None,
    store: StateStore | None = None,
    poll_interval: str | None = None,
    time_trigger_interval: str | None = None,
) -> dict[str, object]:
    """Register a fixed role for event-driven invocation.

    Does NOT launch an agent-host subprocess. Registration prepares the EACN
    identity, canonical workspace, and stable host session name for later wakes.

    If *init_brief* is given, it is published as a targeted EACN task so the
    role's first action uses the same bus as every later handoff.
    """
    if role not in FIXED_ROLES:
        raise RoleError(
            f"register_role only handles fixed roles {FIXED_ROLES}; "
            "use register_expert for experts."
        )
    return _do_register(
        project_port=project_port,
        role_name=role,
        init_brief=init_brief,
        store=store or StateStore(),
        poll_interval=poll_interval,
        time_trigger_interval=time_trigger_interval,
    )


def register_expert(
    project_port: int,
    domain: str,
    name: str | None = None,
    init_brief: str | None = None,
    store: StateStore | None = None,
    poll_interval: str | None = None,
    time_trigger_interval: str | None = None,
) -> dict[str, object]:
    """Register an expert role for event-driven invocation."""
    slug = slugify(domain)
    role_name = name or f"expert-{slug}"
    brief = init_brief or (
        "Survey the current state of your specialty in the context of this project's topic."
    )
    return _do_register(
        project_port=project_port,
        role_name=role_name,
        init_brief=brief,
        store=store or StateStore(),
        poll_interval=poll_interval,
        time_trigger_interval=time_trigger_interval,
    )


def _do_register(
    project_port: int,
    role_name: str,
    init_brief: str | None,
    store: StateStore,
    poll_interval: str | None,
    time_trigger_interval: str | None,
) -> dict[str, object]:
    entry = store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    existing = next((r for r in entry.active_roles if r.name == role_name), None)
    if existing and existing.state == "active":
        raise AlreadyActive(f"Role {role_name!r} is already active on port {project_port}.")

    interval = _resolve_poll_interval(poll_interval)
    resolved_time_trigger = _resolve_time_trigger_interval(role_name, time_trigger_interval)
    wake_policy = "any" if resolved_time_trigger else "event"

    try:
        workspace_branch, workspace_path = ensure_role_workspace(
            project_port,
            role_name,
            base_branch=entry.current_branch or None,
        )
    except Exception as exc:
        raise RoleError(
            f"Role {role_name!r} could not prepare its workspace on port {project_port}: {exc}"
        ) from exc
    session_name = project_session_name(project_port, role_name)

    try:
        agent_token, _seeds = register_project_role_agent(project_port, role_name)
    except BackendError as exc:
        raise RoleError(
            f"Role {role_name!r} could not join project-local EACN3 network "
            f"on port {project_port}: {exc}"
        ) from exc

    now = _now_iso()
    role_entry = RoleEntry(
        name=role_name,
        state="active",
        pid=None,
        spawned_at=now,
        session_name=session_name,
        session_resumable=False,
        workspace_path=str(workspace_path.resolve()),
        workspace_branch=workspace_branch,
        github_push_target=getattr(entry, "github_push_target", None),
        poll_interval=interval,
        wake_policy=wake_policy,
        time_trigger_interval=resolved_time_trigger,
        eacn_agent_id=resolve_agent_id(project_port, role_name),
        eacn_agent_token=agent_token,
        eacn_registered_at=now,
    )

    if init_brief:
        target_agent_id = resolve_agent_id(project_port, role_name)
        initiator_id = resolve_agent_id(project_port, "gru")
        if role_name == "noter":
            try:
                result = eacn_client.send_message(
                    port=project_port,
                    to_agent_id=target_agent_id,
                    from_agent_id=initiator_id,
                    content={
                        "type": "init_brief",
                        "description": init_brief,
                        "role": role_name,
                    },
                )
                with contextlib.suppress(Exception):
                    direct_message_signal(
                        port=project_port,
                        to_agent_id=target_agent_id,
                        from_agent_id=initiator_id,
                        content={
                            "type": "init_brief",
                            "role": role_name,
                            "delivery": result.get("message_id") or result.get("id"),
                        },
                        source="minions.lifecycle.role.register_role",
                        store=store,
                        target_role_name=role_name,
                    )
            except BackendError as exc:
                raise RoleError(
                    f"Role {role_name!r} joined project-local EACN3 on port {project_port}, "
                    f"but the init_brief direct message could not be queued through EACN3: {exc}"
                ) from exc
            logger.info(
                "init_brief direct message published via EACN: role=%r port=%d",
                role_name,
                project_port,
            )
        else:
            try:
                task = eacn_client.create_task(
                    port=project_port,
                    description=init_brief,
                    domains=role_agent_domains(role_name),
                    initiator_id=initiator_id,
                    budget=0.0,
                    expected_output={
                        "type": "status_or_artifact",
                        "description": (
                            "Handle the initial role brief and report progress through EACN."
                        ),
                    },
                    invited_agent_ids=[target_agent_id],
                )
                with contextlib.suppress(Exception):
                    task_signal(
                        port=project_port,
                        task=task,
                        source="minions.lifecycle.role.register_role",
                        store=store,
                        target_role_names=[role_name],
                    )
            except BackendError as exc:
                raise RoleError(
                    f"Role {role_name!r} joined project-local EACN3 on port {project_port}, "
                    f"but the init_brief task could not be queued through EACN3: {exc}"
                ) from exc
            logger.info(
                "init_brief task published via EACN: role=%r port=%d",
                role_name,
                project_port,
            )

    store.upsert_role(project_port, role_entry)
    logger.info("register_role: role=%r port=%d poll=%s", role_name, project_port, interval)

    return {
        "name": role_name,
        "session_name": session_name,
        "workspace_path": str(workspace_path.resolve()),
        "workspace_branch": workspace_branch,
        "poll_interval": interval,
        "wake_policy": wake_policy,
        "time_trigger_interval": resolved_time_trigger,
        "ephemeral": True,
        "eacn_agent_id": role_entry.eacn_agent_id,
    }


# ---------------------------------------------------------------------------
# Ephemeral invocation (short-lived agent-host subprocess)
# ---------------------------------------------------------------------------


def invoke_role_ephemeral(
    role_name: str,
    project_port: int,
    events: list[dict[str, Any]],
    extra_env: dict[str, str] | None = None,
    wait: bool = False,
    scratchpad_path: Path | None = None,
    store: StateStore | None = None,
) -> dict[str, object]:
    """Launch one bounded host wake-up for *role_name* to process *events*.

    The subprocess is seeded with the Role's SYSTEM.md and a user message
    containing the event batch as JSON. Host session persistence remains enabled
    so later wake-ups can resume the same logical session in the role workspace.

    Args:
        role_name: Registered role name.
        project_port: Project port.
        events: List of EACN event dicts to process.
        extra_env: Optional additional environment variables.
        wait: If True, block until the subprocess exits. Default False
            (fire-and-forget; the scheduler does not block on one role).
        store: Optional StateStore for PID persistence.

    Returns:
        ``{"name": role_name, "pid": <pid>, "events": <count>,
        "deferred": <bool>}``. When ``deferred`` is True another invocation
        for the same (port, role) is still in flight and this call was a
        no-op.
    """
    # Opportunistic reap before in-flight check so a just-exited process does
    # not spuriously block a new wakeup.
    reap_finished(store=store)
    key = (project_port, role_name)
    _store = store or StateStore()
    project = _store.get_project(project_port)
    role_record = None
    if project is not None:
        role_record = next((r for r in project.active_roles if r.name == role_name), None)
    workspace = (
        Path(role_record.workspace_path)
        if role_record is not None and role_record.workspace_path
        else project_role_workspace(project_port, role_name)
    )
    if not workspace.exists() and project_workspace(project_port).exists():
        workspace = project_workspace(project_port)
    session_name = (
        role_record.session_name
        if role_record is not None and role_record.session_name
        else project_session_name(project_port, role_name)
    )
    resume_session = bool(role_record and getattr(role_record, "session_resumable", False))
    workspace_branch = (
        role_record.workspace_branch
        if role_record is not None and role_record.workspace_branch
        else project_branch_name(project_port, role_name)
    )
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT or key in _STARTING:
            logger.info(
                "invoke_role_ephemeral: deferring — role=%r port=%d already in flight",
                role_name,
                project_port,
            )
            return {
                "name": role_name,
                "pid": None,
                "events": len(events),
                "deferred": True,
            }
        _STARTING.add(key)

    system_path = _build_system_prompt(role_name)
    log_path = project_role_log(project_port, role_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure memory/ exists and resolve scratchpad path.
    project_memory_dir(project_port).mkdir(parents=True, exist_ok=True)
    if scratchpad_path is None:
        scratchpad_path = project_scratchpad(project_port, role_name)
    scratchpad_status = (extra_env or {}).get("MINIONS_SCRATCHPAD_STATUS", "ok")

    allowed = whitelist_csv(role_name, "main")

    message = _format_event_message(
        events,
        scratchpad_path=scratchpad_path,
        scratchpad_status=scratchpad_status,
        project_port=project_port,
        role_name=role_name,
        workspace_path=workspace,
        workspace_branch=workspace_branch,
        session_name=session_name,
        resume_session=resume_session,
    )

    cfg = load_gru_config()
    invocation = build_role_invocation(
        cfg=cfg,
        role_name=role_name,
        project_port=project_port,
        system_path=system_path,
        allowed_tools=allowed,
        message=message,
        workspace=workspace,
        session_name=session_name,
        resume_session=resume_session,
    )

    env = {
        **os.environ,
        "MINIONS_AGENT_HOST": invocation.host_name,
        "MINIONS_ROLE_NAME": role_name,
        "MINIONS_PROJECT_PORT": str(project_port),
        "MINIONS_WORKSPACE_ROOT": str(project_workspace_root(project_port)),
        "MINIONS_WORKSPACE_MAIN": str(project_workspace(project_port)),
        "MINIONS_ROLE_WORKSPACE": str(workspace),
        "MINIONS_ROLE_WORKSPACE_BRANCH": workspace_branch,
        "MINIONS_SESSION_NAME": session_name,
        "MINIONS_SESSION_MODE": "resume" if resume_session else "fresh",
        "MINIONS_SESSION_RESUMABLE": "1" if resume_session else "0",
        "EACN3_NETWORK_URL": f"http://127.0.0.1:{project_port}",
        # Per-role state dir so the EACN3 MCP plugin's on-disk agent-token
        # cache does not collide between roles sharing the same host.
        "EACN3_STATE_DIR": str(
            plugin_state_dir(project_port, resolve_agent_id(project_port, role_name)).resolve()
        ),
        "MINIONS_GITHUB_PUSH_TARGET": str(
            getattr(role_record, "github_push_target", None)
            or getattr(project, "github_push_target", None)
            or ""
        ),
        "MINIONS_EPHEMERAL": "1",
        "MINIONS_MCP_PROFILE": "codex" if invocation.host_name == "codex" else "full",
        "EACN3_MCP_PROFILE": "codex-core" if invocation.host_name == "codex" else "full",
        "MINIONS_SCRATCHPAD_PATH": str(scratchpad_path),
        "MINIONS_SCRATCHPAD_STATUS": scratchpad_status,
        **(extra_env or {}),
    }

    log_fp = log_path.open("a", encoding="utf-8")
    logger.info(
        "invoke_role_ephemeral: role=%r port=%d events=%d host=%s",
        role_name,
        project_port,
        len(events),
        invocation.host_name,
    )
    proc: subprocess.Popen[bytes] | None = None
    _store = store or StateStore()
    try:
        proc = subprocess.Popen(
            invocation.command,
            cwd=str(invocation.cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=log_fp,
            stderr=log_fp,
            start_new_session=True,
        )

        # Persist liveness state as soon as the PID exists. A running
        # ephemeral process is active; after reap it returns to sleeping.
        try:
            entry = _store.get_project(project_port)
            if entry is not None:
                role = next((r for r in entry.active_roles if r.name == role_name), None)
                if role is not None:
                    _store.upsert_role(
                        project_port,
                        role.model_copy(
                            update={
                                "state": "active",
                                "pid": proc.pid,
                                "spawned_at": _now_iso(),
                                "session_name": session_name,
                                "session_resumable": True,
                                "workspace_path": str(workspace.resolve()),
                                "workspace_branch": workspace_branch,
                                "github_push_target": env["MINIONS_GITHUB_PUSH_TARGET"] or None,
                            }
                        ),
                    )
                    with contextlib.suppress(Exception):
                        _store.touch_role_last_seen(project_port, role_name)
        except Exception as exc:
            logger.debug("invoke_role_ephemeral: pid persist failed: %s", exc)

        try:
            proc.stdin.write(invocation.stdin_text.encode("utf-8"))  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
        except BrokenPipeError:
            logger.warning(
                "invoke_role_ephemeral: %s closed stdin before message was fully written "
                "(role=%r port=%d)",
                invocation.host_name,
                role_name,
                project_port,
            )
        except Exception:
            _terminate_spawned_proc(proc)
            with contextlib.suppress(Exception):
                _clear_persisted_pid_if_matches(_store, project_port, role_name, proc.pid)
            raise

        if invocation.host_name == "codex":
            immediate_rc = _wait_for_immediate_exit(proc, _CODEX_STARTUP_FAILURE_GRACE_SECONDS)
        else:
            polled = proc.poll()
            immediate_rc = polled if isinstance(polled, int) else None
        if immediate_rc is not None:
            with contextlib.suppress(Exception):
                log_fp.flush()
            with contextlib.suppress(Exception):
                _clear_persisted_pid_if_matches(_store, project_port, role_name, proc.pid)
            with contextlib.suppress(Exception):
                log_fp.close()
            if immediate_rc != 0:
                tail = _tail_log(log_path)
                detail = f" Role log tail:\n{tail}" if tail else f" See role log: {log_path}"
                raise RoleError(
                    f"{invocation.host_name} role process exited during startup "
                    f"(role={role_name!r} port={project_port} rc={immediate_rc}).{detail}"
                )
            with _INFLIGHT_LOCK:
                _STARTING.discard(key)
            return {
                "name": role_name,
                "pid": proc.pid,
                "events": len(events),
                "deferred": False,
            }
    except Exception:
        with _INFLIGHT_LOCK:
            _STARTING.discard(key)
        with contextlib.suppress(Exception):
            log_fp.close()
        raise

    with _INFLIGHT_LOCK:
        _STARTING.discard(key)
        _INFLIGHT[key] = (proc, log_fp)

    if wait:
        try:
            proc.wait()
        finally:
            reap_finished(store=_store)
    return {"name": role_name, "pid": proc.pid, "events": len(events), "deferred": False}


def _format_event_message(
    events: list[dict[str, Any]],
    scratchpad_path: Path | None = None,
    scratchpad_status: str = "ok",
    project_port: int | None = None,
    role_name: str | None = None,
    workspace_path: Path | None = None,
    workspace_branch: str | None = None,
    session_name: str | None = None,
    resume_session: bool = False,
) -> str:
    """Render an event batch as a user message for the ephemeral agent-host process."""
    preamble = ""
    if scratchpad_path is not None:
        rel = (
            f"project_{project_port}/memory/{role_name}.md"
            if project_port
            else str(scratchpad_path)
        )
        preamble = (
            f"[Scratchpad] {rel}  (status: {scratchpad_status})\n"
            "Read it first to recover only the durable working memory you need. "
            "Before exit, update it:\n"
            "keep only what future-you needs (in-flight tasks, tentative hypotheses,\n"
            "unresolved questions, decisions not yet written elsewhere). Remove stale\n"
            "entries. Do not dump transcripts or preserve completed-task context.\n"
        )
        if scratchpad_status == "hard":
            preamble += (
                "Compress the scratchpad in place (subagent) BEFORE processing new events.\n"
            )
        elif scratchpad_status == "veto_compact":
            preamble += (
                "This is a maintenance wake-up only: compact the scratchpad in place, "
                "then exit. Do not process buffered EACN work, bid on tasks, or emit "
                "project-status responses during this wake-up. Preserve durable open "
                "state in the main scratchpad; move stale or bulky background notes "
                "to an `archive/` directory under the project memory directory with "
                "a short index entry if needed.\n"
            )
        elif scratchpad_status == "soft":
            preamble += "When convenient, dispatch a subagent to compress.\n"
        preamble += "\n"
    if workspace_path is not None:
        preamble += "[Workspace]\n"
        if project_port is not None:
            preamble += f"- Main workspace: `{project_workspace(project_port)}`\n"
        preamble += f"- Role workspace: `{workspace_path}`\n"
        if workspace_branch:
            preamble += f"- Git branch: `{workspace_branch}`\n"
        if session_name:
            preamble += f"- Session name: `{session_name}`\n"
        preamble += f"- Resume session: `{str(bool(resume_session)).lower()}`\n\n"
    if role_name:
        skills = list_skills(role_name)
        if skills:
            base = "expert" if role_name.startswith("expert") else role_name
            common_skill_path_pattern = (
                MINIONS_ROOT / "minions" / "roles" / "common" / "skills" / "{slug}.md"
            ).resolve()
            role_skill_path_pattern = (
                MINIONS_ROOT / "minions" / "roles" / base / "skills" / "{slug}.md"
            ).resolve()
            lines = [f"- {slug}: {summary}" if summary else f"- {slug}" for slug, summary in skills]
            skills_block = (
                "[Skills]\n"
                + "\n".join(lines)
                + "\n"
                + f"Read shared skill files at `{common_skill_path_pattern}` "
                + f"and role skill files at `{role_skill_path_pattern}` "
                + "when relevant; they are reasoning/procedure disciplines, not rituals.\n\n"
            )
            preamble += skills_block
    if role_name and project_port:
        agent_id = resolve_agent_id(project_port, role_name)
        preamble += (
            "[EACN identity]\n"
            f"You are already registered on this project's Local EACN3 network as "
            f"agent_id `{agent_id}` at `http://127.0.0.1:{project_port}`. "
            "If the EACN3 plugin reports no active session, call `eacn3_connect` "
            "with that network endpoint and claim this agent id if prompted. "
            "When an EACN tool accepts `agent_id`, `sender_id`, or `initiator_id`, "
            f"pass `{agent_id}` explicitly. Do not create or use a different "
            "project identity.\n\n"
        )
        preamble += _boundary_context(role_name, project_port) + "\n"
    if role_name == "gru":
        response_tools = (
            "project-scoped EACN adapter tools (`gru_inbox_poll`, "
            "`project_eacn_send_message`, `project_eacn_create_task`, `gru_relay`)"
        )
    else:
        response_tools = "`eacn3_*` tools"
    hook_signals = [event for event in events if is_wake_signal(event)]
    if hook_signals and len(hook_signals) == len(events):
        lines = [f"- {summarize_signal(signal)}" for signal in hook_signals]
        kinds = {str(signal.get("kind") or "") for signal in hook_signals}
        if kinds == {"phase_change"}:
            header = (
                "You have been invoked by a MinionsOS phase change signal.\n"
                "Read the current phase from the project state before doing any work. "
                "If the signal says this role is no longer allowed, write a compact "
                "scratchpad summary, checkpoint, and exit; if it is still allowed, "
                "reconcile your local context with the new phase and then go onto EACN3 "
                "only after that.\n\n"
            )
            return preamble + header + "Wake signals:\n" + "\n".join(lines) + "\n"
        header = (
            "You have been invoked by MinionsOS hook wake signal(s), not by a "
            "pre-drained EACN event batch.\n"
            f"Go onto this project's EACN3 network using {response_tools}, inspect "
            "your own queue/open tasks/messages, handle work that belongs to your Role, "
            "then checkpoint and exit this bounded wake window. The wake signal below "
            "is only a routing hint; do not treat it as the authoritative task or "
            "message payload.\n\n"
        )
        return preamble + header + "Wake signals:\n" + "\n".join(lines) + "\n"
    if scratchpad_status == "veto_compact":
        header = (
            "You have been invoked for scratchpad maintenance because the role's "
            "scratchpad exceeded the veto threshold.\n"
            "Act only on the maintenance event below: reduce the scratchpad to durable, "
            "high-signal state and then exit. Buffered EACN events are still held by "
            "MinionsOS and will be redelivered after the scratchpad is below veto.\n\n"
        )
    else:
        header = (
            "You have been invoked to process the following EACN event batch.\n"
            f"Act on these events, emit any necessary EACN responses via {response_tools}, "
            "then exit this bounded wake window; do not start a polling loop. "
            "If accepted work belongs to your Role, dispatch your "
            "own focused subagent(s) for the substantive execution and keep this "
            "main session focused on coordination, review, checkpointing, and EACN "
            "communication. Treat this as fresh execution context; after the task "
            "is handled or checkpointed, leave only compressed durable state in the "
            "scratchpad.\n\n"
        )
    try:
        body = json.dumps(events, indent=2, default=str)
    except Exception:
        body = repr(events)
    return preamble + header + f"Events:\n```json\n{body}\n```\n"


# ---------------------------------------------------------------------------
# Backwards-compatible aliases
# ---------------------------------------------------------------------------

# ``spawn_role`` / ``spawn_expert`` retained as aliases so the MCP server,
# CLI, and existing tests keep working during migration.
spawn_role = register_role
spawn_expert = register_expert


# ---------------------------------------------------------------------------
# Dismiss / list
# ---------------------------------------------------------------------------


def dismiss_role(
    project_port: int,
    role_name: str,
    store: StateStore | None = None,
) -> dict[str, str]:
    """Mark a role dismissed in the registry. No subprocess to terminate."""
    _store = store or StateStore()
    entry = _store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    role = next((r for r in entry.active_roles if r.name == role_name), None)
    if role is None:
        raise RoleError(f"Role {role_name!r} not found on port {project_port}.")

    try:
        from minions.lifecycle import eacn_client

        eacn_client.unregister_agent(project_port, role.eacn_agent_id or role_name)
    except Exception as exc:
        logger.warning(
            "dismiss_role: EACN unregister failed for role=%r port=%d: %s",
            role_name,
            project_port,
            exc,
        )

    _store.upsert_role(project_port, role.model_copy(update={"state": "dismissed", "pid": None}))
    logger.info("dismiss_role done: role=%r port=%d", role_name, project_port)
    return {"name": role_name}


def list_roles(
    project_port: int,
    store: StateStore | None = None,
) -> list[dict[str, object]]:
    _store = store or StateStore()
    entry = _store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")
    return [
        {
            "name": r.name,
            "state": r.state,
            "pid": r.pid,
            "eacn_agent_id": r.eacn_agent_id or r.name,
            "session_name": getattr(r, "session_name", None),
            "session_resumable": getattr(r, "session_resumable", False),
            "workspace_path": getattr(r, "workspace_path", None),
            "workspace_branch": getattr(r, "workspace_branch", None),
        }
        for r in entry.active_roles
    ]
