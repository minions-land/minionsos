"""Per-role on-disk veto buffer.

When the scratchpad-veto gate in :mod:`minions.lifecycle.wakeup` blocks a
wake-up, the events the scheduler already drained from EACN3 must NOT be
dropped: the server-side poll is destructive (EACN3 does not re-queue),
so anything we fetched and don't dispatch needs to be re-delivered by us.

This module mirrors the :mod:`minions.lifecycle.gru_inbox` pattern but is
keyed per (port, role): each buffered event batch is appended to a small
jsonl file that the next tick drains *before* polling EACN3 again.

Format: each line is a JSON object ``{"event": <raw event>}``. No seq /
cursor — the file is fully consumed and truncated on drain.
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
    """Append *events* to the per-role veto buffer. Returns count written."""
    if not events:
        return 0
    p = buffer_path(port, role)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps({"event": ev}, default=str) + "\n")
    return len(events)


def drain(port: int, role: str) -> list[dict[str, Any]]:
    """Read and remove all buffered events for (*port*, *role*).

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
        logger.warning("role_inbox drain failed port=%d role=%s: %s", port, role, exc)
        return []
    with contextlib.suppress(OSError):
        os.remove(p)
    return out


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
