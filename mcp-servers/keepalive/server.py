#!/usr/bin/env python3
"""Keepalive MCP server.

Two tools:
  - wait_bg(deadline_seconds=45, bg_ids=None, note=None,
            output_files=None, done_markers=None)
      Block up to deadline_seconds, then return a byte-stable tick payload.
      Two early-exit channels (orthogonal, used together when both apply):
        * output_files: poll lsof every 1s; exit when no listed file is held
          open. Source signal for bg `Bash` tasks (Claude Code writes their
          stdout to a temp file via a child shell; once the shell exits
          the file is no longer held).
        * done_markers: poll filesystem every 1s; exit when every listed
          marker path exists. Source signal for bg `Agent` / `Task`
          subagents — the SubagentStop hook touches one marker per
          agent_id. Markers are unlinked on early exit so the directory
          stays bounded.

  - keepalive_now()
      Non-blocking, returns the same byte-stable tick payload immediately.

Implementation notes:
  - sleeps in 1s chunks so SIGTERM is honored within ~1s
  - hard cap deadline at 270s (5-min cache cliff with safety margin)
  - hard floor at 5s
"""

from __future__ import annotations

import asyncio
import contextlib
import os
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
        "If your bg task is still running: call BashOutput(bash_id) / "
        "TaskOutput(task_id) to see progress, then call wait_bg again. "
        "If early_exit=True the task completed; process the result. "
        "The tick itself is content-free; do not analyze it."
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
        result = subprocess.run(
            ["lsof", "--", *paths],
            capture_output=True,
            timeout=2,
        )
        # exit 0 = at least one file is held -> still running
        # exit 1 = no files held -> all tasks done
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True


def _all_markers_present(paths: list[str]) -> bool:
    """Return True iff every listed marker path exists on disk."""
    return bool(paths) and all(os.path.exists(p) for p in paths)


def _cleanup_markers(paths: list[str]) -> None:
    """Best-effort unlink of marker files; never raises."""
    for p in paths:
        with contextlib.suppress(OSError):
            os.unlink(p)


@mcp.tool()
async def wait_bg(
    deadline_seconds: int = 45,
    bg_ids: list[str] | None = None,
    note: str | None = None,
    output_files: list[str] | None = None,
    done_markers: list[str] | None = None,
) -> dict[str, Any]:
    """Block up to deadline_seconds, return a byte-stable cache-keepalive tick.

    Two orthogonal early-exit channels:
      * output_files: bg Bash tasks. Poll lsof; exit once no listed file is
        held open by any process.
      * done_markers: bg Agent/Task subagents. Poll filesystem; exit once
        every listed marker path exists. Markers are written by the
        SubagentStop hook keyed on agent_id, then unlinked here.

    Either, both, or neither may be supplied. Both empty falls back to a
    pure sleep — useful as a generic cache-warming turn.

    Args:
        deadline_seconds: max block duration. Floor 5s, ceiling 270s.
            Default 45s — short enough that early-exit-by-completion has
            low worst-case latency, long enough to avoid excessive turns.
        bg_ids: optional background task ids. Echoed in result for trace.
        note: optional human-readable note. Echoed in result.
        output_files: optional bg-task output file paths (the paths shown
            in "Output is being written to: ..." messages).
        done_markers: optional marker file paths. Each is touched by the
            SubagentStop hook when its agent_id finishes.

    Returns:
        Tick payload (byte-stable across calls when called with same args).
        Adds slept_seconds / early_exit / early_exit_reason for observability.
    """
    secs = max(5, min(270, int(deadline_seconds)))
    files = list(output_files or [])
    markers = list(done_markers or [])
    early_exit = False
    early_exit_reason = ""
    elapsed = 0
    while elapsed < secs:
        await asyncio.sleep(1)
        elapsed += 1
        if elapsed < 2:
            continue
        if markers and _all_markers_present(markers):
            early_exit = True
            early_exit_reason = "done_markers"
            _cleanup_markers(markers)
            break
        if files and not _files_still_held(files):
            early_exit = True
            early_exit_reason = "output_files"
            break

    result = dict(TICK)
    result["caller"] = {"bg_ids": list(bg_ids or []), "note": note or ""}
    result["slept_seconds"] = elapsed
    result["early_exit"] = early_exit
    result["early_exit_reason"] = early_exit_reason
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
