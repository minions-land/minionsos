#!/usr/bin/env python3
"""Keepalive MCP server.

Two tools:
  - wait_bg(deadline_seconds=45, bg_ids=None, note=None, output_files=None)
      Block up to deadline_seconds, then return a byte-stable tick payload.
      If output_files is provided, polls every 1s and returns early once all
      listed files are no longer held open by any process (i.e. bg task done).

  - keepalive_now()
      Non-blocking, returns the same byte-stable tick payload immediately.

Implementation notes:
  - sleeps in 1s chunks so SIGTERM is honored within ~1s
  - hard cap deadline at 300s (5-min cache cliff)
  - hard floor at 5s
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write(
        "keepalive MCP: `mcp` python package not available. "
        "Run via: uv run --with 'mcp[cli]' python ~/.claude/mcp/keepalive/server.py\n"
    )
    raise

mcp = FastMCP("keepalive")

# Byte-stable payload: every field is constant. bg_ids / note are echoed
# in a separate object so the cache key only varies when the caller varies
# them (which is fine; cache still hits within a single bg-task window).
TICK = {
    "type": "tick",
    "ok": True,
    "purpose": "5min-cache-keepalive",
    "next_action": (
        "If your bg task is still running: call BashOutput(bash_id) to see "
        "progress, then call wait_bg again. If it completed, process the "
        "result. The tick itself is content-free; do not analyze it."
    ),
}


def _files_still_held(paths: list[str]) -> bool:
    """Return True if any of the given files is still held open by a process.

    Uses lsof. A bg Bash task in Claude Code writes to its output file via
    a child shell; once the shell exits, no process holds the file open
    anymore — that is the signal that the task has completed.

    Returns True (still held) on any lsof error to err on the side of
    keeping the keepalive running rather than exiting prematurely.
    """
    if not paths:
        return False
    try:
        # lsof returns exit 0 if any path is held, exit 1 if none.
        # We pass all paths in one call for efficiency.
        result = subprocess.run(
            ["lsof", "--", *paths],
            capture_output=True,
            timeout=2,
        )
        # exit 0 = at least one file is held -> still running
        # exit 1 = no files held -> all tasks done
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # On any error, assume still running (don't exit early on uncertainty)
        return True


@mcp.tool()
async def wait_bg(
    deadline_seconds: int = 45,
    bg_ids: list[str] | None = None,
    note: str | None = None,
    output_files: list[str] | None = None,
) -> dict[str, Any]:
    """Block up to deadline_seconds, return a byte-stable cache-keepalive tick.

    If output_files is provided, polls every 1s with lsof. Once no listed file
    is held open by any process (= all bg tasks done), returns immediately
    with early_exit=True. This avoids wasting time waiting after bg tasks
    have already completed.

    Args:
        deadline_seconds: max block duration. Floor 5s, ceiling 270s. Default
            45s — short enough that early-exit-by-completion-notification has
            low worst-case latency, long enough to avoid excessive turns.
        bg_ids: optional list of background task ids. Echoed in result.
        note: optional human-readable note. Echoed in result.
        output_files: optional list of bg task output file paths (the paths
            shown in "Output is being written to: ..." messages). When all
            listed files are no longer held open, wait_bg returns early.

    Returns:
        Tick payload (byte-stable across calls when called with same args).
        Adds slept_seconds and early_exit fields for observability.
    """
    secs = max(5, min(270, int(deadline_seconds)))
    files = list(output_files or [])
    early_exit = False
    elapsed = 0
    while elapsed < secs:
        await asyncio.sleep(1)
        elapsed += 1
        if files and elapsed >= 2 and not _files_still_held(files):
            early_exit = True
            break

    result = dict(TICK)
    result["caller"] = {"bg_ids": list(bg_ids or []), "note": note or ""}
    result["slept_seconds"] = elapsed
    result["early_exit"] = early_exit
    return result


@mcp.tool()
async def keepalive_now() -> dict[str, Any]:
    """Non-blocking variant. Returns the same tick immediately.

    Useful when the model wants to deliberately touch the cache right now
    without waiting (e.g. just finished a long synchronous tool, suspects
    the cache may have expired, wants one cheap turn to refresh before the
    next real call). Rare; prefer wait_bg for bg-task scenarios.
    """
    return dict(TICK)


if __name__ == "__main__":
    mcp.run()
