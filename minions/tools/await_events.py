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
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EACN3_POLL_TIMEOUT_SEC = 60
IDLE_CHECK_THRESHOLD = 5  # consecutive empty polls before idle check

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
        "Cache keepalive — no work to do. Reply with a single short ack "
        "(e.g. 'ack') and immediately call mos_await_events() again. Do "
        "not write to the Draft, do not send EACN messages, do not "
        "invoke any other tool."
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


def _build_idle_check(
    port: int,
    agent_id: str,
) -> dict[str, Any] | None:
    """Build a synthetic idle_check event if there is actionable work.

    Returns None if truly nothing to do (no-idle → swallow silently).
    Logic mirrors eacn3_next's idle branch (server.ts:1562-1607).
    """
    active, delegated, completed = _query_agent_tasks(port, agent_id)
    unanswered = _query_unanswered_messages(port, agent_id)

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

    if not prompts:
        # Truly nothing — no-idle. Return None to signal "keep waiting."
        return None

    # Always append reflective prompts (same as eacn3_next)
    prompts.append(
        "Could another agent handle part of your current work better?"
        " Consider delegating via eacn3_create_task."
    )

    # Pick the most actionable item for suggested_tool
    if delegated:
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
    try:
        resp = httpx.get(
            url,
            params={"timeout": min(timeout_secs, EACN3_POLL_TIMEOUT_SEC)},
            timeout=timeout_secs + 10.0,
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
    out: list[dict[str, Any]] = []
    for evt in raw_events:
        if not isinstance(evt, dict):
            continue
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
            reminder = (
                "[Draft-discipline reminder] Your previous cycle handled real "
                "events but wrote no Draft node. If anything you decided or "
                "produced is worth remembering, call mos_draft_append BEFORE "
                "mos_await_events again. Published artifacts are not a "
                "substitute — the Draft is the cold-start trail other roles "
                "(and your post-compact self) read.\n\n"
            )
            first = events_payload[0]
            existing = str(first.get("suggested_action", ""))
            first["suggested_action"] = reminder + existing
        return {"count": len(events_payload), "events": events_payload}

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
