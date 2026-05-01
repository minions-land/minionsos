"""Per-role on-disk wake signal buffer.

MinionsOS stores compact wake signals here so resident role sessions can be
re-awakened without exposing the full EACN payload in the prompt. Legacy
poll-based wake batches and new hook-driven signals share the same storage
format: a small jsonl file keyed by ``(port, role)``.

Format: each line is a JSON object ``{"event": <signal>}``. No seq / cursor.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from minions.paths import project_logs_dir

logger = logging.getLogger(__name__)


def buffer_path(port: int, role: str) -> Path:
    safe_role = role.replace("/", "_").replace("..", "_")
    return project_logs_dir(port) / f"veto_buffer-{safe_role}.jsonl"


def append_events(port: int, role: str, events: list[dict[str, Any]]) -> int:
    """Append *events* to the per-role wakeup buffer. Returns count written."""
    if not events:
        return 0
    p = buffer_path(port, role)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps({"event": ev}, default=str) + "\n")
    return len(events)


def read_events(port: int, role: str) -> list[dict[str, Any]]:
    """Read all buffered events for (*port*, *role*) without removing them.

    Returns an empty list if the buffer does not exist.
    """
    p = buffer_path(port, role)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                ev = entry.get("event")
                if isinstance(ev, dict):
                    out.append(ev)
    except Exception as exc:
        logger.warning("role_inbox read failed port=%d role=%s: %s", port, role, exc)
        return []
    return out


def replace_events(port: int, role: str, events: list[dict[str, Any]]) -> int:
    """Atomically replace the per-role wakeup buffer with *events*."""
    p = buffer_path(port, role)
    if not events:
        clear(port, role)
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps({"event": ev}, default=str) + "\n")
    os.replace(tmp, p)
    return len(events)


def clear(port: int, role: str) -> None:
    """Remove the per-role wakeup buffer if it exists."""
    with contextlib.suppress(OSError):
        os.remove(buffer_path(port, role))


def drain(port: int, role: str) -> list[dict[str, Any]]:
    """Read and remove all buffered events for (*port*, *role*)."""
    events = read_events(port, role)
    clear(port, role)
    return events


def count(port: int, role: str) -> int:
    """Return number of buffered events for (*port*, *role*)."""
    p = buffer_path(port, role)
    if not p.exists():
        return 0
    n = 0
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n
