"""Role lifecycle: register, wake, dismiss, list.

Current MinionsOS transition model:

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
import time
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
from minions.lifecycle.hooks import LifecycleEvent
from minions.lifecycle.hooks import fire as hooks_fire
from minions.lifecycle.project import ensure_role_workspace, project_phase_snapshot
from minions.lifecycle.skills import list_skills
from minions.lifecycle.wake_signals import (
    is_wake_signal,
    summarize_signal,
)
from minions.paths import (
    MINIONS_ROOT,
    common_role_system_md,
    project_branch_name,
    project_memory_dir,  # noqa: F401  # re-exported for test monkeypatch compatibility
    project_role_branch_leaf,
    project_role_log,
    project_role_workspace,
    project_scratchpad,
    project_session_name,
    project_workspace,
    project_workspace_root,
    role_system_md,
)
from minions.state.store import ProjectPhaseSnapshot, RoleEntry, StateStore

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
# (port, role) -> per-wake metadata used by the reaper to archive the host
# session jsonl after the subprocess exits. Populated alongside _INFLIGHT.
_WAKE_META: dict[tuple[int, str], dict[str, Any]] = {}
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

    Closes their log file handles, clears PID from the registry, archives the
    host session jsonl into the role's branch, and records the exit status.
    Returns a list of ``(port, role, returncode)`` tuples for the processes
    that were reaped in this call.
    """
    from minions.lifecycle.session_archive import archive_session

    reaped: list[tuple[int, str, int]] = []
    reaped_details: list[tuple[int, str, int, int]] = []
    wake_metas: list[tuple[int, str, dict[str, Any]]] = []
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
            meta = _WAKE_META.pop(key, None)
            del _INFLIGHT[key]
            reaped.append((key[0], key[1], rc))
            reaped_details.append((key[0], key[1], pid, rc))
            if meta is not None:
                wake_metas.append((key[0], key[1], meta))

    # Archive host session jsonl outside the inflight lock (does file I/O).
    for port, role_name, meta in wake_metas:
        try:
            archive_session(
                host=str(meta.get("host") or ""),
                workspace=meta["workspace"],
                started_at=float(meta.get("started_at") or 0.0),
            )
        except Exception as exc:
            logger.debug("reap: session archive failed port=%d role=%r: %s", port, role_name, exc)

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


def _read_pending_safely(project_port: int, role_name: str) -> list[dict[str, Any]]:
    """Return the pending inbox contents, swallowing any error.

    The pending inbox is the per-role crash-shim managed by
    ``minions.lifecycle.mos_pool``. Reading it must never fail a wake:
    if the file is corrupt or the module is temporarily unavailable we
    log and act as if there is nothing pending.
    """
    try:
        from minions.lifecycle import mos_pool

        return mos_pool.mos_pending_read(project_port, role_name)
    except Exception as exc:
        logger.debug(
            "wake: reading pending inbox failed (port=%d role=%s): %s",
            project_port,
            role_name,
            exc,
        )
        return []


def _summarize_pending_entry(entry: dict[str, Any]) -> str:
    """Render a single pending-inbox event as a one-line preamble bullet.

    Keeps the prompt short: agent is expected to go look up full details
    via non-destructive EACN3 reads (eacn3_get_task / eacn3_get_messages)
    before acting. We only surface the identifier and a minimal routing
    hint so the agent knows which queue position this entry represents.
    """
    event_id = ""
    for key in ("msg_id", "id", "event_id", "task_id"):
        val = entry.get(key)
        if isinstance(val, str) and val:
            event_id = val
            break
    event_type = str(entry.get("type") or "unknown")
    task_id = str(entry.get("task_id") or "")
    parts = [f"event_id=`{event_id or '<missing>'}`", f"type=`{event_type}`"]
    if task_id and task_id != event_id:
        parts.append(f"task_id=`{task_id}`")
    payload = entry.get("payload")
    if isinstance(payload, dict):
        src = payload.get("from") or payload.get("initiator_id")
        if isinstance(src, str) and src:
            parts.append(f"from=`{src}`")
    return ", ".join(parts)


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


def _combined_system_prompt_text(role: str) -> str | None:
    """Return the combined common+role SYSTEM.md text, or None if unavailable."""
    role_path = role_system_md(role if not role.startswith("expert") else "expert")
    common_path = common_role_system_md()
    paths = [path for path in (common_path, role_path) if path.exists()]
    if not paths:
        return None

    parts: list[str] = []
    for path in paths:
        label = "Common Role System" if path == common_path else f"{role} Role System"
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        parts.append(f"# {label}\n\n{text.strip()}\n")
    if not parts:
        return None
    return "\n\n---\n\n".join(parts) + "\n"


_AGENTS_MD_HEADER = (
    "<!--\n"
    "Auto-generated by MinionsOS at wake-up. Do not edit by hand; edits are\n"
    "overwritten on the next wake. The source of truth is the role's SYSTEM.md\n"
    "under `minions/roles/{role}/SYSTEM.md` plus the common\n"
    "`minions/roles/SYSTEM.md`.\n\n"
    "Codex discovers this file automatically when launched with cwd at the\n"
    "role's branch directory, so the role contract stays in the host's\n"
    "instruction layer (not the conversation body) and is not at risk of being\n"
    "reshaped by auto-compact.\n"
    "-->\n\n"
)


def _ensure_role_agents_md(role: str, workspace: Path) -> None:
    """Write the combined SYSTEM.md to ``<workspace>/AGENTS.md`` idempotently.

    Codex reads AGENTS.md from cwd and treats it as a top-level instruction
    wrapper; writing it here is how MinionsOS injects the role contract into
    Codex's system layer. The write is a no-op when contents already match.
    """
    text = _combined_system_prompt_text(role)
    if text is None:
        return
    payload = _AGENTS_MD_HEADER + text
    out_path = workspace / "AGENTS.md"
    try:
        if out_path.exists() and out_path.read_text(encoding="utf-8") == payload:
            return
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".md.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, out_path)
    except Exception as exc:
        logger.warning("Could not write %s for role %r: %s", out_path, role, exc)


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
        "Write boundaries: your branch `branches/main/` (this is Gru's own branch), "
        "`artifacts/` project coordination notes, and your own "
        "`branches/main/.minionsos/scratchpad.md`. Do NOT edit other roles' branches "
        "directly; ask the owning role through EACN instead.\n"
    ),
    "noter": (
        "[Role boundary: human-side agent]\n"
        "You provide staged reports so humans can observe the system: periodic summaries, "
        "pending tasks, risks, evidence chains, artifact indexes, concise status. "
        "You reduce Gru context pressure rather than add to it.\n"
        "Write boundaries: `artifacts/notes/` and your own "
        "`branches/noter/.minionsos/scratchpad.md` only. Do NOT write to any other "
        "role's branch under `branches/`.\n"
    ),
    "coder": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Delegate complex execution to subagents; summarize and write back results.\n"
        "Write boundaries: your branch `branches/coder/` and your own "
        "`branches/coder/.minionsos/scratchpad.md` by default. Conditional "
        "system-maintenance boundary: MinionsOS repository runtime code only when "
        "Gru or the author explicitly assigns that implementation work through EACN "
        "and names the scope, allowed paths, and verification target.\n"
    ),
    "experimenter": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Delegate complex execution to subagents; summarize and write back results.\n"
        "Write boundaries: your branch `branches/experimenter/`, `artifacts/exp-*/` "
        "result bundles, and your own `branches/experimenter/.minionsos/scratchpad.md`.\n"
    ),
    "writer": (
        "[Role boundary: EACN-visible agent]\n"
        "Do NOT invent claims. Output must be based on available evidence, expert feedback, "
        "experiment results, and competitor positioning. "
        "Claims must be supported by evidence, experiment, derivation, citation, "
        "or explicit speculation markers.\n"
        "Write boundaries: your branch `branches/writer/` (primary: "
        "`branches/writer/paper/`) and your own `branches/writer/.minionsos/scratchpad.md`.\n"
    ),
    "reviewer": (
        "[Role boundary: EACN-visible agent — ISOLATED]\n"
        "You see ONLY the paper PDF and submitted/open-source-ready repository code. "
        "You must NOT access internal experiment artifacts, evidence/claim maps, "
        "Ethics reports, Noter reports, internal discussions, known limitations files, "
        "or unresolved risk lists unless they are visible in the submitted PDF or repository. "
        "Each review round produces at least three independent opinions. "
        "Gru does not participate in Review.\n"
        "Write boundaries: `artifacts/reviews/` and your own "
        "`branches/reviewer/.minionsos/scratchpad.md` only. Do NOT write to any "
        "other role's branch under `branches/`.\n"
    ),
    "ethics": (
        "[Role boundary: EACN-visible agent — continuous evidence validation]\n"
        "You continuously check whether agent behavior, communication, theory, code, "
        "and claims have real evidence support. You MAY inspect internal materials: "
        "experiment artifacts, evidence/claim maps, appendix plans, known limitations, "
        "unresolved risks, agent communications, and all claim types.\n"
        "Write boundaries: `artifacts/ethics/` and your own "
        "`branches/ethics/.minionsos/scratchpad.md` only. Do NOT write to any other "
        "role's branch under `branches/`. Do NOT read any other role's "
        "`.minionsos/scratchpad.md` — private working memory must stay private.\n"
    ),
    "expert": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Preferably read-mostly; write to your own branch only when necessary.\n"
        "Write boundaries: your branch `branches/<expert>/` (sparingly, scientific "
        "scratch only) and your own `branches/<expert>/.minionsos/scratchpad.md`.\n"
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
                hooks_fire(
                    LifecycleEvent.wake_direct_message,
                    {
                        "port": project_port,
                        "to_agent_id": target_agent_id,
                        "from_agent_id": initiator_id,
                        "content": {
                            "type": "init_brief",
                            "role": role_name,
                            "delivery": result.get("message_id") or result.get("id"),
                        },
                        "source": "minions.lifecycle.role.register_role",
                        "store": store,
                        "target_role_name": role_name,
                    },
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
                eacn_client.create_task(
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
                hooks_fire(
                    LifecycleEvent.wake_eacn_queue_pending,
                    {
                        "port": project_port,
                        "source": "minions.lifecycle.role.register_role",
                        "store": store,
                    },
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
    project_phase = project_phase_snapshot(project) if project is not None else None
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

    # Ensure this role's .minionsos/ state dir exists inside its branch and
    # resolve the scratchpad path (branches/<role>/.minionsos/scratchpad.md).
    if scratchpad_path is None:
        scratchpad_path = project_scratchpad(project_port, role_name)
    scratchpad_path.parent.mkdir(parents=True, exist_ok=True)
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
        project_phase=project_phase,
    )

    cfg = load_gru_config()
    if cfg.effective_agent_host() == "codex":
        _ensure_role_agents_md(role_name, workspace)
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
        "MINIONS_AGENT_TYPE": "main",
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
        # Codex cannot take an `--allowed-tools` list, so the EACN3 proxy
        # must enforce the same per-role EACN3 surface Claude gets through
        # its CLI flag. Use the role-scoped profile so the proxy consults
        # the active MinionsOS whitelist instead of the legacy fixed subset.
        "EACN3_MCP_PROFILE": ("minions-role" if invocation.host_name == "codex" else "full"),
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
    started_at = time.time()
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

        stdin = proc.stdin
        if stdin is None:
            raise RoleError("Role process did not expose stdin for prompt delivery.")
        try:
            stdin.write(invocation.stdin_text.encode("utf-8"))
            stdin.close()
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
        _WAKE_META[key] = {
            "host": invocation.host_name,
            "workspace": workspace,
            "started_at": started_at,
        }

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
    project_phase: ProjectPhaseSnapshot | None = None,
) -> str:
    """Render an event batch as a user message for the ephemeral agent-host process."""
    preamble = ""
    if scratchpad_path is not None:
        # The scratchpad lives inside the role's branch dir under
        # ``.minionsos/scratchpad.md`` (see project_scratchpad). Render the
        # branch-relative path so the agent finds it regardless of which
        # workspace it was launched in.
        if project_port and role_name:
            leaf = project_role_branch_leaf(role_name)
            rel = f"project_{project_port}/branches/{leaf}/.minionsos/scratchpad.md"
        else:
            rel = str(scratchpad_path)
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

    # Surface un-ACK'd events from the previous wake's crash-shim, if any.
    # The common SYSTEM.md Wake window protocol already tells the role how
    # to handle a "Pending from previous wake" block: verify each is still
    # relevant (eacn3_get_task / eacn3_get_messages), handle if so, then
    # call mos_ack_clear with the event id either way so it retires from
    # pending.jsonl. A healthy wake cycle leaves the file empty, and this
    # block is then omitted entirely.
    if project_port is not None and role_name:
        pending = _read_pending_safely(project_port, role_name)
        if pending:
            preamble += "[Pending from previous wake]\n"
            preamble += (
                f"The previous wake drained {len(pending)} event(s) from EACN3 "
                "but did not finish ACK'ing them before exiting. Each entry "
                "below is already off EACN3's server-side queue, so you must "
                "handle or retire it here. See the common SYSTEM.md "
                "Pending-inbox recovery section for the exact flow.\n\n"
            )
            for entry in pending:
                preamble += f"- {_summarize_pending_entry(entry)}\n"
            preamble += (
                "\nAfter you handle or decide to retire each entry, call "
                "`mos_ack_clear(port, role_name, [event_id])` so it is "
                "removed from `.minionsos/inbox/pending.jsonl`.\n\n"
            )
    if project_phase is not None:
        current_phase = project_phase["current_phase"] or "unset"
        phase_version = project_phase["phase_version"]
        allowed_roles = [
            str(role).strip() for role in project_phase["phase_allowed_roles"] if str(role).strip()
        ]
        online_roles = [
            str(role).strip() for role in project_phase["phase_online_roles"] if str(role).strip()
        ]
        preamble += "[Project phase]\n"
        preamble += f"- Current phase: `{current_phase}`\n"
        preamble += f"- Phase version: `{phase_version}`\n"
        preamble += (
            "- Phase allowed roles: `"
            + (", ".join(allowed_roles) if allowed_roles else "all active roles")
            + "`\n"
        )
        preamble += (
            "- Online roles: `" + (", ".join(online_roles) if online_roles else "none") + "`\n"
        )
        if role_name:
            allowed = project_phase["phase_allowed_roles"]
            role_allowed = not allowed or "*" in allowed or "all" in allowed or role_name in allowed
            preamble += f"- This role allowed now: `{str(bool(role_allowed)).lower()}`\n"
        preamble += "\n"
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
            "the MOS Agent Pool (`mos_await_events`, `mos_send_message`, "
            "`mos_create_task`, `mos_ack_clear`) for MinionsOS-internal work, "
            "or raw `eacn3_*` tools for Global EACN3 scope, plus `gru_relay` "
            "for cross-project bridging"
        )
    else:
        response_tools = (
            "the MOS Agent Pool (`mos_await_events`, `mos_send_message`, "
            "`mos_create_task`, `mos_ack_clear`) for event intake, messages, "
            "and task creation, plus non-destructive `eacn3_get_*` / "
            "`eacn3_list_*` reads when needed"
        )
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
            "Follow the Plan → Dispatch → Verify contract from the common "
            "SYSTEM.md: (1) plan the response in 3-6 lines before acting, "
            "(2) dispatch the substantive work to a host-native subagent, "
            "(3) verify the subagent's return, then (4) emit any necessary "
            f"EACN responses via {response_tools}, and exit this bounded "
            "wake window without starting a polling loop. The main session "
            "is a coordinator — file edits, mutating Bash, `exp_*`, paper "
            "search, coding/reviewing/auditing/writing all belong to a "
            "subagent, not the main thread. Treat this as fresh execution "
            "context; after the task is handled or checkpointed, leave only "
            "compressed durable state in the scratchpad.\n\n"
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
