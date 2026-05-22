#!/usr/bin/env python3
"""PostToolUse hook: capture subagent/codex transcripts into Reel (L0).

Trigger: tool_name in {Agent, Task, mcp__codex-subagent__codex} AND
tool_response contains an output_file field.

This hook archives the verbatim transcript from the output_file into the
calling role's reel directory, creating an audit trail for all dispatched
execution.

Design:
- Zero role burden: roles never call reel tools; capture is automatic.
- Full fidelity: transcripts are copied verbatim, not summarized.
- Role-private: each role writes to its own branch (branches/<role>/reel/).

Exits 0 always (advisory only). Emits structured JSON on stdout when
triggered; nothing on stdout for non-matching tools.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Tools that produce transcripts we want to capture
CAPTURE_TOOLS = {"Agent", "Task", "mcp__codex-subagent__codex"}

# Map tool names to reel "kind" labels
TOOL_TO_KIND = {
    "Agent": "subagent",
    "Task": "subagent",
    "mcp__codex-subagent__codex": "codex",
}


def _generate_session_id() -> str:
    """Generate a session ID based on current timestamp."""
    return f"sess-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in CAPTURE_TOOLS:
        return 0

    tool_response = payload.get("tool_response", {})
    output_file = tool_response.get("output_file")
    if not output_file:
        return 0

    # Extract environment
    port = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    session_id = os.environ.get("MINIONS_SESSION_ID", "").strip()

    if not port or not role:
        # Not in a MinionsOS role context; skip silently
        return 0

    if not session_id:
        # Generate a session ID if not set
        session_id = _generate_session_id()

    # Extract task ID from response
    task_id = (
        tool_response.get("agent_id")
        or tool_response.get("task_id")
        or tool_response.get("background_task_id")
        or tool_response.get("bash_id")
        or "unknown"
    )

    kind = TOOL_TO_KIND.get(tool, "subagent")

    # Import reel module and archive
    try:
        # Add minions package to path
        minions_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(minions_root))

        from minions.tools.reel import archive_transcript

        archive_transcript(
            port=int(port),
            role=role,
            session_id=session_id,
            task_id=task_id,
            source_path=Path(output_file),
            kind=kind,
        )

        # Emit advisory message
        result = {
            "hook": "reel_capture",
            "action": "archived",
            "port": port,
            "role": role,
            "session_id": session_id,
            "task_id": task_id,
            "kind": kind,
            "output_file": output_file,
        }
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)

    except Exception as exc:
        # Log error but don't fail the hook
        error = {
            "hook": "reel_capture",
            "action": "error",
            "error": str(exc),
            "port": port,
            "role": role,
            "session_id": session_id,
            "task_id": task_id,
        }
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
