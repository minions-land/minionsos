#!/usr/bin/env python3
"""PostToolUse hook: nudge model into wait_bg keepalive loop after spawning
any backgroundable tool (Bash, Agent, Task).

Trigger: tool_name in {Bash, Agent, Task} AND tool_input.run_in_background is
truthy. Hook fires once per bg spawn; foreground calls (no run_in_background)
silently pass — at the time PostToolUse fires for a foreground call the work
is already complete, so a nudge is moot.

The nudge tells wait_bg how to early-exit on this specific task:
  - Bash: pass `output_files=[<output_file>]` and let wait_bg lsof-poll until
    the bg shell releases the file.
  - Agent / Task: pass `done_markers=["<MARKER_DIR>/<agent_id>.done"]`. The
    `keepalive_subagent_done.py` SubagentStop hook touches that marker when
    the subagent finishes; wait_bg sees the marker and returns immediately.

The two channels are orthogonal — wait_bg checks both each tick.

Exits 0 always (advisory only). Emits structured JSON on stdout when
triggered; nothing on stdout for non-matching tools.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BG_TOOLS = {"Bash", "Agent", "Task"}

MARKER_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "claude-keepalive-markers"

NUDGE_TEMPLATE = (
    "You just spawned a background {tool} task ({id_label}). The main session "
    "will sit idle until it completes; the prompt cache (5-min TTL) will "
    "expire on long-running tasks unless you keep it warm.\n"
    "\n"
    "Pattern to follow:\n"
    "  1. Call `wait_bg(deadline_seconds=180, bg_ids=[{id_value}]{exit_arg})` "
    "to block and refresh the cache. wait_bg returns early as soon as the "
    "task completes — you do NOT pay the full deadline.\n"
    "  2. When wait_bg returns, check `early_exit` in the result:\n"
    "     - If early_exit=True: task completed, call `{check_tool}({id_value})` "
    "to read the result.\n"
    "     - If early_exit=False: deadline reached without completion. Call "
    "`{check_tool}({id_value})` to peek at progress, then call wait_bg again.\n"
    "  3. Repeat until done.\n"
    "\n"
    "Do NOT just sit and wait without calling wait_bg — you will pay a full "
    "uncached-input cold start (~tens of thousands of tokens) on your next "
    "real turn. The wait_bg tick payload is byte-stable so the post-tick "
    "tail stays cacheable."
)

# How to inspect each tool's progress between ticks.
CHECK_TOOL = {
    "Bash": "BashOutput",
    "Agent": "TaskOutput",
    "Task": "TaskOutput",
}

# Likely fields in tool_response carrying the spawned task id, in priority order.
# Agent tool uses camelCase `agentId`; Bash uses snake_case `bash_id`. Other
# variants are kept for forward-compatibility with future tool shapes.
RESPONSE_ID_KEYS = (
    "bash_id",
    "agentId",
    "agent_id",
    "taskId",
    "task_id",
    "background_task_id",
    "shell_id",
    "id",
)

OUTPUT_FILE_KEY = "output_file"


def _build_exit_arg(tool: str, bg_id: str | None, output_file: str | None) -> str:
    """Return the wait_bg kwarg fragment that lets it early-exit on this task.

    Bash → `output_files=[...]` (lsof channel).
    Agent / Task → `done_markers=[...]` (SubagentStop hook channel).
    Unknown tool or missing id → empty string; wait_bg falls back to plain sleep.
    """
    if tool == "Bash" and output_file:
        return f', output_files=["{output_file}"]'
    if tool in {"Agent", "Task"} and bg_id:
        marker = MARKER_DIR / f"{bg_id}.done"
        return f', done_markers=["{marker}"]'
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in BG_TOOLS:
        return 0
    inp = payload.get("tool_input") or {}
    if not inp.get("run_in_background"):
        return 0

    bg_id = None
    output_file = None
    resp = payload.get("tool_response") or {}
    if isinstance(resp, dict):
        for k in RESPONSE_ID_KEYS:
            if resp.get(k):
                bg_id = str(resp[k])
                break
        output_file = resp.get(OUTPUT_FILE_KEY)

    id_label = f"id={bg_id}" if bg_id else "id unknown — find it in the tool result"
    id_value = f'"{bg_id}"' if bg_id else "<task_id>"
    exit_arg = _build_exit_arg(tool, bg_id, output_file)

    nudge = NUDGE_TEMPLATE.format(
        tool=tool,
        id_label=id_label,
        id_value=id_value,
        exit_arg=exit_arg,
        check_tool=CHECK_TOOL.get(tool, "BashOutput"),
    )

    out = {
        "systemMessage": f"Background {tool} spawned — enter wait_bg keepalive loop.",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": nudge,
        },
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
