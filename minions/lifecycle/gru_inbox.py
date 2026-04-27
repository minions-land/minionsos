"""Gru EACN pending journal: per-project on-disk event safety buffer.

The source of truth is always the project-local EACN3 queue for agent
``"gru"``. EACN3's HTTP event endpoint is drain-on-read and currently has no
message-level ack/claim, so Gru's MCP adapter journals messages immediately
after polling them. Gru then processes those pending entries and advances the
cursor after it has replied or otherwise handled them.

This is not a second communication system; it is a local reliability shim for
EACN3's drain-only transport.

Format: each line is a JSON object
``{"seq": <int>, "fetched_at": <iso>, "port": <int>, "event": <raw event>}``.
A sibling ``gru_inbox.cursor`` file stores the last ``seq`` Gru has read.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.paths import project_logs_dir

logger = logging.getLogger(__name__)


def inbox_path(port: int) -> Path:
    return project_logs_dir(port) / "gru_inbox.jsonl"


def cursor_path(port: int) -> Path:
    return project_logs_dir(port) / "gru_inbox.cursor"


def _read_cursor(port: int) -> int:
    p = cursor_path(port)
    if not p.exists():
        return 0
    try:
        return int(p.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def _write_cursor(port: int, seq: int) -> None:
    p = cursor_path(port)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(str(seq), encoding="utf-8")
    os.replace(tmp, p)


def _next_seq(port: int) -> int:
    """Return the next seq by scanning the last line of the inbox (cheap enough)."""
    p = inbox_path(port)
    if not p.exists() or p.stat().st_size == 0:
        return 1
    last_seq = 0
    try:
        with p.open("rb") as fh:
            # Read last 4KB to grab the final line without loading the whole file.
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            chunk = min(size, 4096)
            fh.seek(size - chunk)
            tail = fh.read().decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                last_seq = int(json.loads(line).get("seq", 0))
                break
            except Exception:
                continue
    except Exception as exc:
        logger.warning("_next_seq scan failed port=%d: %s", port, exc)
    return last_seq + 1


def append_events(port: int, events: list[dict[str, Any]]) -> int:
    """Append *events* to the gru inbox for *port*. Returns count written."""
    if not events:
        return 0
    p = inbox_path(port)
    p.parent.mkdir(parents=True, exist_ok=True)
    seq = _next_seq(port)
    now = datetime.now(tz=UTC).isoformat()
    with p.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(
                json.dumps(
                    {"seq": seq, "fetched_at": now, "port": port, "event": ev},
                    default=str,
                )
                + "\n"
            )
            seq += 1
    return len(events)


def read_unread(port: int, max_events: int = 50) -> list[dict[str, Any]]:
    """Return up to *max_events* inbox entries with seq > cursor. Does not advance."""
    p = inbox_path(port)
    if not p.exists():
        return []
    cur = _read_cursor(port)
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if int(entry.get("seq", 0)) > cur:
                out.append(entry)
                if len(out) >= max_events:
                    break
    return out


def mark_read(port: int, up_to_seq: int) -> None:
    """Advance the cursor to max(current, up_to_seq)."""
    cur = _read_cursor(port)
    if up_to_seq > cur:
        _write_cursor(port, up_to_seq)


def unread_count(port: int) -> int:
    p = inbox_path(port)
    if not p.exists():
        return 0
    cur = _read_cursor(port)
    n = 0
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                if int(json.loads(line).get("seq", 0)) > cur:
                    n += 1
            except Exception:
                continue
    return n
