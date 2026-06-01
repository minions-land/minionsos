#!/usr/bin/env python3
"""SubagentStop / Stop hook: signal completion to wait_bg.

When a Claude Code subagent (Agent / Task) finishes,
the SubagentStop event fires with `agent_id` (and friends) on stdin. We
touch a marker file at MARKER_DIR/<agent_id>.done so a wait_bg call running
in the parent session can early-exit instead of sleeping out the full
deadline.

The marker dir is shared by `bg_keepalive_nudge.py` (which embeds the
expected path into its nudge string) and by `keepalive/server.py:wait_bg`
(which polls for the markers and unlinks them on exit). Keep the path
constants in lockstep across the three files — there is no schema layer.

Stop (top-level) gets the same treatment for symmetry, even though wait_bg
in the *root* session doesn't currently need it; it costs nothing and
future-proofs nested-session keepalive.

Exits 0 always (advisory only). Best-effort: any error swallowed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MARKER_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "claude-keepalive-markers"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    agent_id = payload.get("agent_id") or payload.get("agentId") or payload.get("session_id")
    if not agent_id:
        return 0

    try:
        MARKER_DIR.mkdir(parents=True, exist_ok=True)
        (MARKER_DIR / f"{agent_id}.done").touch()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
