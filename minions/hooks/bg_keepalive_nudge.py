#!/usr/bin/env python3
"""PostToolUse hook for Bash: nudge model into the wait_bg keepalive loop
whenever a background task is spawned.

Trigger condition: tool_name == "Bash" AND tool_input.run_in_background is
truthy. The hook fires once per bg spawn and injects additionalContext that
tells the model:
  1. you just spawned a bg task -- the main session will go idle while it runs
  2. the 5-min prompt cache will expire if you sit silent
  3. call wait_bg(deadline_seconds=240, bg_ids=[<id>]) repeatedly until the
     task completes, checking BashOutput between ticks

Why PostToolUse rather than Pre: at Pre we do not yet know the spawned id;
at Post the tool_response carries it. The cost of one extra turn before the
nudge is negligible (still well within the 5-min cliff).

Exits 0 always (advisory only, never blocks). Emits structured JSON on stdout
when triggered; nothing on stdout for non-matching tools.
"""

from __future__ import annotations

import json
import sys

NUDGE = (
    "You just spawned a background task. The main session will now sit idle "
    "until the task completes, and the prompt cache (5-min TTL) will expire "
    "during long-running tasks unless you keep it warm.\n"
    "\n"
    "Pattern to follow (every time you spawn a bg task):\n"
    "  1. Call `wait_bg(deadline_seconds=240, bg_ids=[<bash_id>])` to block "
    "and refresh the cache.\n"
    "  2. When wait_bg returns its tick, call `BashOutput(<bash_id>)` to check "
    "progress. If completed, process the result. If still running, call "
    "wait_bg again.\n"
    "  3. Repeat until done.\n"
    "\n"
    "Do NOT just sit and wait without calling wait_bg -- you will pay a full "
    "uncached-input cold start on your next real turn (~tens of thousands of "
    "tokens). The wait_bg tick payload is byte-stable so the post-tick tail "
    "stays cacheable."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    inp = payload.get("tool_input") or {}
    if not inp.get("run_in_background"):
        return 0

    bash_id = None
    resp = payload.get("tool_response") or {}
    # Different harness versions land the id in different fields; try common ones.
    for k in ("bash_id", "id", "background_task_id", "shell_id"):
        if isinstance(resp, dict) and resp.get(k):
            bash_id = resp[k]
            break

    nudge = NUDGE
    if bash_id:
        nudge = nudge.replace("<bash_id>", str(bash_id))

    out = {
        "systemMessage": "Background task spawned -- enter wait_bg keepalive loop.",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": nudge,
        },
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
