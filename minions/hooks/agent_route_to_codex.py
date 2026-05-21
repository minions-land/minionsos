#!/usr/bin/env python3
"""PreToolUse hook for Agent / Task: advise routing to codex Tier 2 when
the call would otherwise dispatch Sonnet for non-trivial work.

The codex SKILL.md says Sonnet is the degraded fallback only — non-trivial
work should run on Haiku→codex (Tier 2). But there's no enforcement, and
Sonnet is the harness's pre-existing default for "kind of medium-hard"
tasks. This hook closes that gap with a non-blocking nudge.

Trigger: tool_name in {Agent, Task} AND tool_input.model == "sonnet" AND
description does NOT contain "codex fallback" (case-insensitive). The
fallback exemption is so that Step 5 of the codex skill — which legitimately
dispatches Sonnet after codex itself errored — does not get re-nudged in a
loop.

The hook NEVER blocks — it always exits 0; the advisory is just a hint to
the model on the next turn. If the model decides Sonnet is genuinely
appropriate (e.g., codex unavailable, or a niche task type), it can ignore
the advisory and proceed.
"""

from __future__ import annotations

import json
import sys

ADVISORY = (
    "You called {tool} with model='sonnet'. Per ~/.claude/skills/codex/SKILL.md, "
    "Sonnet is the degraded fallback ONLY — for non-trivial work the default "
    "is Tier 2 (Haiku→codex GPT-5.5 xhigh): same capability as Opus 4.7, lower "
    "cost than Sonnet on this account, plus first-class run_in_background + "
    "wait_bg cache keepalive.\n"
    "\n"
    "Decide:\n"
    "  - Trivial (lookup, format, narrow Q&A) → Tier 1: re-dispatch with "
    "model='haiku' direct.\n"
    "  - Anything else (refactor, multi-file, debug, implement, review, "
    "investigate) → Tier 2: re-dispatch as Agent(model='haiku', "
    "run_in_background=true) with the relay prompt from "
    "~/.claude/skills/codex/SKILL.md Step 3 calling the codex MCP tool. "
    "For short / read-only tasks the Step 3-Mini relay is enough.\n"
    "  - Codex genuinely unreachable → keep Sonnet, but add '(codex "
    "fallback)' to the description so this hook stops nudging.\n"
    "\n"
    "If you genuinely believe Sonnet is the right tool for THIS task and "
    "codex is reachable, ignore this advisory and proceed."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in ("Agent", "Task"):
        return 0
    inp = payload.get("tool_input") or {}
    model = (inp.get("model") or "").lower()
    if model != "sonnet":
        return 0
    desc = (inp.get("description") or "").lower()
    if "codex fallback" in desc or "codex-fallback" in desc:
        return 0

    advisory = ADVISORY.format(tool=tool)

    out = {
        "systemMessage": (
            f"{tool}(model='sonnet') — consider Tier 2 (Haiku→codex) instead; "
            "Sonnet is the codex-unavailable fallback only."
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
