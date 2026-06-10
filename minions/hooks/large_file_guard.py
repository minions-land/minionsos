#!/usr/bin/env python3
"""
PreToolUse hook for Write / Edit.

Blocks calls that are likely to stall the tool, time out, or produce a
half-written file, and routes the next turn into the reliable file-IO
procedure.
The hook trips on four independent signals:

  1. Size: Write content > threshold lines.
  2. Content shape: many code fences, CJK characters, math segments, smart
     quotes, dashes, or heredoc-collision tokens.
  3. Edit fragility: old_string with trailing whitespace/NBSP, or new_string
     with risky shape.
  4. Session-tainted path: once Write/Edit has failed on a path this session
     (recorded by edit_failure_rescue.py), later Write/Edit calls on the same
     path are blocked.

When blocked, the hook exits 2 with stderr guidance; Claude Code feeds that
stderr to the model as a tool error so the next turn is steered into the
reliable file-IO procedure.

Allowed tools and small/clean Write/Edit calls pass through with exit 0.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

THRESHOLD_LINES = 550
HEAVY_NEW_STRING_LINES = 500
LONG_OLD_STRING_LINES = 400
CJK_CHAR_THRESHOLD = 5000
FENCE_THRESHOLD = 150
MATH_THRESHOLD = 500
SMART_QUOTE_THRESHOLD = 200
HEREDOC_TOKEN_RE = re.compile(r"(^|\n)(EOF|PY|MARK|CHUNK_[A-Za-z0-9_]*)\s*(\n|$)")

TAINT_DIR = Path("/tmp/claude_taint")

GUIDANCE_HEADER = "Skill required: reliable-file-io"
GUIDANCE_TEMPLATE = (
    "{header}\n"
    "Reason: {reason}\n"
    "Action: open the reliable file-IO procedure before writing. In a "
    "MinionsOS checkout, read `minions/roles/common/skills/reliable-file-io.md`. "
    "The procedure uses Python pathlib + atomic rename inside one quoted heredoc "
    "and produces an identical file. "
    "Covers all three cases: large generation, anchor-based update, and append.\n"
    "Do NOT retry plain Write/Edit on this path; first failure on a path is "
    "a one-way door for the rest of this session."
)

SMART_PUNCT = {
    "\u2018",
    "\u2019",
    "\u201c",
    "\u201d",
    "\u2013",
    "\u2014",
    "\u2026",
}


def _count_lines(text: str) -> int:
    if not text:
        return 0
    n = text.count("\n")
    if not text.endswith("\n"):
        n += 1
    return n


def _count_cjk(text: str) -> int:
    n = 0
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x30FF
            or 0x3400 <= cp <= 0x4DBF
            or 0x4E00 <= cp <= 0x9FFF
            or 0xAC00 <= cp <= 0xD7AF
            or 0xF900 <= cp <= 0xFAFF
            or 0x20000 <= cp <= 0x2FFFF
        ):
            n += 1
    return n


def _count_fences(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("```"))


def _count_math(text: str) -> int:
    block = text.count("$$")
    inline = sum(line.count("$") for line in text.splitlines())
    inline -= block * 2
    return max(0, inline // 2) + block // 2


def _count_smart_punct(text: str) -> int:
    return sum(1 for ch in text if ch in SMART_PUNCT)


def _has_heredoc_token(text: str) -> bool:
    return bool(HEREDOC_TOKEN_RE.search(text))


def _content_shape_reasons(text: str, label: str) -> list[str]:
    reasons: list[str] = []
    cjk = _count_cjk(text)
    if cjk >= CJK_CHAR_THRESHOLD:
        reasons.append(f"{label} contains {cjk} CJK chars")
    fences = _count_fences(text)
    if fences >= FENCE_THRESHOLD:
        reasons.append(f"{label} contains {fences} code-fence lines")
    math = _count_math(text)
    if math >= MATH_THRESHOLD:
        reasons.append(f"{label} contains {math} math segments")
    smart = _count_smart_punct(text)
    if smart >= SMART_QUOTE_THRESHOLD:
        reasons.append(f"{label} contains {smart} smart-quote/dash chars")
    if _has_heredoc_token(text):
        reasons.append(f"{label} contains heredoc-collision tokens (EOF/PY/MARK/CHUNK_*)")
    return reasons


def _has_fragile_whitespace(s: str) -> bool:
    if not s:
        return False
    for line in s.splitlines():
        if line.endswith(" ") or line.endswith("\t"):
            return True
        if "\u00a0" in line:
            return True
    return False


def _session_id(payload: dict) -> str:
    sid = payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID") or ""
    return re.sub(r"[^A-Za-z0-9_-]", "_", sid)[:64]


def _is_path_tainted(session: str, path: str) -> bool:
    if not session or not path:
        return False
    f = TAINT_DIR / f"{session}.txt"
    try:
        if not f.is_file():
            return False
        norm = os.path.realpath(path)
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip() == norm:
                    return True
    except OSError:
        return False
    return False


def _emit_block(reasons: list[str]) -> int:
    reason = "; ".join(reasons) if reasons else "size or content threshold exceeded"
    sys.stderr.write(GUIDANCE_TEMPLATE.format(header=GUIDANCE_HEADER, reason=reason))
    return 2


def _check_write(payload: dict, inp: dict) -> int:
    content = inp.get("content", "") or ""
    reasons: list[str] = []

    lines = _count_lines(content)
    if lines > THRESHOLD_LINES:
        reasons.append(f"Write payload is {lines} lines (threshold {THRESHOLD_LINES})")
    reasons.extend(_content_shape_reasons(content, "Write content"))

    path = inp.get("file_path", "") or ""
    sid = _session_id(payload)
    if _is_path_tainted(sid, path):
        reasons.append(f"path {path} already had a failed Write/Edit this session")

    if reasons:
        return _emit_block(reasons)
    return 0


def _check_edit(payload: dict, inp: dict) -> int:
    path = inp.get("file_path", "") or ""
    old_s = inp.get("old_string", "") or ""
    new_s = inp.get("new_string", "") or ""
    reasons: list[str] = []

    new_lines = _count_lines(new_s)
    if new_lines > HEAVY_NEW_STRING_LINES:
        reasons.append(f"new_string is {new_lines} lines (heavy)")

    old_lines = _count_lines(old_s)
    if old_lines > LONG_OLD_STRING_LINES:
        reasons.append(f"old_string is {old_lines} lines (matching gets fragile)")
    if _has_fragile_whitespace(old_s):
        reasons.append("old_string has trailing whitespace or NBSP (matching may break)")

    reasons.extend(_content_shape_reasons(new_s, "new_string"))

    sid = _session_id(payload)
    if _is_path_tainted(sid, path):
        reasons.append(f"path {path} already had a failed Write/Edit this session")

    if reasons:
        return _emit_block(reasons)
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input") or {}

    if tool == "Write":
        return _check_write(payload, inp)
    if tool == "Edit":
        return _check_edit(payload, inp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
