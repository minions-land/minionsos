#!/usr/bin/env python3
"""PostToolUse hook: nudge model into wait_bg keepalive loop after spawning
any backgroundable tool (Bash, Agent, Task).

Trigger: tool_name in {Bash, Agent, Task} AND tool_input.run_in_background is
truthy. Hook fires once per bg spawn; foreground calls (no run_in_background)
silently pass — at the time PostToolUse fires for a foreground call the work
is already complete, so a nudge is moot.

Why fire on bg only:
  - bg Bash: dispatch returns task id immediately; main session can call
    wait_bg in following turns to keep 5-min cache warm.
  - bg Agent / Task: same shape — model gets a task id back and is free to
    issue wait_bg calls while the agent runs.
  - foreground Agent / Task in a single turn = main session goes into a
    multi-minute tool-pending state; cannot issue ANY new tool calls (incl.
    wait_bg) until the agent returns. The cure is to re-dispatch in bg
    mode, but that decision must be taken at PreToolUse, not here.

Exits 0 always (advisory only). Emits structured JSON on stdout when
triggered; nothing on stdout for non-matching tools.
"""

from __future__ import annotations

import json
import sys

BG_TOOLS = {"Bash", "Agent", "Task"}

NUDGE_TEMPLATE = (
    "You just spawned a background {tool} task ({id_label}). The main session "
    "will sit idle until it completes; the prompt cache (5-min TTL) will "
    "expire on long-running tasks unless you keep it warm.\n"
    "\n"
    "Pattern to follow:\n"
    "  1. Call `wait_bg(deadline_seconds=180, bg_ids=[{id_value}])` to block "
    "and refresh the cache.\n"
    "  2. When wait_bg returns its tick, call `{check_tool}({id_value})` to "
    "check progress. If completed, process the result. If still running, "
    "call wait_bg again.\n"
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
RESPONSE_ID_KEYS = (
    "bash_id",
    "agent_id",
    "task_id",
    "background_task_id",
    "shell_id",
    "id",
)


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
    resp = payload.get("tool_response") or {}
    if isinstance(resp, dict):
        for k in RESPONSE_ID_KEYS:
            if resp.get(k):
                bg_id = str(resp[k])
                break

    id_label = f"id={bg_id}" if bg_id else "id unknown — find it in the tool result"
    id_value = f'"{bg_id}"' if bg_id else "<task_id>"
    nudge = NUDGE_TEMPLATE.format(
        tool=tool,
        id_label=id_label,
        id_value=id_value,
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
