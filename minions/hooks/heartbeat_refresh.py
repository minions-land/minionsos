#!/usr/bin/env python3
"""PreToolUse heartbeat refresh.

Fires on every tool call (Bash, Edit, Write, Read, Agent, Task, codex MCP)
and refreshes ``branches/<role>/.minionsos/heartbeat`` so observers know
the Role is alive WHILE doing work, not just between turns.

The pre-v15.8 design refreshed heartbeat only inside ``mos_await_events``
and ``mos_noter_wait``. Both run between turns, not during. While a Role
was deep in a long thinking turn, a multi-minute Codex sub-agent
dispatch, or a long Bash call, the heartbeat went stale and any health
view that read ``alive_at`` reported the Role as dead — see GitHub
Issue #4 for the user-visible misread.

This hook fixes the misread by piggybacking on the tool-call boundary,
which fires often even during long multi-tool turns. Cost: one
``json.dump`` to a tiny file per tool call. No LLM cost (PreToolUse
output is not injected into the model context unless the hook returns a
non-zero exit).

Identity: read from ``MINIONS_ROLE_NAME`` and the workspace path is
resolved via ``MINIONS_WORKSPACE`` (the launcher sets both at spawn
time). When either is missing, the hook is a silent no-op — this
matches the pre-v15.8 behavior of ``_touch_heartbeat`` in
``minions/tools/await_events.py``.

Cache safety: writes one file under workspace; emits no stdout / stderr
text on success. Does not affect the prompt-prefix cache key.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    workspace_env = os.environ.get("MINIONS_WORKSPACE", "").strip()
    if not role or not workspace_env:
        return 0  # not running inside a Role process — silent no-op

    workspace = Path(workspace_env)
    if not workspace.is_dir():
        return 0  # workspace missing — likely a stale env, don't crash

    hb_dir = workspace / ".minionsos"
    hb_path = hb_dir / "heartbeat"
    payload = {
        "agent_id": os.environ.get("MINIONS_AGENT_ID", role),
        "role": role,
        "alive_at": datetime.now(tz=UTC).isoformat(),
        "pid": os.getpid(),
        "source": "pretool_hook",
    }
    try:
        hb_dir.mkdir(parents=True, exist_ok=True)
        with hb_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except OSError:
        # Filesystem hiccup must never block a tool call.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
