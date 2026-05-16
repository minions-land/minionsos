"""mos_await_events — Role-facing MCP tool for EACN3 event polling.

Wraps ``GET /api/events/{agent_id}?timeout=60`` in an internal loop that
only returns to the LLM when there is actionable content:

1. Real EACN3 events → return immediately with annotations.
2. After 5 consecutive empty polls (~5 min), run an idle check:
   - Query task state and message sessions (same logic as eacn3_next idle).
   - If actionable items found → return as synthetic idle_check event.
   - If nothing (no-idle) → swallow silently, continue polling.
3. Heartbeat file updated every cycle (git-visible liveness, zero LLM tokens).

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EACN3_POLL_TIMEOUT_SEC = 60
IDLE_CHECK_THRESHOLD = 5  # consecutive empty polls before idle check


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


# ─── Core poll (aligned with eacn3_get_events drain semantics) ──────────


def _poll_once(
    port: int,
    agent_id: str,
    timeout_secs: int = EACN3_POLL_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Single HTTP long-poll. Same as eacn3_get_events drain-on-read."""
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
    return [e for e in raw_events if isinstance(e, dict)]


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
        where N > 0 always. Events may be real EACN3 events or a synthetic
        idle_check (after ~5 min of silence, if there is unfinished work).
    """
    port = _env_port()
    agent_id = _env_agent_id()
    workspace = _env_workspace()

    consecutive_empty = 0

    while True:
        events = _poll_once(port, agent_id)
        _touch_heartbeat(workspace, agent_id)

        if events:
            consecutive_empty = 0
            annotated = []
            for evt in events:
                annotation = _build_suggested_action(evt)
                annotated.append({"event": evt, **annotation})
            return {"count": len(annotated), "events": annotated}

        consecutive_empty += 1

        if consecutive_empty >= IDLE_CHECK_THRESHOLD:
            idle_event = _build_idle_check(port, agent_id)
            consecutive_empty = 0  # reset regardless of result

            if idle_event is not None:
                return {"count": 1, "events": [idle_event]}
            # no-idle: truly nothing to do. Swallow silently, keep polling.
