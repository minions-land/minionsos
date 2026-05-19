#!/usr/bin/env python3
"""PreToolUse hook for Agent / Task: advise switching to bg mode when long
work is likely.

Foreground Agent/Task synchronously blocks the main session for the entire
subagent run. If that exceeds the 5-min prompt cache TTL, the cache expires
and the next real turn pays a full uncached cold start. The keepalive
infrastructure (wait_bg + bg_keepalive_nudge hook) only engages when
``run_in_background=true``.

This hook reads the proposed Agent/Task call. If it looks like a long task
AND ``run_in_background`` is not set, it emits an advisory (additionalContext)
suggesting the model add ``run_in_background: true`` so the cache can stay
warm. The hook NEVER blocks — it always exits 0; the advisory is just a
hint to the model on the next turn.

Heuristic for "long task":
  - prompt mentions one of LONG_KEYWORDS (long / large / many / refactor / ...)
  - description mentions one of LONG_KEYWORDS
  - prompt > LONG_PROMPT_BYTES (longer prompts often map to longer work)

Foreground calls without long-task signals pass silently — they are likely
short investigations / one-shot lookups where wrap overhead exceeds gain.
"""

from __future__ import annotations

import json
import re
import sys

LONG_KEYWORDS = re.compile(
    r"\b(?:"
    r"long|large|huge|big|many|several|multiple|"
    r"refactor|migrate|migration|"
    r"end[- ]?to[- ]?end|e2e|"
    r"benchmark|comprehensive|exhaustive|"
    r"all (?:tests|files|modules)|"
    r"5\s*min|10\s*min|hours?"
    r")\b",
    re.IGNORECASE,
)
LONG_PROMPT_BYTES = 1500

ADVISORY = (
    "You called {tool} foreground (no run_in_background). The main session "
    "will block until the subagent returns; if that exceeds 5 minutes the "
    "prompt cache will expire (cold start ~tens of thousands of tokens on "
    "your next real turn).\n"
    "\n"
    "Reason this hook fired: {reason}.\n"
    "\n"
    "Recommendation: re-dispatch with run_in_background=true and enter the "
    "wait_bg loop:\n"
    "  1. Re-call {tool} with the same args plus run_in_background=true.\n"
    "  2. wait_bg(deadline_seconds=180, bg_ids=[<task_id>]) to keep cache warm.\n"
    "  3. {check_tool}(<task_id>) to check progress between ticks.\n"
    "  4. Loop until done.\n"
    "\n"
    "If you genuinely expect this task to finish in <2 min, ignore this and "
    "proceed foreground."
)

CHECK_TOOL = {
    "Agent": "TaskOutput",
    "Task": "TaskOutput",
}


def _looks_long(prompt: str, description: str) -> tuple[bool, str]:
    if LONG_KEYWORDS.search(description):
        m = LONG_KEYWORDS.search(description)
        return True, f'description mentions "{m.group(0)}"'
    if LONG_KEYWORDS.search(prompt):
        m = LONG_KEYWORDS.search(prompt)
        return True, f'prompt mentions "{m.group(0)}"'
    n = len(prompt.encode("utf-8"))
    if n > LONG_PROMPT_BYTES:
        return True, f"prompt is {n} bytes (>{LONG_PROMPT_BYTES})"
    return False, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in ("Agent", "Task"):
        return 0
    inp = payload.get("tool_input") or {}
    if inp.get("run_in_background"):
        return 0

    prompt = inp.get("prompt", "") or ""
    desc = inp.get("description", "") or ""
    is_long, reason = _looks_long(prompt, desc)
    if not is_long:
        return 0

    advisory = ADVISORY.format(
        tool=tool,
        reason=reason,
        check_tool=CHECK_TOOL.get(tool, "TaskOutput"),
    )

    out = {
        "systemMessage": (
            f"Foreground {tool} looks long ({reason}); cache may expire — "
            "consider run_in_background=true."
        ),
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": advisory,
        },
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
