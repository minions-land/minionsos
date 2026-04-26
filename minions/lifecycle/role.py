"""Role lifecycle: register, invoke (ephemeral), dismiss, list.

Event-driven model (replaces the long-running-subprocess model):

- ``register_role`` / ``register_expert`` register a project-local EACN3
  AgentCard and record a Role in ``projects.json`` (name, port, poll cadence).
  No Claude subprocess is launched.
- ``invoke_role_ephemeral`` launches a SHORT-LIVED Claude subprocess seeded
  with the Role's SYSTEM.md and a batch of events to act on. The process
  exits when the Role finishes its response.
- ``dismiss_role`` / ``list_roles`` operate on the registry.

The public ``spawn_role`` / ``spawn_expert`` names are retained as
backwards-compatible aliases for ``register_role`` / ``register_expert`` so
existing MCP tool callers and tests keep working.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from minions.config import (
    ROLE_CLASSIFICATION,
    ROLE_WRITE_BOUNDARIES,
    RoleType,
    slugify,
    whitelist_csv,
)
from minions.errors import AlreadyActive, BackendError, RoleError
from minions.lifecycle.agent_registry import register_project_role_agent
from minions.lifecycle.skills import list_skills
from minions.paths import (
    MINIONS_ROOT,
    project_dir,
    project_memory_dir,
    project_role_log,
    project_scratchpad,
    project_workspace,
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
_INFLIGHT_LOCK = threading.Lock()


def is_inflight(project_port: int, role_name: str) -> bool:
    """Return True if an ephemeral subprocess for (port, role) is still running.

    Opportunistically reaps any exited processes before answering.
    """
    reap_finished()
    with _INFLIGHT_LOCK:
        return (project_port, role_name) in _INFLIGHT


def reap_finished(store: StateStore | None = None) -> list[tuple[int, str, int]]:
    """Reap any exited in-flight ephemeral subprocesses.

    Closes their log file handles, clears PID from the registry, and records
    the exit status. Returns a list of ``(port, role, returncode)`` tuples
    for the processes that were reaped in this call.
    """
    reaped: list[tuple[int, str, int]] = []
    with _INFLIGHT_LOCK:
        keys = list(_INFLIGHT.keys())
        for key in keys:
            proc, log_fp = _INFLIGHT[key]
            rc = proc.poll()
            if rc is None:
                continue
            with contextlib.suppress(Exception):
                log_fp.close()
            del _INFLIGHT[key]
            reaped.append((key[0], key[1], rc))

    if reaped:
        _store = store or StateStore()
        for port, role_name, _rc in reaped:
            try:
                entry = _store.get_project(port)
                if entry is None:
                    continue
                role = next((r for r in entry.active_roles if r.name == role_name), None)
                if role is None or role.state != "active":
                    continue
                # Clear pid so liveness check does not misfire on a reused PID.
                _store.upsert_role(
                    port,
                    role.model_copy(update={"pid": None}),
                )
            except Exception as exc:
                logger.debug("reap: clear pid failed port=%d role=%r: %s", port, role_name, exc)
    return reaped


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _build_system_prompt(role: str) -> Path | None:
    base = role_system_md(role if not role.startswith("expert") else "expert")
    if not base.exists():
        logger.debug("SYSTEM.md not found for role %r at %s", role, base)
        return None
    return base


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
        "Write boundaries: workspace/, memory/.\n"
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
) -> dict[str, object]:
    """Register a fixed role for event-driven invocation.

    Does NOT launch a Claude subprocess. The Python-level WakeupScheduler
    polls EACN for this role and invokes it ephemerally when events arrive.

    If *init_brief* is given, it is dispatched as a one-shot invocation
    immediately so the role can do its first action (e.g. Expert's survey).
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
    )


def register_expert(
    project_port: int,
    domain: str,
    name: str | None = None,
    init_brief: str | None = None,
    store: StateStore | None = None,
    poll_interval: str | None = None,
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
    )


def _do_register(
    project_port: int,
    role_name: str,
    init_brief: str | None,
    store: StateStore,
    poll_interval: str | None,
) -> dict[str, object]:
    entry = store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    existing = next((r for r in entry.active_roles if r.name == role_name), None)
    if existing and existing.state == "active":
        raise AlreadyActive(f"Role {role_name!r} is already active on port {project_port}.")

    interval = _resolve_poll_interval(poll_interval)

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
        poll_interval=interval,
        eacn_agent_id=role_name,
        eacn_agent_token=agent_token,
        eacn_registered_at=now,
    )

    if init_brief:
        # Post the kickoff as a real EACN direct message (gru → role). The
        # WakeupScheduler will then deliver it on the next tick. This is the
        # authoritative path: it leaves an audit trail on the bus and matches
        # the "dispatch via EACN only" convention. We deliberately do NOT
        # spawn a local ephemeral Claude here — that would be invisible to
        # EACN and race with the scheduler.
        from minions.lifecycle import eacn_client

        try:
            eacn_client.post_message(
                port=project_port,
                to_agent_id=role_name,
                from_agent_id="gru",
                content={"type": "init_brief", "text": init_brief},
            )
        except BackendError as exc:
            raise RoleError(
                f"Role {role_name!r} joined project-local EACN3 on port {project_port}, "
                f"but the init_brief could not be queued through EACN3: {exc}"
            ) from exc
        logger.info("init_brief posted via EACN: role=%r port=%d", role_name, project_port)

    store.upsert_role(project_port, role_entry)
    logger.info("register_role: role=%r port=%d poll=%s", role_name, project_port, interval)

    return {
        "name": role_name,
        "poll_interval": interval,
        "ephemeral": True,
        "eacn_agent_id": role_name,
    }


# ---------------------------------------------------------------------------
# Ephemeral invocation (short-lived Claude subprocess)
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
    """Launch a short-lived Claude subprocess for *role_name* to process *events*.

    The subprocess is seeded with the Role's SYSTEM.md and a user message
    containing the event batch as JSON. It exits when the Role finishes
    responding.

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
    with _INFLIGHT_LOCK:
        if (project_port, role_name) in _INFLIGHT:
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

    system_path = _build_system_prompt(role_name)
    workspace = project_workspace(project_port)
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
    )

    cmd = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "claude",
    ]
    if system_path and system_path.exists():
        cmd += ["--append-system-prompt", f"@{system_path}"]
    cmd += [
        "--mcp-config",
        str(MINIONS_ROOT / ".mcp.json"),
        "--allowed-tools",
        allowed,
        # Headless wake-up: bypass interactive permission prompts (Roles are
        # ephemeral and cannot answer them), and use -p/--print with stdin for
        # prompt delivery. The legacy `--message <msg>` flag does not exist in
        # current Claude CLI and caused role wake-ups to fail with
        # `error: unknown option '--message'`.
        "--permission-mode",
        "bypassPermissions",
        "-p",
    ]

    env = {
        **os.environ,
        "MINIONS_ROLE_NAME": role_name,
        "MINIONS_PROJECT_PORT": str(project_port),
        "EACN3_NETWORK_URL": f"http://127.0.0.1:{project_port}",
        # Per-role state dir so the EACN3 MCP plugin's on-disk agent-token
        # cache does not collide between roles sharing the same host.
        "EACN3_STATE_DIR": str(
            (project_dir(project_port) / "eacn3_data" / f"plugin-{role_name}").resolve()
        ),
        "MINIONS_EPHEMERAL": "1",
        "MINIONS_SCRATCHPAD_PATH": str(scratchpad_path),
        "MINIONS_SCRATCHPAD_STATUS": scratchpad_status,
        **(extra_env or {}),
    }

    log_fp = log_path.open("a", encoding="utf-8")
    logger.info(
        "invoke_role_ephemeral: role=%r port=%d events=%d",
        role_name,
        project_port,
        len(events),
    )
    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace) if workspace.exists() else str(MINIONS_ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=log_fp,
        stderr=log_fp,
        start_new_session=True,
    )
    try:
        proc.stdin.write(message.encode("utf-8"))  # type: ignore[union-attr]
        proc.stdin.close()  # type: ignore[union-attr]
    except BrokenPipeError:
        logger.warning(
            "invoke_role_ephemeral: claude closed stdin before message was fully written "
            "(role=%r port=%d)",
            role_name,
            project_port,
        )

    # Persist liveness state.
    _store = store or StateStore()
    try:
        entry = _store.get_project(project_port)
        if entry is not None:
            role = next((r for r in entry.active_roles if r.name == role_name), None)
            if role is not None:
                _store.upsert_role(
                    project_port,
                    role.model_copy(update={"pid": proc.pid, "spawned_at": _now_iso()}),
                )
    except Exception as exc:
        logger.debug("invoke_role_ephemeral: pid persist failed: %s", exc)

    with _INFLIGHT_LOCK:
        _INFLIGHT[(project_port, role_name)] = (proc, log_fp)

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
) -> str:
    """Render an event batch as a user message for the ephemeral Claude process."""
    preamble = ""
    if scratchpad_path is not None:
        rel = (
            f"project_{project_port}/memory/{role_name}.md"
            if project_port
            else str(scratchpad_path)
        )
        preamble = (
            f"[Scratchpad] {rel}  (status: {scratchpad_status})\n"
            "Read it first to recover your working memory. Before exit, update it:\n"
            "keep only what future-you needs (in-flight tasks, tentative hypotheses,\n"
            "unresolved questions, decisions not yet written elsewhere). Remove stale\n"
            "entries. Do not dump transcripts.\n"
        )
        if scratchpad_status == "hard":
            preamble += (
                "Compress the scratchpad in place (subagent) BEFORE processing new events.\n"
            )
        elif scratchpad_status == "soft":
            preamble += "When convenient, dispatch a subagent to compress.\n"
        preamble += "\n"
    if role_name:
        skills = list_skills(role_name)
        if skills:
            base = "expert" if role_name.startswith("expert") else role_name
            lines = [f"- {slug}: {summary}" if summary else f"- {slug}" for slug, summary in skills]
            skills_block = (
                "[Skills]\n"
                + "\n".join(lines)
                + "\n"
                + f"Consult these skills at `minions/roles/{base}/skills/{{slug}}.md` "
                + "when relevant; they are reasoning/procedure disciplines, not rituals.\n\n"
            )
            preamble += skills_block
    if role_name and project_port:
        preamble += (
            "[EACN identity]\n"
            f"You are already registered on this project's Local EACN3 network as "
            f"agent_id `{role_name}` at `http://127.0.0.1:{project_port}`. "
            "When an EACN tool accepts `agent_id`, `sender_id`, or `initiator_id`, "
            f"pass `{role_name}` explicitly. Do not create or use a different "
            "project identity.\n\n"
        )
        preamble += _boundary_context(role_name, project_port) + "\n"
    header = (
        "You have been invoked to process the following EACN event batch.\n"
        "Act on these events, emit any necessary EACN responses via `eacn3_*` "
        "tools, then exit (this is an ephemeral session — do not start a "
        "polling loop).\n\n"
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
        }
        for r in entry.active_roles
    ]
