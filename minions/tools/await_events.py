"""mos_await_events — Role-facing MCP tool for EACN3 event polling.

Wraps ``GET /api/events/{agent_id}?timeout=60`` in an internal loop that
only returns to the LLM when there is actionable content:

1. Real EACN3 events → return immediately with annotations.
2. After 5 consecutive empty polls (~5 min), run an idle check:
   - Query task state and message sessions (same logic as eacn3_next idle).
   - If actionable items found → return as synthetic idle_check event.
   - If nothing (no-idle) → swallow silently, continue polling.
3. After ``cache_keepalive_seconds`` of wall-clock silence, force-return a
   stable synthetic ``cache_keepalive`` event. The Role acks with a fixed
   short reply and immediately re-enters the loop. This re-touches the
   prompt cache before the 5-minute TTL cliff (or, where the gateway
   honors it, the 1-hour cliff after ``ENABLE_PROMPT_CACHING_1H=1`` in
   the Role env). The payload is byte-for-byte identical every time —
   no timestamps, counters, or per-process state — so the post-keepalive
   conversation tail stays cacheable too.
4. Heartbeat file updated every cycle (git-visible liveness, zero LLM tokens).

Token efficiency: the LLM is suspended while this tool blocks. Tokens are
consumed only at call time (input) and return time (output). All intermediate
work (HTTP polls, heartbeat writes, no-idle checks) costs zero LLM tokens.

Internal logic mirrors eacn3_next (idle intelligence), eacn3_await_events
(annotation format), and eacn3_get_events (drain-on-read semantics).
Only the input (env-var identity) and output (never-empty guarantee) differ.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from minions.paths import project_dir as _project_dir

logger = logging.getLogger(__name__)

EACN3_POLL_TIMEOUT_SEC = 60
IDLE_CHECK_THRESHOLD = 5  # consecutive empty polls before idle check

# Issue #37: wall-clock ceiling on a single long-poll call. httpx already
# has timeouts at the connect/read level, but a half-open TCP connection or
# a backend that accepts the request and never writes can defeat them. This
# extra deadline is enforced in Python (signal.SIGALRM where available) and
# guarantees _poll_once returns control to the loop within a bounded window
# regardless of socket-level pathologies. The buffer over the httpx timeout
# is generous so honest network jitter does not trip it — only true wedges do.
_POLL_WATCHDOG_MARGIN_SEC = 30

# Filename of the per-role cold-start flag inside ``workspace/.minionsos/``.
# Presence of this file means the cold_start_hint has already been emitted
# for this role and must not fire again — see Issue #35.
_COLD_START_FLAG_NAME = "cold_start_hint_emitted"

# Stable synthetic event returned just before the prompt-cache TTL cliff.
# Byte-for-byte identical every time so the conversation tail that follows
# it stays cacheable across the next several turns. Any drift here (port
# number, timestamp, counter) defeats the cache it is meant to refresh.
_KEEPALIVE_EVENT: dict[str, Any] = {
    "event": {
        "type": "cache_keepalive",
        "task_id": "",
        "payload": {},
    },
    "suggested_action": (
        "Cache refresh — no real work pending. The ONLY action permitted "
        "this turn is: reply 'ack' (literal three characters) and call "
        "mos_await_events(). Do not analyze, do not plan, do not think "
        "out loud, do not write to the Draft, do not send EACN messages. "
        "mos_await_events is the one tool you must call; nothing else. "
        "Ending the turn without calling mos_await_events stops the role "
        "silently and kills the cache."
    ),
    "suggested_tool": "mos_await_events",
    "suggested_params": {},
    "urgency": "low",
}


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError(
            "MINIONS_PROJECT_PORT not set. mos_await_events requires this environment variable."
        )
    return int(raw)


def _env_agent_id() -> str:
    val = os.environ.get("MINIONS_AGENT_ID", "")
    if not val:
        raise RuntimeError(
            "MINIONS_AGENT_ID not set. mos_await_events requires this environment variable."
        )
    return val


def _env_workspace() -> Path | None:
    val = os.environ.get("MINIONS_WORKSPACE", "")
    return Path(val) if val else None


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


# ─── Heartbeat (silent, zero LLM tokens) ───────────────────────────────


def _touch_heartbeat(workspace: Path | None, agent_id: str) -> None:
    """Update workspace heartbeat file. Git diff = alive. No LLM cost."""
    if workspace is None:
        return
    hb_path = workspace / ".minionsos" / "heartbeat"
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent_id": agent_id,
        "alive_at": datetime.now(tz=UTC).isoformat(),
        "pid": os.getpid(),
    }
    tmp = hb_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, hb_path)


# ─── Event annotation (aligned with eacn3_await_events output) ──────────


def _build_suggested_action(event: dict[str, Any]) -> dict[str, Any]:
    """Annotate a raw EACN3 event. Same format as eacn3_await_events."""
    etype = event.get("type", "")
    task_id = event.get("task_id", "")
    payload = event.get("payload", {})

    if etype == "task_broadcast":
        domains = payload.get("domains", [])
        budget = payload.get("budget", "?")
        return {
            "suggested_action": (
                f"New task in [{', '.join(domains)}] budget={budget}. Evaluate and bid."
            ),
            "suggested_tool": "eacn3_submit_bid",
            "suggested_params": {"task_id": task_id},
            "urgency": "high",
        }
    elif etype == "direct_message":
        sender = payload.get("from", "?")
        content_preview = str(payload.get("content", ""))[:200]
        return {
            "suggested_action": (f'Message from {sender}: "{content_preview}". Reply.'),
            "suggested_tool": "eacn3_send_message",
            "suggested_params": {"to_agent_id": sender, "task_id": task_id},
            "urgency": "high",
        }
    elif etype == "subtask_completed":
        subtask_id = payload.get("subtask_id", task_id)
        return {
            "suggested_action": (f"Subtask {subtask_id} completed. Fetch results."),
            "suggested_tool": "eacn3_get_task_results",
            "suggested_params": {"task_id": str(subtask_id)},
            "urgency": "high",
        }
    elif etype == "bid_result":
        accepted = payload.get("accepted", False)
        if accepted:
            return {
                "suggested_action": (f"Bid accepted on {task_id}. Start working."),
                "suggested_tool": "eacn3_get_task",
                "suggested_params": {"task_id": task_id},
                "urgency": "high",
            }
        reason = payload.get("reason", "unknown")
        return {
            "suggested_action": (f"Bid rejected on {task_id}. Reason: {reason}."),
            "suggested_tool": None,
            "suggested_params": {},
            "urgency": "low",
        }
    elif etype == "bid_request_confirmation":
        return {
            "suggested_action": (f"Bid on {task_id} exceeded budget. Approve or reject."),
            "suggested_tool": "eacn3_confirm_budget",
            "suggested_params": {"task_id": task_id},
            "urgency": "high",
        }
    elif etype == "result_submitted":
        submitter = payload.get("agent_id", "?")
        return {
            "suggested_action": (
                f"Agent {submitter} submitted result for {task_id}. Review and select."
            ),
            "suggested_tool": "eacn3_get_task_results",
            "suggested_params": {"task_id": task_id},
            "urgency": "high",
        }
    elif etype == "task_collected":
        return {
            "suggested_action": (f"Task {task_id}: all executors done. Retrieve and select."),
            "suggested_tool": "eacn3_get_task_results",
            "suggested_params": {"task_id": task_id},
            "urgency": "medium",
        }
    elif etype == "discussion_update":
        return {
            "suggested_action": (f"New clarification on task {task_id}. Review context."),
            "suggested_tool": "eacn3_get_task",
            "suggested_params": {"task_id": task_id},
            "urgency": "medium",
        }
    elif etype == "task_timeout":
        return {
            "suggested_action": (f"Task {task_id} timed out. No action needed."),
            "suggested_tool": None,
            "suggested_params": {},
            "urgency": "low",
        }
    elif etype == "skills_updated":
        return {
            "suggested_action": (
                "New skills admitted to your skills directory. "
                "Run /reload-skills to pick them up without restarting."
            ),
            "suggested_tool": None,
            "suggested_params": {},
            "urgency": "medium",
        }
    else:
        return {
            "suggested_action": f'Event "{etype}" on {task_id}.',
            "suggested_tool": "eacn3_get_task",
            "suggested_params": {"task_id": task_id},
            "urgency": "low",
        }


# ─── Idle check (aligned with eacn3_next idle logic) ───────────────────


def _query_agent_tasks(
    port: int,
    agent_id: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Query EACN3 for this agent's task state. Returns (active, delegated, completed)."""
    base = _base_url(port)
    active: list[dict] = []
    delegated: list[dict] = []
    completed: list[dict] = []
    try:
        resp = httpx.get(
            f"{base}/api/tasks",
            params={"limit": 50, "order": "desc"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            for task in resp.json():
                if not isinstance(task, dict):
                    continue
                status = task.get("status", "")
                initiator = task.get("initiator_id", "")
                bids = task.get("bids", [])
                is_executor = any(
                    b.get("agent_id") == agent_id for b in bids if isinstance(b, dict)
                )
                if is_executor and status in ("bidding", "unclaimed"):
                    active.append(task)
                elif initiator == agent_id and status not in (
                    "completed",
                    "no_one",
                ):
                    delegated.append(task)
                elif initiator == agent_id and status in (
                    "awaiting_retrieval",
                    "completed",
                ):
                    completed.append(task)
    except Exception as exc:
        logger.debug("idle check task query failed: %s", exc)
    return active, delegated, completed


def _query_unanswered_messages(
    port: int,
    agent_id: str,
) -> list[str]:
    """Check for unanswered incoming messages. Returns list of sender agent_ids."""
    # EACN3 doesn't have a direct "unanswered messages" endpoint.
    # We check open tasks where we are initiator and look for discussion updates,
    # or rely on the event queue (which we already drained). For now, return
    # empty — this can be enriched when message session state is accessible.
    return []


def _query_biddable_tasks(
    port: int,
    agent_id: str,
) -> list[dict]:
    """Query open tasks this agent has NOT yet bid on and could potentially claim.

    This is the key signal missing from the original idle_check: without it, a
    role can sit idle while work matching its domains is sitting unclaimed on the
    network.  We use the /api/tasks/open endpoint (same as eacn3_list_open_tasks)
    and filter out tasks where:
    - This agent is already the initiator (own tasks).
    - This agent has already submitted a bid (already knows about it).
    Returns up to 5 candidates so the idle_check prompt stays concise.
    """
    base = _base_url(port)
    biddable: list[dict] = []
    try:
        resp = httpx.get(
            f"{base}/api/tasks/open",
            timeout=5.0,
        )
        if resp.status_code != 200:
            return biddable
        for task in resp.json():
            if not isinstance(task, dict):
                continue
            # Skip tasks initiated by this agent
            if task.get("initiator_id") == agent_id:
                continue
            # Skip tasks where this agent already has a bid
            bids = task.get("bids", [])
            already_bid = any(b.get("agent_id") == agent_id for b in bids if isinstance(b, dict))
            if already_bid:
                continue
            biddable.append(task)
            if len(biddable) >= 5:
                break
    except Exception as exc:
        logger.debug("idle check biddable-tasks query failed: %s", exc)
    return biddable


def _build_idle_check(
    port: int,
    agent_id: str,
) -> dict[str, Any] | None:
    """Build a synthetic idle_check event if there is actionable work.

    Returns None if truly nothing to do (no-idle → swallow silently).
    Logic mirrors eacn3_next's idle branch (server.ts:1562-1607).

    Extended (Issue #39): now also queries for open tasks this agent has not yet
    bid on, so a role in idle state receives a concrete signal about available
    collaboration opportunities — not just a generic suggestion to call
    eacn3_list_open_tasks.
    """
    active, delegated, completed = _query_agent_tasks(port, agent_id)
    unanswered = _query_unanswered_messages(port, agent_id)
    biddable = _query_biddable_tasks(port, agent_id)

    prompts: list[str] = []

    if active:
        ids = ", ".join(t.get("id", "?") for t in active[:5])
        prompts.append(
            f"You have {len(active)} task(s) in progress ({ids}). Have you finished them?"
        )
    if delegated:
        ids = ", ".join(t.get("id", "?") for t in delegated[:5])
        prompts.append(
            f"You delegated {len(delegated)} task(s) ({ids}). Have you checked their results?"
        )
    if completed:
        ids = ", ".join(t.get("id", "?") for t in completed[:5])
        prompts.append(
            f"You have {len(completed)} completed task(s) ({ids}). Have you reviewed all results?"
        )
    if unanswered:
        prompts.append(
            f"Unanswered messages from {len(unanswered)} agent(s)"
            f" ({', '.join(unanswered[:5])}). Reply?"
        )
    if biddable:
        ids = ", ".join(t.get("id", "?") for t in biddable)
        domains_preview = ", ".join(d for t in biddable[:2] for d in (t.get("domains") or [])[:2])
        prompts.append(
            f"{len(biddable)} open task(s) you haven't bid on yet"
            f" ({ids}; domains: {domains_preview or 'various'})."
            f" Evaluate and bid if relevant."
        )

    if not prompts:
        # Truly nothing — no-idle. Return None to signal "keep waiting."
        return None

    # Always append reflective prompts (same as eacn3_next)
    prompts.append(
        "Could another agent handle part of your current work better?"
        " Consider delegating via eacn3_create_task."
    )

    # Pick the most actionable item for suggested_tool.
    # Biddable tasks take priority over generic delegation reminder —
    # a concrete task_id is more actionable than a list query.
    if biddable:
        suggested_tool = "eacn3_submit_bid"
        suggested_params = {"task_id": biddable[0].get("id", "")}
    elif delegated:
        suggested_tool = "eacn3_get_task_results"
        suggested_params = {"task_id": delegated[0].get("id", "")}
    elif completed:
        suggested_tool = "eacn3_get_task_results"
        suggested_params = {"task_id": completed[0].get("id", "")}
    elif unanswered:
        suggested_tool = "eacn3_send_message"
        suggested_params = {"to_agent_id": unanswered[0]}
    else:
        suggested_tool = "eacn3_list_open_tasks"
        suggested_params = {}

    return {
        "event": {
            "type": "idle_check",
            "task_id": "",
            "payload": {
                "active_tasks": [t.get("id") for t in active[:5]],
                "delegated_tasks": [t.get("id") for t in delegated[:5]],
                "completed_tasks": [t.get("id") for t in completed[:5]],
                "unanswered_from": unanswered[:5],
                "biddable_tasks": [t.get("id") for t in biddable],
                "prompts": prompts,
            },
        },
        "suggested_action": " | ".join(prompts[:2]),
        "suggested_tool": suggested_tool,
        "suggested_params": suggested_params,
        "urgency": "medium",
    }


# ─── Cold-start self-initiation (Issue #35) ─────────────────────────────


def _cold_start_flag_path(workspace: Path | None) -> Path | None:
    if workspace is None:
        return None
    return workspace / ".minionsos" / _COLD_START_FLAG_NAME


def _has_event_history(port: int, agent_id: str) -> bool:
    """True if this role has ever drained a real EACN event in any prior life.

    The events jsonl is the durable, sync-written record of every event
    surfaced to this role across all respawns (see ``events_log.py``).
    A non-empty file means the role has already participated in the
    network at some point — it is not a cold-start candidate, even if
    its workspace flag is missing (e.g. workspace recreated after a
    manual cleanup).
    """
    try:
        from minions.tools import events_log

        path = events_log.event_log_path(port, agent_id)
        return path.exists() and path.stat().st_size > 0
    except Exception as exc:
        logger.debug("cold-start event-history probe failed: %s", exc)
        return False


def _build_cold_start_hint(
    port: int,
    agent_id: str,
    workspace: Path | None,
) -> dict[str, Any] | None:
    """One-shot proactive collaboration nudge for a freshly-spawned role.

    Fires at most once per role lifetime, only when ALL hold:
    - The idle-check found no actionable work (caller's precondition).
    - The role has no event history on disk (never drained a real event).
    - The workspace flag file does not exist (hint not yet emitted).
    - A workspace path is configured (otherwise we cannot persist the flag,
      and a stateless hint would re-fire every empty cycle — far worse than
      not firing at all).

    Writing the flag BEFORE returning is critical: if the role crashes
    after receiving the hint but before producing any action, the next
    role process must not re-fire (the hint is a soft nudge, not a
    correctness mechanism).
    """
    flag_path = _cold_start_flag_path(workspace)
    if flag_path is None:
        return None
    if flag_path.exists():
        return None
    if _has_event_history(port, agent_id):
        # Established role with history but no current work — silent wait
        # is the correct behaviour. Mark the flag so we don't probe again.
        try:
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.write_text(
                f"skipped: prior event history present at {datetime.now(tz=UTC).isoformat()}\n",
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("cold-start flag write (skip-path) failed: %s", exc)
        return None

    try:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(
            f"emitted at {datetime.now(tz=UTC).isoformat()} for {agent_id}\n",
            encoding="utf-8",
        )
    except Exception as exc:
        # If we cannot persist the flag, do NOT emit the hint — a hint
        # without a flag would re-fire every cycle and burn one assistant
        # turn each ~5 minutes for the rest of the role's life.
        logger.warning(
            "cold-start flag write failed; suppressing hint for agent=%s: %s",
            agent_id,
            exc,
        )
        return None

    return {
        "event": {
            "type": "cold_start_hint",
            "task_id": "",
            "payload": {
                "hint": (
                    "You are a fresh role with no pending work and no "
                    "event history. The team will not move unless someone "
                    "moves first. Read project CLAUDE.md and any "
                    "branches/shared/handoffs/ files, then proactively: "
                    "(a) eacn3_send_message a relevant peer to propose "
                    "collaboration, or (b) eacn3_create_task to publish "
                    "a piece of work the team needs. Wisdom emerges from "
                    "collaboration, not from waiting. This nudge fires "
                    "exactly once per role lifetime — after this turn, "
                    "the system reverts to fully event-driven behaviour."
                ),
            },
        },
        "suggested_action": (
            "Cold start: bootstrap your participation. Send a message to a "
            "peer or create a task — do not return to await_events without "
            "taking at least one autonomous step."
        ),
        "suggested_tool": "eacn3_send_message",
        "suggested_params": {},
        "urgency": "medium",
    }


# ─── Core poll (aligned with eacn3_get_events drain semantics) ──────────


@contextmanager
def _poll_watchdog(timeout_sec: float, port: int, agent_id: str):
    """Wall-clock kill-switch for a single long-poll call.

    Issue #37: a hung backend (uvicorn accepted the connection but never
    responded) or a half-open socket can keep httpx blocked past every
    library-level timeout. SIGALRM fires from the kernel regardless of what
    Python is doing, so the poll always returns control to the event loop
    within ``timeout_sec``.

    SIGALRM is a main-thread, POSIX-only mechanism. On Windows or when the
    tool is invoked from a worker thread (e.g. some MCP transports) we fall
    back to a no-op — httpx's structured Timeout is the only guard in that
    case, which is the same behaviour as before this fix.
    """
    can_alarm = hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()
    if not can_alarm:
        yield
        return

    def _on_alarm(signum, frame):
        raise TimeoutError(
            f"mos_await_events poll watchdog tripped after {timeout_sec:.0f}s "
            f"(port={port}, agent={agent_id})"
        )

    prev_handler = signal.signal(signal.SIGALRM, _on_alarm)
    # signal.alarm() takes integer seconds; round up so we never undershoot.
    prev_remaining = signal.alarm(max(1, int(timeout_sec + 0.999)))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev_handler)
        # Restore any prior alarm the caller had pending. signal.alarm(0)
        # already cleared ours; this re-arms theirs if they had one.
        if prev_remaining > 0:
            signal.alarm(prev_remaining)


def _poll_once(
    port: int,
    agent_id: str,
    timeout_secs: int = EACN3_POLL_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Single HTTP long-poll. Same as eacn3_get_events drain-on-read.

    GitHub Issue #28: filter ``cache_keepalive``-typed events out of the
    upstream payload. The synthetic in-process keepalive (this module's
    ``_KEEPALIVE_EVENT``) is a deliberate cache refresh; an upstream-
    emitted ``cache_keepalive`` is not — it would fire on every quiet
    cycle and burn one assistant turn per ~4 min interval. The events log
    on disk shows we never actually see one in production, but defence-
    in-depth: if EACN3 ever starts emitting one we don't want to wake
    the model on it.
    """
    url = f"{_base_url(port)}/api/events/{agent_id}"
    # Issue #37: structured httpx timeout (connect/read/write/pool all bounded
    # independently) defeats a half-open socket that would slip past a single
    # combined timeout, and SIGALRM is a kernel-level backstop that fires even
    # if httpx is wedged below the Python event loop. Together they guarantee
    # this function returns (success or exception) within the watchdog window.
    watchdog_sec = timeout_secs + _POLL_WATCHDOG_MARGIN_SEC
    http_timeout = httpx.Timeout(
        connect=10.0,
        read=timeout_secs + 10.0,
        write=10.0,
        pool=10.0,
    )
    with _poll_watchdog(watchdog_sec, port, agent_id):
        try:
            resp = httpx.get(
                url,
                params={"timeout": min(timeout_secs, EACN3_POLL_TIMEOUT_SEC)},
                timeout=http_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "mos_await_events poll failed port=%d agent=%s: %s",
                port,
                agent_id,
                exc,
            )
            raise RuntimeError(f"EACN3 poll failed: {exc}") from exc
    raw_events = data.get("events") or data.get("messages") or []
    # Issue #47: hydrate ${PROJECT_DIR} placeholders back to absolute paths
    # using the live project_port -> project_dir mapping. Server stays
    # project-agnostic; substitution only happens here at the role-side
    # boundary, where we know which project_port owns the queue.
    try:
        from minions.lifecycle._path_placeholder import decode_project_paths
        from minions.paths import project_dir

        raw_events = decode_project_paths(raw_events, str(project_dir(port)))
    except Exception as exc:
        logger.debug("decode_project_paths failed in mos_await_events: %s", exc)
    out: list[dict[str, Any]] = []
    # Issue #47: decode ${PROJECT_DIR} placeholders to the live project_dir
    # before annotation / return. Done MinionsOS-side because the EACN3
    # server is project-agnostic and does not know the port→project_dir
    # mapping.
    try:
        pdir = str(_project_dir(port))
    except Exception:
        pdir = ""
    for evt in raw_events:
        if not isinstance(evt, dict):
            continue
        if pdir:
            with suppress(Exception):
                evt = decode_project_paths(evt, pdir)
        # Drop upstream-emitted cache_keepalive frames silently. The
        # synthetic one this module fires (when keepalive cliff hits) is
        # the only legitimate keepalive path; anything else is noise.
        inner = evt.get("event")
        if isinstance(inner, dict) and inner.get("type") == "cache_keepalive":
            logger.debug("mos_await_events: dropped upstream cache_keepalive from poll")
            continue
        if evt.get("type") == "cache_keepalive":
            logger.debug("mos_await_events: dropped upstream cache_keepalive (flat shape)")
            continue
        out.append(evt)
    return out


# ─── Public entry point ─────────────────────────────────────────────────


def await_events() -> dict[str, Any]:
    """Block until EACN3 delivers actionable content, then return it.

    The LLM is suspended while this blocks — zero token cost for:
    - 60s HTTP long-polls (repeating)
    - Heartbeat file writes (every cycle)
    - No-idle checks (swallowed silently)

    Tokens are consumed only when this function returns with content.

    Returns:
        {count: N, events: [{event, suggested_action, suggested_tool,
                             suggested_params, urgency}, ...]}
        where N > 0 always. Events may be real EACN3 events, a synthetic
        idle_check (after ~5 min of silence, if there is unfinished work),
        or a synthetic cache_keepalive (after ``cache_keepalive_seconds``
        of wall-clock silence, regardless of work state — this keeps the
        Role's 1h prompt cache from expiring).
    """
    port = _env_port()
    agent_id = _env_agent_id()
    workspace = _env_workspace()

    # Wall-clock since this Role last produced an LLM turn. Used to refresh
    # the prompt cache (5 min default; lifted to 1 h when the env var
    # ENABLE_PROMPT_CACHING_1H=1 is set in role_launcher and the upstream
    # gateway transmits it) before its cliff. Read knob lazily so a
    # missing/broken gru.yaml does not break the event loop — keepalive
    # is an optimization, not a correctness requirement.
    keepalive_seconds = _load_keepalive_seconds()
    started_monotonic = time.monotonic()

    consecutive_empty = 0

    def _return(events_payload: list[dict[str, Any]], *, real: bool) -> dict[str, Any]:
        """Wrap the return path with the Draft-discipline audit hook.

        At every return, snapshot the per-role audit state, decide whether
        the previous cycle warrants a Draft-discipline reminder, and reset
        the counters for the next cycle. When *real* is False (a
        cache_keepalive or no-work return), draft_audit is skipped
        entirely — the keepalive ack path must have zero side effects so
        a transient FS issue (e.g. concurrent draft writes from peer
        roles) cannot wedge the await_events tool call (Issue #36 FM2).
        Skipping also preserves ``last_delivery_was_real`` across
        keepalives, so the next *real* return correctly fires (or
        suppresses) the discipline reminder based on the pre-keepalive
        cycle, not on the keepalive itself. Consistent with Issue #15
        wedge protection.
        """
        snapshot = None
        if real:
            try:
                from minions.tools import draft_audit as _draft_audit

                snapshot = _draft_audit.take_snapshot_and_reset(
                    port, agent_id, returning_real_events=True
                )
            except Exception as exc:
                logger.debug("draft_audit snapshot failed: %s", exc)
                snapshot = None
        if real and snapshot is not None and snapshot.reminder_due and events_payload:
            # Issue #39: Draft-discipline reminder must NOT overwrite high-urgency
            # EACN collaboration signals. A task_broadcast or direct_message is
            # time-sensitive — prepending a Memory reminder visually de-prioritizes
            # the collaboration action. For these event types, append the reminder
            # instead (or skip entirely if urgency=high). For lower-urgency events
            # (idle_check, discussion_update), prepending is fine.
            first = events_payload[0]
            event_type = ""
            inner = first.get("event")
            if isinstance(inner, dict):
                event_type = inner.get("type", "")
            urgency = first.get("urgency", "low")
            high_priority_collab = (
                event_type
                in (
                    "task_broadcast",
                    "direct_message",
                    "bid_result",
                )
                or urgency == "high"
            )

            reminder = (
                "[Draft-discipline reminder] Your previous cycle handled real "
                "events but wrote no Draft node. If anything you decided or "
                "produced is worth remembering, call mos_draft_append BEFORE "
                "mos_await_events again. Published artifacts are not a "
                "substitute — the Draft is the cold-start trail other roles "
                "(and your post-compact self) read.\n\n"
            )
            existing = str(first.get("suggested_action", ""))
            if high_priority_collab:
                # Append reminder after the collaboration signal
                first["suggested_action"] = existing + "\n\n" + reminder
            else:
                # Prepend for lower-priority events (idle_check, etc.)
                first["suggested_action"] = reminder + existing
        # Context-pressure annotation (issue #38). Read the role's session
        # JSONL tail to compute avg cache_read over recent assistant turns;
        # if it has bloated past threshold, advise mos_compact_context via
        # the suggested_action channel. Skipped for keepalive/empty returns
        # so the keepalive ack path stays byte-stable (cache safety).
        if real and events_payload:
            try:
                from minions.tools import context_pressure as _ctx_pressure

                pressure = _ctx_pressure.probe(workspace=workspace)
                if pressure.level != "low":
                    _ctx_pressure.annotate_event(events_payload[0], pressure)
            except Exception as exc:
                # Pressure detection is advisory only — never block the event
                # path on its failure.
                logger.debug("context_pressure probe failed: %s", exc)
        return {"count": len(events_payload), "events": events_payload}

    # Pattern B: idle-window preemptive compact (issue #38).
    # Before entering the poll loop, probe context pressure once. If pressure
    # is HIGH and no cooldown is active AND the EACN queue is currently empty
    # (peek without dequeue), this is the cleanest time to schedule /compact:
    # the role is between work batches, no events have been pulled off the
    # queue (so nothing gets stranded mid-cycle), and the next wake will run
    # on a freshly compressed prefix.
    #
    # If the queue is NOT empty, deliver the events with Pattern A
    # annotation in _return — Pattern A is the right path when there IS
    # real work to surface alongside the compact directive.
    try:
        from minions.tools import context_pressure as _ctx_pressure

        entry_pressure = _ctx_pressure.probe(workspace=workspace)
        if entry_pressure.level == "high" and not entry_pressure.on_cooldown:
            peeked = _poll_once(port, agent_id)
            _touch_heartbeat(workspace, agent_id)
            if peeked:
                from minions.tools import events_log as _events_log

                _events_log.append_events(port, agent_id, peeked)
                events_payload = []
                for evt in peeked:
                    annotation = _build_suggested_action(evt)
                    events_payload.append({**evt, **annotation})
                return _return(events_payload, real=True)
            # Queue empty — schedule compact preemptively.
            scheduled = _schedule_preemptive_compact(port, agent_id)
            if scheduled:
                synthetic = {
                    "event": {
                        "type": "context_pressure_compact",
                        "task_id": "",
                        "payload": entry_pressure.to_dict(),
                    },
                    "context_pressure": entry_pressure.to_dict(),
                    "suggested_action": (
                        f"⚠ CONTEXT PRESSURE HIGH (avg cache_read "
                        f"{entry_pressure.avg_cr_recent:,} over last "
                        f"{entry_pressure.window_turns} turns). EACN queue is "
                        f"idle. /compact has been scheduled preemptively — it "
                        f"will fire as the next user input. \n\n"
                        f"IMPORTANT: if you carry any in-flight plan or "
                        f"unpersisted note that the compact summary cannot "
                        f"reconstruct (a half-thought decision, an unwritten "
                        f"hypothesis, a deferred next step), call "
                        f"mos_draft_append RIGHT NOW with metadata."
                        f"pending_plan=true BEFORE the /compact lands. "
                        f"Anything not on disk before /compact is gone.\n\n"
                        f"If you have nothing to persist: STOP NOW — do not "
                        f"call any more tools, do not produce text. After the "
                        f"compact summary loads, your first action is "
                        f"mos_draft_summary() then mos_await_events() to "
                        f"resume in compressed context."
                    ),
                }
                return _return([synthetic], real=False)
            # If schedule failed, fall through to normal poll. Pattern A
            # in _return will still annotate any subsequent events.
    except Exception as exc:
        logger.debug("context_pressure entry probe failed: %s", exc)

    while True:
        # Early cache-keepalive cliff check: do BEFORE the next long-poll, not
        # only after. The long-poll itself blocks for ~60s, so checking only
        # at the bottom of the loop means a config of cache_keepalive_seconds
        # < 60 is dead, and a config near the cliff (e.g. 240) only has 60s
        # safety margin minus poll latency. Checking up-front gives the full
        # configured value as headroom.
        if keepalive_seconds > 0 and (time.monotonic() - started_monotonic) >= keepalive_seconds:
            _touch_heartbeat(workspace, agent_id)
            return _return([_KEEPALIVE_EVENT], real=False)

        events = _poll_once(port, agent_id)
        _touch_heartbeat(workspace, agent_id)
        # Sync-write durable copy BEFORE the LLM ever sees the events.
        # If anything below this point crashes, the events are still on
        # disk under project_{port}/events/{agent_id}.jsonl, available
        # for post-mortem reconstruction.
        if events:
            from minions.tools import events_log as _events_log

            _events_log.append_events(port, agent_id, events)

        if events:
            consecutive_empty = 0
            annotated = []
            for evt in events:
                annotation = _build_suggested_action(evt)
                annotated.append({"event": evt, **annotation})
            return _return(annotated, real=True)

        consecutive_empty += 1

        if consecutive_empty >= IDLE_CHECK_THRESHOLD:
            idle_event = _build_idle_check(port, agent_id)
            consecutive_empty = 0  # reset regardless of result

            if idle_event is not None:
                return _return([idle_event], real=True)
            # no-idle: nothing in the task/message state. Before silently
            # continuing, check whether this is a fresh role that has never
            # received any real events — if so, fire the one-shot cold-start
            # nudge (Issue #35) so the team can self-initiate without a
            # seed task from Gru.
            cold_start_event = _build_cold_start_hint(port, agent_id, workspace)
            if cold_start_event is not None:
                return _return([cold_start_event], real=True)
            # Either established role, hint already fired, or no workspace
            # configured — keep polling silently.

        # Cache-keepalive cliff guard. Independent of idle_check: even when
        # there is genuinely no work, we must surface a tiny LLM turn before
        # the prompt-cache TTL expires, or the next real event will eat
        # a full system-prompt + tool-definitions cold start (~50k input
        # tokens uncached). The synthetic event payload is constant so the
        # post-keepalive conversation tail stays cacheable.
        if keepalive_seconds > 0 and (time.monotonic() - started_monotonic) >= keepalive_seconds:
            return _return([_KEEPALIVE_EVENT], real=False)


def _schedule_preemptive_compact(port: int, agent_id: str) -> bool:
    """Schedule /compact via tmux send-keys without going through mos_compact_context.

    This is the Pattern B path (issue #38): when ``await_events`` detects
    high context pressure on entry AND the EACN queue is idle, we want to
    schedule a compact directly from inside the tool, NOT via a Role-side
    ``mos_compact_context`` call. Reasons:

    - We are already on the Role's stack — calling mos_compact_context
      from inside await_events would mean importing tools that touch the
      Draft, journal, etc. Better to write the journal entry inline and
      re-use the same tmux-send mechanism.
    - The Role is between work batches (queue empty), so there are no
      pending_plans to persist. The cognitive-checkpoint discipline does
      not apply here.

    Writes a journal entry tagged ``op="compact_preemptive"`` so context_pressure
    cooldown sees it and stops re-firing.
    """
    import json as _json
    import subprocess as _subprocess
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    role = os.environ.get("MINIONS_ROLE_NAME", agent_id)
    session = f"mos-{port}-{role}"

    # Journal first so cooldown is set even if tmux fails.
    try:
        from minions.paths import project_shared_subdir

        draft_dir = project_shared_subdir(port, "draft")
        draft_dir.mkdir(parents=True, exist_ok=True)
        journal_path = draft_dir / "journal.jsonl"
        entry = {
            "op": "compact",
            "role": role,
            "reason": "context_pressure_preemptive",
            "timestamp": _datetime.now(_UTC).isoformat(timespec="seconds"),
            "trigger": "await_events_entry_probe",
        }
        with journal_path.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("preemptive compact: journal write failed: %s", exc)

    # tmux send-keys "/compact" + Enter
    try:
        _subprocess.run(
            ["tmux", "send-keys", "-t", session, "-l", "/compact"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        _subprocess.run(
            ["tmux", "send-keys", "-t", session, "Enter"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (OSError, _subprocess.SubprocessError) as exc:
        logger.warning("preemptive compact: tmux send-keys failed for %s: %s", session, exc)
        return False


def _load_keepalive_seconds() -> int:
    """Read cache_keepalive_seconds from gru.yaml, defaulting to off on error.

    Reading the config lazily (not at module import) keeps the await_events
    tool decoupled from gru.yaml availability — a Role process can still
    poll EACN3 even if its config file is malformed; it just loses the
    keepalive optimization.
    """
    try:
        from minions.config import load_gru_config

        return int(load_gru_config().cache_keepalive_seconds)
    except Exception as exc:
        logger.debug("cache_keepalive_seconds load failed; keepalive disabled: %s", exc)
        return 0
