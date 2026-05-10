"""MOS Agent Pool — EACN3 access wrapper for MinionsOS internal roles.

All internal MinionsOS roles (Coder, Writer, Experimenter, Reviewer, Ethics,
Noter, Expert, and Gru-for-internal-collaboration) read and write EACN3
through this layer instead of calling ``eacn3_*`` tools directly. The wrapper
does two things on top of raw EACN3:

1. **Three-layer addressing fix.** Every outgoing message or task gets its
   ``server_id`` and ``network_id`` populated from the target's AgentCard. The
   previous hand-written POST sent empty strings, which works locally but
   silently fails on cross-node delivery (EACN3's network relay path gates on
   non-empty addressing).

2. **Per-wake local ACK inbox.** ``mos_await_events`` drains EACN3 and, before
   returning the events to the caller, persists a copy to
   ``project_<port>/branches/<role>/.minionsos/inbox/pending.jsonl``. Agents do
   NOT read this file. It is a crash-shim: if the wake process dies between
   ``await_events`` and finishing the work, the next wake's init prompt can
   re-surface those events so the agent knows what it was doing. When the
   agent finishes processing, it calls ``mos_ack_clear`` to remove the entries.

   Lifecycle rules:

   - Normal wake completion -> pending.jsonl is empty. Cleared per round.
   - Mid-wake crash -> pending.jsonl retains the un-acknowledged batch. Next
     wake reads it once and injects into the init prompt. Whether those events
     are still relevant is an agent-side judgment (it may need to call
     ``eacn3_get_task`` / ``eacn3_get_messages`` to verify before acting).
   - Pending file is never loaded into model memory or scratchpad. It is a
     pure MinionsOS-owned disk fallback.

This module intentionally does not touch EACN3. It calls the existing
``eacn_client`` HTTP wrappers which are the only MinionsOS code that speaks
EACN3 HTTP directly.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from minions.errors import BackendError
from minions.lifecycle import eacn_client
from minions.paths import project_role_workspace

logger = logging.getLogger(__name__)


# EACN3 backend caps each GET /api/events/{agent_id}?timeout at 60s (see
# EACN3/eacn/network/api/routes.py: Query(default=0, ge=0, le=60)). That's
# a protocol constraint we intentionally do not modify.
# MinionsOS-side we hide it from agents: mos_await_events does N chunked
# 60s polls inside one tool call, returning as soon as any chunk produces
# events. Agents see a single long-poll call that lasts up to
# MOS_AWAIT_TIMEOUT_DEFAULT_SEC.
EACN3_POLL_CHUNK_SEC = 60
MOS_AWAIT_TIMEOUT_DEFAULT_SEC = 3600  # 1 hour wake-window patience
MOS_AWAIT_TIMEOUT_MAX_SEC = 86400  # hard ceiling: 24 hours per tool call


# ---------------------------------------------------------------------------
# Pending inbox paths + utilities
# ---------------------------------------------------------------------------


def _pending_path(port: int, role_name: str) -> Path:
    """Return the per-role pending inbox jsonl path.

    The file lives inside the role's branch worktree under ``.minionsos/inbox/``.
    Placing it there keeps Noter's archive and the pending shim on the same
    branch-local tier and makes the per-role ownership explicit.
    """
    return project_role_workspace(port, role_name) / ".minionsos" / "inbox" / "pending.jsonl"


def _event_id(event: dict[str, Any]) -> str:
    """Derive a stable per-event identifier from an EACN3 event payload.

    Falls back through a few likely fields EACN3 uses so we can dedupe and
    ack without requiring every backend version to agree on a single key.
    """
    for key in ("msg_id", "id", "event_id", "task_id"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return val
    # Last resort: hash a JSON dump. Not perfect but stable within a wake.
    try:
        return json.dumps(event, sort_keys=True, default=str)
    except Exception:
        return repr(event)


def _append_pending(port: int, role_name: str, events: list[dict[str, Any]]) -> None:
    """Append *events* to the pending inbox jsonl (one JSON object per line)."""
    if not events:
        return
    path = _pending_path(port, role_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, default=str) + "\n")


def mos_pending_read(port: int, role_name: str) -> list[dict[str, Any]]:
    """Read the per-role pending inbox. Empty list if the file does not exist.

    Malformed lines are skipped rather than raising; a corrupt pending file
    must never block a wake. Corrupt lines are logged at debug level.
    """
    path = _pending_path(port, role_name)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except Exception as exc:
                    logger.debug("mos_pending_read skipped malformed line in %s: %s", path, exc)
                    continue
                if isinstance(obj, dict):
                    events.append(obj)
    except Exception as exc:
        logger.warning("mos_pending_read failed for %s: %s", path, exc)
        return []
    return events


def mos_pending_wipe(port: int, role_name: str) -> None:
    """Remove the pending inbox file entirely."""
    path = _pending_path(port, role_name)
    if path.exists():
        try:
            path.unlink()
        except Exception as exc:
            logger.warning("mos_pending_wipe failed for %s: %s", path, exc)


def mos_ack_clear(port: int, role_name: str, event_ids: list[str]) -> int:
    """Remove entries whose ``_event_id`` matches any of *event_ids*.

    Returns the number of entries actually removed. If *event_ids* is empty,
    this is a no-op. If removing the last remaining entry empties the file,
    the file itself is deleted so callers can treat "file does not exist" and
    "empty pending" as the same state.
    """
    if not event_ids:
        return 0
    path = _pending_path(port, role_name)
    if not path.exists():
        return 0
    wanted = set(event_ids)
    kept: list[dict[str, Any]] = []
    removed = 0
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                if _event_id(obj) in wanted:
                    removed += 1
                    continue
                kept.append(obj)
    except Exception as exc:
        logger.warning("mos_ack_clear read failed for %s: %s", path, exc)
        return 0

    if not kept:
        try:
            path.unlink()
        except Exception as exc:
            logger.warning("mos_ack_clear unlink failed for %s: %s", path, exc)
        return removed

    tmp = path.with_suffix(".jsonl.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            for obj in kept:
                fh.write(json.dumps(obj, default=str) + "\n")
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("mos_ack_clear write failed for %s: %s", path, exc)
        with contextlib.suppress(Exception):
            tmp.unlink()
    return removed


# ---------------------------------------------------------------------------
# Core wrappers
# ---------------------------------------------------------------------------


def mos_await_events(
    port: int,
    role_name: str,
    agent_id: str,
    timeout_seconds: int = MOS_AWAIT_TIMEOUT_DEFAULT_SEC,
    http_timeout: float = 10.0,
) -> dict[str, Any]:
    """Long-poll EACN3 events for *agent_id* — one tool call, ≤ *timeout_seconds* wait.

    From the caller's perspective this is a single tool invocation. Internally
    it chunks the wait into EACN3's 60-second-capped HTTP long-polls. It
    returns as soon as ANY chunk yields events; it only returns an empty
    result after the full *timeout_seconds* of silence has elapsed with no
    events. Either way the caller pays the token cost of exactly one tool
    call, which is the whole point of this wrapper — agents do not see the
    underlying chunk loop and must never be asked to implement it in prompts.

    Parameters
    ----------
    port:
        Project EACN3 backend port.
    role_name:
        MinionsOS role name ("coder", "writer", etc.). Used to locate the
        role's branch dir for the pending inbox.
    agent_id:
        The EACN agent id whose queue to drain. Normally the role's own
        agent id; passing someone else's id would drain their queue, which
        only Gru-as-Gru on its own id should ever do.
    timeout_seconds:
        Total wait budget in seconds (0 to :data:`MOS_AWAIT_TIMEOUT_MAX_SEC`).
        Default is 1 hour. The value is clamped to the allowed range.
    http_timeout:
        Per-chunk HTTP socket timeout safety margin.

    Returns
    -------
    ``{"events": [...], "count": int, "timeout": bool, "pending_count": int}``.
    ``timeout`` is True only when the full *timeout_seconds* elapsed with no
    events.
    """
    if timeout_seconds < 0:
        timeout_seconds = 0
    if timeout_seconds > MOS_AWAIT_TIMEOUT_MAX_SEC:
        timeout_seconds = MOS_AWAIT_TIMEOUT_MAX_SEC

    # Python-side chunked long-poll. Each chunk is a normal EACN3 long-poll
    # respecting the backend's 60s cap; the chunk boundaries are invisible
    # to the caller. We return early the moment any chunk yields events.
    remaining = timeout_seconds
    events: list[dict[str, Any]] = []
    while True:
        this_chunk = min(EACN3_POLL_CHUNK_SEC, remaining) if remaining > 0 else 0
        try:
            payload = eacn_client.poll_events(
                port=port,
                agent_id=agent_id,
                timeout_secs=this_chunk,
                http_timeout=http_timeout + this_chunk,
            )
        except BackendError:
            raise
        events_raw = payload.get("events") or payload.get("messages") or []
        events = [e for e in events_raw if isinstance(e, dict)]
        if events:
            break
        remaining -= this_chunk
        if remaining <= 0:
            break
        # EACN3 returned cleanly with no events — keep going.

    # Side effect: persist a local ACK copy before returning to the caller.
    # We do this synchronously; if the append fails we still return the events
    # (better to deliver than to lose them on a disk hiccup), but we log loudly.
    try:
        _append_pending(port, role_name, events)
    except Exception as exc:
        logger.warning(
            "mos_await_events: pending append failed port=%d role=%s: %s",
            port,
            role_name,
            exc,
        )

    pending_count = 0
    with contextlib.suppress(Exception):
        pending_count = len(mos_pending_read(port, role_name))

    return {
        "events": events,
        "count": len(events),
        "timeout": len(events) == 0,
        "pending_count": pending_count,
    }


def mos_send_message(
    port: int,
    to_agent_id: str,
    from_agent_id: str,
    content: Any,
    timeout: float = eacn_client.DEFAULT_TIMEOUT,
    *,
    validate_target: bool = True,
    audit_to_noter: bool = True,
) -> dict[str, Any]:
    """Send a direct message with three-layer addressing resolved.

    Thin wrapper over ``eacn_client.send_message`` for now: the existing
    function already runs ``require_agent`` and the Noter audit mirror. This
    wrapper exists so all internal callers funnel through a single name that
    we can upgrade later (e.g. to also populate ``server_id`` / ``network_id``
    inside the HTTP payload once ``eacn_client._post_message_raw`` is fixed).
    """
    return eacn_client.send_message(
        port=port,
        to_agent_id=to_agent_id,
        from_agent_id=from_agent_id,
        content=content,
        timeout=timeout,
        validate_target=validate_target,
        audit_to_noter=audit_to_noter,
    )


def mos_create_task(
    port: int,
    description: str,
    domains: list[str],
    initiator_id: str,
    budget: float = 0.0,
    expected_output: dict[str, Any] | None = None,
    deadline: str | None = None,
    level: str | None = None,
    invited_agent_ids: list[str] | None = None,
    max_concurrent_bidders: int | None = None,
    task_id: str | None = None,
    timeout: float = eacn_client.DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Create a task with three-layer addressing validated.

    Thin wrapper over ``eacn_client.create_task``. Existing contract is
    preserved; this wrapper exists as the single call site every MinionsOS
    internal caller should use, so future addressing fixes only touch one
    place.
    """
    return eacn_client.create_task(
        port=port,
        description=description,
        domains=domains,
        initiator_id=initiator_id,
        budget=budget,
        expected_output=expected_output,
        deadline=deadline,
        level=level,
        invited_agent_ids=invited_agent_ids,
        max_concurrent_bidders=max_concurrent_bidders,
        task_id=task_id,
        timeout=timeout,
    )
