#!/usr/bin/env python3
"""
PostToolUseFailure hook for Write / Edit.

When Write or Edit fails, this hook:

  1. Taints the failed file path in /tmp/claude_taint/<session>.txt. The
     PreToolUse hook reads this file and blocks subsequent Write/Edit calls on
     the same path for the rest of the session.
  2. Emits additionalContext telling the model to recover with the reliable
     file-IO procedure instead of stopping or retrying plain Write/Edit.

The hook always exits 0; it never blocks work itself.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

TAINT_DIR = Path("/tmp/claude_taint")

NUDGE = (
    "Write/Edit just failed on this path. Do NOT stop and wait for the user, "
    "and do NOT retry plain Write/Edit on this path; it is now session-tainted. "
    "Open the reliable file-IO procedure immediately: read "
    "`minions/roles/common/skills/reliable-file-io.md`. Then "
    "use the anchor-based update template (Python pathlib + atomic rename "
    "inside one quoted heredoc). That path raises a precise Python error if "
    "the anchor is missing, so it is recoverable; staring at `Error editing "
    "file` is not."
)


def _session_id(payload: dict) -> str:
    sid = payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID") or ""
    return re.sub(r"[^A-Za-z0-9_-]", "_", sid)[:64]


def _record_taint(session: str, path: str) -> None:
    if not session or not path:
        return
    try:
        TAINT_DIR.mkdir(parents=True, exist_ok=True)
        f = TAINT_DIR / f"{session}.txt"
        norm = os.path.realpath(path)
        existing: set[str] = set()
        if f.is_file():
            with f.open("r", encoding="utf-8") as fh:
                existing = {ln.strip() for ln in fh if ln.strip()}
        if norm in existing:
            return
        with f.open("a", encoding="utf-8") as fh:
            fh.write(norm + "\n")
    except OSError:
        return


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        return 0

    inp = payload.get("tool_input") or {}
    path = inp.get("file_path", "") or ""
    sid = _session_id(payload)
    _record_taint(sid, path)

    output = {
        "systemMessage": "Edit/Write failed: path tainted, switch to reliable-file-io",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure",
            "additionalContext": NUDGE,
        },
    }
    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
