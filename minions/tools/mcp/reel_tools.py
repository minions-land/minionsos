"""MCP tools for Reel (L0) — raw session-level execution traces.

Exposes:
- mos_reel_get(ref) — read a single transcript by reference.
- mos_reel_window(ref, span) — read index entries around a reference.

Authz:
- All main roles can see these tools (CLI whitelist).
- Server-side enforcement: non-Gru roles can only read their own reels.
"""

from __future__ import annotations

from typing import Any

from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed
from minions.tools.reel import mos_reel_get as _mos_reel_get
from minions.tools.reel import mos_reel_window as _mos_reel_window


@mcp.tool()
def mos_reel_get(ref: str) -> dict[str, Any]:
    """Read a single transcript by reel reference.

    Args:
        ref: Reel reference in the form "<role>/<session_id>/<task_id>".
             Example: "expert-moe-arch/sess-20260522-123456/a1b2c3d4e5f6"

    Returns:
        A dict with keys:
        - ref: The input reference.
        - role: Role name.
        - session_id: Session identifier.
        - task_id: Task identifier.
        - kind: Entry kind (from index).
        - ts: Timestamp (from index).
        - draft_refs: List of Draft node IDs that reference this entry.
        - lines: List of transcript lines (parsed JSON objects).

    Raises:
        PermissionError: If the caller lacks permission to read this reel.
        ValueError: If the ref is malformed or the transcript does not exist.
    """
    _require_tool_allowed("mos_reel_get")
    return _mos_reel_get(ref)


@mcp.tool()
def mos_reel_window(ref: str, span: int = 5) -> list[dict[str, Any]]:
    """Read index entries around a reel reference.

    Args:
        ref: Reel reference in the form "<role>/<session_id>/<task_id>".
        span: Number of entries to return before and after the target (default 5).

    Returns:
        A list of index entries (dicts with seq, ts, kind, task_id, draft_refs).
        The target entry is included; the list is sorted by seq.

    Raises:
        PermissionError: If the caller lacks permission to read this reel.
        ValueError: If the ref is malformed or the session does not exist.
    """
    _require_tool_allowed("mos_reel_window")
    return _mos_reel_window(ref, span)
