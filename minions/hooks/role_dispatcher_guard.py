#!/usr/bin/env python3
"""PreToolUse hook: nudge Role main agents toward Task-based dispatch.

Active only when ``MINIONS_AGENT_TYPE=main`` is set in env (Role main
processes; ``role_launcher._role_env`` sets this). On every other Claude
Code session this hook is a no-op.

The hook fires for ``Read`` and ``Bash`` because empirical session-jsonl
analysis shows those two tools account for 94% of uncached input tokens
in the main session. Catching them at the boundary preserves the main
session's prompt cache by routing heavy work into a disposable Task
subagent context.

Behavior (exit-code semantics matching ``large_file_guard.py``):

- ``exit 0``: silent pass. Either not a Role main, or the call is small
  enough that direct execution is fine.
- ``exit 2`` + stderr advisory: tool call exceeds the dispatcher
  budget. Claude Code feeds stderr to the model as a tool error; the
  next turn typically re-routes the call through ``Task``. The
  advisory text names the threshold and how to dispatch.

Thresholds (matched to the dispatcher-discipline skill):

- ``Read``: file size > 8192 bytes (~2k tokens). Below that the file is
  considered "metadata / config" and a direct read is allowed.
- ``Bash``: command has no output-bounding pipe (``head``, ``tail``,
  ``grep``, ``wc``, ``jq``, ``awk``, ``sed``, ``cut``, ``find -name``,
  ``ls``, redirection to ``/dev/null``) AND looks like a file
  enumeration / large-output command. Conservative on false positives.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

READ_BUDGET_BYTES = 8192  # ~2k tokens

# Bash commands that always produce small output (or whose output we don't
# bound but is harmless because they typically run for control-plane work).
_SMALL_BASH_PREFIX = (
    "git status",
    "git rev-parse",
    "git log --oneline -",
    "git tag",
    "git branch",
    "git remote -v",
    "echo ",
    "true",
    "false",
    "pwd",
    "date",
    "whoami",
    "uv run python -m minions.tools.cache_stats",
)

# Words that signal output-bounding so the command is safe.
_BOUNDING_TOKENS = re.compile(
    r"\|\s*(head|tail|grep|wc|jq|awk|sed|cut|fold|less)\b"
    r"|\>/dev/null"
    r"|\bls\s+-?\w*\s+\|\s*head"
    r"|\bfind\b.*-name\b"
    r"|\b2>&1\s*\|\s*tail"
)

# Words that signal likely-large output the user did not bound.
_LARGE_OUTPUT_TOKENS = re.compile(
    r"\bcat\b"
    r"|\bls\s+-l[aR]?\b"
    r"|\bfind\b(?!.*-name\b)"
    r"|\bgrep\b\s+-r"
    r"|\bnpm\s+(test|run)"
    r"|\bpytest\b"
    r"|\buv\s+run\s+pytest\b"
    r"|\bgit\s+diff\b"
    r"|\bgit\s+log\b"
)


def _is_role_main() -> bool:
    return os.environ.get("MINIONS_AGENT_TYPE", "") == "main"


def _emit_block(advisory: str) -> int:
    sys.stderr.write(advisory)
    return 2


def _check_read(inp: dict) -> int:
    path = inp.get("file_path") or ""
    if not path:
        return 0
    try:
        size = Path(path).stat().st_size
    except OSError:
        return 0  # file gone / unreadable — let Read fail naturally
    if size <= READ_BUDGET_BYTES:
        return 0
    return _emit_block(
        f"dispatcher-discipline: Read on {path} would inject ~{size // 4} tokens "
        f"into your main-session conversation history (file is {size} bytes; budget "
        f"is {READ_BUDGET_BYTES} bytes / ~2k tokens for direct main-session reads). "
        f"Dispatch via Task instead — the subagent reads the file in its disposable "
        f"context and returns a compact summary. See "
        f"minions/roles/common/skills/dispatcher-discipline.md for the prompt "
        f"template. If you genuinely need to keep the raw bytes in your context "
        f"(rare — almost never the right call for a long-lived Role), use "
        f"`Read(file_path='{path}', offset=0, limit=N)` with a narrow line slice."
    )


def _check_bash(inp: dict) -> int:
    cmd = inp.get("command") or ""
    if not cmd:
        return 0
    cmd_strip = cmd.strip()
    if cmd_strip.startswith(_SMALL_BASH_PREFIX):
        return 0
    if _BOUNDING_TOKENS.search(cmd):
        return 0
    if not _LARGE_OUTPUT_TOKENS.search(cmd):
        return 0
    return _emit_block(
        f"dispatcher-discipline: Bash command may produce unbounded output "
        f"and inject it into your main-session conversation history. Either:\n"
        f"  1. Bound output with `| head -100` / `| tail -100` / `| grep ...` / "
        f"`| wc -l` so the result fits in a few hundred tokens; or\n"
        f"  2. Dispatch via Task — the subagent runs the command, reads the "
        f"output in its disposable context, and returns a structured summary.\n"
        f"Command: {cmd[:200]}"
    )


def main() -> int:
    if not _is_role_main():
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    # Subagents spawned by the main Role inherit MINIONS_AGENT_TYPE from env,
    # but they carry a non-empty `agent_type` in the hook payload (e.g.
    # "general-purpose", "Explore"). Only enforce on the main agent itself
    # (agent_type absent or empty). This prevents the hook from blocking
    # subagent Reads and causing retry loops.
    if payload.get("agent_type"):
        return 0
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input") or {}
    if tool == "Read":
        return _check_read(inp)
    if tool == "Bash":
        return _check_bash(inp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
