#!/usr/bin/env python3
"""Keepalive MCP server.

Two tools:
  - wait_bg(deadline_seconds=240, bg_ids=None, note=None)
      Block up to deadline_seconds, then return a byte-stable tick payload.
      Purpose: while a background task (Bash run_in_background, long subagent,
      MCP call, etc.) is in flight, the main session would otherwise sit idle
      with no API turns, letting the 5-minute prompt cache TTL expire. This
      tool turns each idle stretch into one tiny API turn -> cache stays warm.

      The return payload is identical every call (independent of when /
      with what bg_ids the caller invoked) so the post-tick conversation tail
      remains cacheable too. bg_ids and note are echoed back for the model's
      benefit but DO NOT affect cache key (they go in a separate field that
      is also stable when caller passes the same args).

  - keepalive_now()
      Non-blocking, returns the same byte-stable tick payload immediately.
      Use when the model just wants a cheap "touch the cache now" turn
      without waiting (rare; wait_bg is the main path).

Implementation notes:
  - sleeps in 1s chunks so SIGTERM is honored within ~1s
  - hard cap deadline at 300s defensively (5-min cliff is 300s; 240 is the
    recommended value; never exceed cliff)
  - hard floor at 5s (anything shorter is just a non-blocking call)
"""
from __future__ import annotations

import asyncio
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


@mcp.tool()
async def wait_bg(
    deadline_seconds: int = 180,
    bg_ids: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Block up to deadline_seconds, return a byte-stable cache-keepalive tick.

    Args:
        deadline_seconds: how long to block. Hard floor 5s, hard ceiling 300s
            (5-min cache cliff). Default 180s leaves 120s of headroom for
            tool roundtrip + model processing on either side. Empirically
            240s was tight enough to occasionally miss the cliff.
        bg_ids: optional list of background task ids the caller is waiting on.
            Echoed in the result so the model can remember which BashOutput
            to call next. Does not affect blocking duration.
        note: optional human-readable note (e.g. "waiting on pytest"). Echoed
            in the result. Does not affect blocking duration.

    Returns:
        Tick payload (byte-stable across calls). bg_ids and note are echoed
        in a `caller` sub-object.
    """
    secs = max(5, min(270, int(deadline_seconds)))
    elapsed = 0
    while elapsed < secs:
        chunk = min(1, secs - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk

    result = dict(TICK)
    result["caller"] = {"bg_ids": list(bg_ids or []), "note": note or ""}
    result["slept_seconds"] = secs
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
