"""Shared per-agent EACN event-log persistence — synchronous write-then-read.

The contract: when ``mos_await_events`` (Roles) or ``mos_get_events`` (Gru)
drain events out of EACN3, the bytes are appended to
``project_{port}/events/{agent_id}.jsonl`` **before** the function returns
to the LLM. There is no background flusher, no "audit mirror" written
later — the disk copy and the LLM-visible copy come out of the same
critical section, so a power cut between drain and LLM read leaves the
disk copy intact.

This guarantees post-mortem reconstruction: at the end of a project the
union of every ``events/<agent>.jsonl`` plus each role's Exploration DAG
describes the complete network history exactly as the agents saw it.

Roles do not read these files in normal operation — they consume events
through the MCP return value and then look at the DAG and their
scratchpad. The jsonl is for humans (and for any future replay tooling).

Gru additionally maintains a tiny ``{agent_id}.last_seen`` companion file
holding the byte offset it has read up to. ``unread_count`` returns
``file_size - last_seen``; ``advance_last_seen`` pushes it forward after
a Gru read.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _events_dir(port: int) -> Path:
    """Resolve the per-project events directory.

    Imported lazily because ``minions.paths`` pulls in environment-dependent
    settings; tests that don't construct a project still want this module to
    import cleanly.
    """
    from minions.paths import project_events_dir

    return project_events_dir(port)


def event_log_path(port: int, agent_id: str) -> Path:
    return _events_dir(port) / f"{agent_id}.jsonl"


def last_seen_path(port: int, agent_id: str) -> Path:
    return _events_dir(port) / f"{agent_id}.last_seen"


def append_events(port: int, agent_id: str, events: list[dict[str, Any]]) -> None:
    """Synchronously append *events* to ``events/{agent_id}.jsonl``.

    Called by ``mos_await_events`` and ``mos_get_events`` BEFORE they
    return events to the LLM. The disk write is the durable copy; the
    LLM's view is a derivative.

    No-op when *events* is empty. Failures are logged and swallowed — the
    sync-write is best-effort; a disk hiccup must never break the
    LLM-visible event-loop return path.
    """
    if not events:
        return
    try:
        path = event_log_path(port, agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        ingested_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as fh:
            for evt in events:
                fh.write(
                    json.dumps(
                        {"ingested_at": ingested_at, "event": evt},
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
    except Exception as exc:
        logger.warning(
            "events_log.append_events failed port=%d agent=%s: %s",
            port,
            agent_id,
            exc,
        )


def read_last_seen(port: int, agent_id: str) -> int:
    """Return the last-seen byte offset for *agent_id*, or 0 if absent."""
    path = last_seen_path(port, agent_id)
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def advance_last_seen(port: int, agent_id: str) -> None:
    """Push the last-seen offset to the current file end."""
    log_path = event_log_path(port, agent_id)
    if not log_path.exists():
        return
    try:
        size = log_path.stat().st_size
    except OSError:
        return
    seen = last_seen_path(port, agent_id)
    seen.parent.mkdir(parents=True, exist_ok=True)
    tmp = seen.with_suffix(".last_seen.tmp")
    try:
        tmp.write_text(str(size), encoding="utf-8")
        os.replace(tmp, seen)
    except OSError as exc:
        logger.warning(
            "events_log.advance_last_seen failed port=%d agent=%s: %s",
            port,
            agent_id,
            exc,
        )


def unread_count(port: int, agent_id: str) -> int:
    """Return the count of jsonl lines past the last_seen offset."""
    log_path = event_log_path(port, agent_id)
    if not log_path.exists():
        return 0
    seen_offset = read_last_seen(port, agent_id)
    try:
        size = log_path.stat().st_size
    except OSError:
        return 0
    if size <= seen_offset:
        return 0
    try:
        with log_path.open("rb") as fh:
            fh.seek(seen_offset)
            tail = fh.read()
    except OSError:
        return 0
    return tail.count(b"\n")


def read_unread_events(port: int, agent_id: str) -> list[dict[str, Any]]:
    """Return all events appended since last_seen, without advancing it."""
    log_path = event_log_path(port, agent_id)
    if not log_path.exists():
        return []
    seen_offset = read_last_seen(port, agent_id)
    try:
        with log_path.open("rb") as fh:
            fh.seek(seen_offset)
            tail = fh.read()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for raw in tail.splitlines():
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out
