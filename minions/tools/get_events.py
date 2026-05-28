"""mos_get_events / mos_unread_summary — Gru-facing pull-mode event tools.

Gru is the to-human window. It does NOT drive an event loop with
``mos_await_events``; that is the resident-Role tool. Instead Gru pulls
on demand:

- ``mos_get_events(port)`` drains the project-local ``gru`` queue once
  (a single non-blocking ``GET /api/events/gru`` HTTP call), mirrors the
  events to ``project_{port}/events/gru.jsonl``, advances the
  ``gru.last_seen`` pointer to the new file end, and returns the events
  to Gru as annotated suggestions.
- ``mos_unread_summary()`` walks every active project, returns
  ``{port: unread_count}`` based on the persisted ``gru.last_seen``
  pointer. Gru uses this to decide which project to inspect next.

Drain semantics on EACN3 mean a queue read is destructive. The local
``events/gru.jsonl`` is the **durable copy**, written synchronously
before the function returns to Gru. ``last_seen`` lets Gru replay if it
ever needs to.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

import httpx

from minions.lifecycle._path_placeholder import decode_project_paths
from minions.paths import project_dir as _project_dir
from minions.tools import events_log
from minions.tools.await_events import _build_suggested_action

logger = logging.getLogger(__name__)

GRU_AGENT_ID = "gru"
HTTP_TIMEOUT_SEC = 10.0


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _drain_gru_queue(port: int) -> list[dict[str, Any]]:
    """Single non-blocking drain of the project-local Gru queue.

    Returns whatever EACN3 had buffered. Empty list when nothing is
    pending. We pass ``timeout=0`` so the server does not long-poll —
    Gru is pull-mode, never blocking.
    """
    url = f"{_base_url(port)}/api/events/{GRU_AGENT_ID}"
    try:
        resp = httpx.get(url, params={"timeout": 0}, timeout=HTTP_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"EACN3 drain on port {port} failed: {exc}") from exc
    raw = data.get("events") or data.get("messages") or []
    # Issue #47: rehydrate ${PROJECT_DIR} placeholders before mirroring to
    # disk and surfacing to Gru. Done at the boundary so events_log writes
    # the path-correct form for this host.
    try:
        pdir = str(_project_dir(port))
    except Exception:
        pdir = ""
    decoded: list[dict[str, Any]] = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        if pdir:
            with contextlib.suppress(Exception):
                e = decode_project_paths(e, pdir)
        decoded.append(e)
    return decoded


def get_events(port: int) -> dict[str, Any]:
    """Drain the Gru queue on *port* once and mirror to disk.

    Returns ``{count, events: [{event, suggested_action, suggested_tool,
    suggested_params, urgency}, ...], unread_remaining}``. ``count`` may
    be 0 when nothing was buffered. ``unread_remaining`` is the number of
    events still ahead of the advanced ``last_seen`` pointer — should
    almost always be 0 right after a successful read.
    """
    new_events = _drain_gru_queue(port)
    events_log.append_events(port, GRU_AGENT_ID, new_events)

    # The Gru pointer should track what Gru has actually been handed.
    # Read the unread tail (which now includes anything appended above
    # plus any earlier-buffered drain that Gru never picked up), then
    # push last_seen to the file end.
    pending = events_log.read_unread_events(port, GRU_AGENT_ID)
    events_log.advance_last_seen(port, GRU_AGENT_ID)

    annotated: list[dict[str, Any]] = []
    for record in pending:
        evt = record.get("event") if isinstance(record, dict) else None
        if not isinstance(evt, dict):
            continue
        annotation = _build_suggested_action(evt)
        annotated.append({"event": evt, **annotation})

    return {
        "count": len(annotated),
        "events": annotated,
        "unread_remaining": events_log.unread_count(port, GRU_AGENT_ID),
    }


def unread_summary() -> dict[str, Any]:
    """Return per-project Gru unread counts across all active projects.

    Output: ``{ports: [{port, name, unread}], total_unread}``. Used by
    Gru to decide which project to inspect, and by ``./mos noter <port>``
    to surface unread depth to the operator.
    """
    from minions.state.store import StateStore

    store = StateStore()
    rows: list[dict[str, Any]] = []
    total = 0
    for project in store.list_projects(filter="active"):
        unread = events_log.unread_count(int(project.port), GRU_AGENT_ID)
        rows.append({"port": int(project.port), "name": project.real_name, "unread": unread})
        total += unread
    return {"ports": rows, "total_unread": total}
