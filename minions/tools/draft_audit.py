"""Per-role Draft-discipline audit tracker.

Tracks two pieces of cycle-level state per (project, role):

- ``last_delivery_was_real``: whether the most recent ``mos_await_events``
  delivery contained at least one real (non-``cache_keepalive``) event.
- ``appends_since_last_await``: number of ``mos_draft_append`` calls
  the role made between the last ``mos_await_events`` return and now.

The combination drives the "Draft discipline reminder": at every
``mos_await_events`` return we ask, "did the previous cycle handle real
events but produce zero Draft writes?" If yes, prepend a soft reminder
to the suggested_action of the first event so the model is nudged to
record what it just did.

State lives at ``project_state_dir(port)/draft_audit/<agent_id>.json``.
File-locked atomic writes via ``.tmp + rename`` so concurrent
``mos_draft_append`` calls (rare in practice — a role's tools are
serialized — but possible across subagents) don't corrupt the counter.

Why on disk: the role process can be killed and respawned mid-cycle
(``mos_compact_context`` / Gru watchdog respawn). The freshly cold-started
role still receives its events from EACN's queue, and we want the
``previous cycle had real events`` flag to survive the restart so the
first post-restart ``mos_await_events`` return correctly fires (or
suppresses) the reminder.

Why a separate module: the audit is read by ``mos_await_events`` and
written by ``mos_draft_append``, both of which already have a lot of
inline logic. Keeping the tracker isolated keeps that logic readable
and lets us unit-test the state machine in isolation.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from minions.paths import project_state_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditSnapshot:
    """Snapshot of the audit state at the moment of an await_events return."""

    appends_since_last_await: int
    prev_delivery_was_real: bool

    @property
    def reminder_due(self) -> bool:
        """The previous cycle handled real events but wrote 0 Draft nodes.

        That is the failure mode the reminder is meant to nudge: the
        role got a real EACN event, did some work (e.g. published an
        artifact), and is about to call ``mos_await_events`` again
        without leaving a Draft trail.
        """
        return self.prev_delivery_was_real and self.appends_since_last_await == 0


def _audit_dir(port: int) -> Path:
    return project_state_dir(port) / "draft_audit"


def _audit_path(port: int, agent_id: str) -> Path:
    safe_agent = agent_id.replace("/", "_").replace("..", "_")
    return _audit_dir(port) / f"{safe_agent}.json"


def _load(port: int, agent_id: str) -> dict:
    path = _audit_path(port, agent_id)
    if not path.is_file():
        return {"appends_since_last_await": 0, "last_delivery_was_real": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("draft_audit: failed to load %s: %s", path, exc)
        return {"appends_since_last_await": 0, "last_delivery_was_real": False}


def _store(port: int, agent_id: str, payload: dict) -> None:
    path = _audit_path(port, agent_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug("draft_audit: failed to store %s: %s", path, exc)


def record_append(port: int, agent_id: str, count: int = 1) -> None:
    """Increment the per-role append counter by *count* (default 1).

    Called by ``mos_draft_append`` after the disk write succeeds. Failure
    is logged at debug level and swallowed — the audit is observability,
    not correctness, and a transient FS issue must never break Draft
    writes.
    """
    if count <= 0:
        return
    payload = _load(port, agent_id)
    payload["appends_since_last_await"] = int(payload.get("appends_since_last_await", 0)) + count
    _store(port, agent_id, payload)


def take_snapshot_and_reset(
    port: int, agent_id: str, *, returning_real_events: bool
) -> AuditSnapshot:
    """Read current state, then reset for the next cycle.

    Called by ``mos_await_events`` exactly once per return, after the
    return-events have been classified as real vs keepalive.

    Returns a snapshot of the *previous* cycle's state so the caller can
    decide whether to emit the discipline reminder. The state is then
    reset: ``appends_since_last_await`` → 0, and
    ``last_delivery_was_real`` → ``returning_real_events`` (so the next
    snapshot reflects this delivery's class).
    """
    payload = _load(port, agent_id)
    snapshot = AuditSnapshot(
        appends_since_last_await=int(payload.get("appends_since_last_await", 0)),
        prev_delivery_was_real=bool(payload.get("last_delivery_was_real", False)),
    )
    _store(
        port,
        agent_id,
        {
            "appends_since_last_await": 0,
            "last_delivery_was_real": bool(returning_real_events),
        },
    )
    return snapshot
