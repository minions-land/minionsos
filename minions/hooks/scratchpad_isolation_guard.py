#!/usr/bin/env python3
"""PreToolUse hook for Workflow / Write / Edit / Bash / Task.

Enforces the canonical Workflow scratchpad path for Role processes:

    $MINIONS_ROLE_BRANCH/.claude/scratchpad/

Forbidden: any other ``.claude/`` directory — host-shared
``~/.claude/``, repo-shared ``/Users/mjm/MinionsOS/.claude/``,
project-root ``projects/project_<port>/.claude/``, or another role's
branch ``branches/<other>/.claude/``. Under hermetic mode
(``MINIONS_ROLE_HERMETIC_CWD=1``) the canonical scratchpad lives
inside the hermetic stub at ``$MINIONS_ROLE_HERMETIC_DIR/.claude/
scratchpad/``; ``reel_capture`` ports meaningful transcripts back
into the role's branch reel.

The hook is fail-closed on parse errors that look hostile but exits 0
on missing env (so developer sessions outside a Role are unaffected).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

_PATH_KEYS = ("file_path", "path", "filePath", "filename")
_BASH_CD_RE = re.compile(r"(?:^|[\s;|&])cd\s+([^\s;|&]+)")
_BASH_MKDIR_RE = re.compile(r"(?:^|[\s;|&])mkdir(?:\s+-[a-z]+)*\s+([^\s;|&]+(?:\s+[^\s;|&]+)*)")
_BASH_DOTCLAUDE_WRITE = re.compile(
    r"(?:^|[\s;|&])(?:>|>>|tee|cp|mv|rsync|install|touch)\s+\S*\.claude\b"
)


def _legal_roots() -> list[Path]:
    """Paths under which a Role's `.claude/scratchpad/` is permitted to live."""
    roots: list[Path] = []
    branch = os.environ.get("MINIONS_ROLE_BRANCH") or os.environ.get("MINIONS_ROLE_WORKSPACE")
    if branch:
        with contextlib.suppress(OSError):
            roots.append(Path(branch).resolve(strict=False))
    hermetic = os.environ.get("MINIONS_ROLE_HERMETIC_DIR")
    if hermetic:
        with contextlib.suppress(OSError):
            roots.append(Path(hermetic).resolve(strict=False))
    return roots


def _resolve(path_str: str) -> Path | None:
    if not path_str:
        return None
    try:
        return Path(path_str).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None


def _is_under(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _is_dotclaude_path(target: Path) -> bool:
    """True iff target's path traverses a .claude directory."""
    return any(part == ".claude" for part in target.parts)


def _is_legal_scratchpad(target: Path, legal_roots: list[Path]) -> bool:
    """A `.claude/` path is legal only when it lives under
    `<legal_root>/.claude/scratchpad/` for some legal_root."""
    for root in legal_roots:
        legal = root / ".claude" / "scratchpad"
        if _is_under(target, legal):
            return True
        # Also permit reads/writes to skill symlinks under .claude/skills/ ;
        # workflow_plugins.inject_skills_to_workspace recreates them on
        # respawn and roles legitimately need to introspect them.
        skills = root / ".claude" / "skills"
        if _is_under(target, skills):
            return True
    return False


def _block(reason: str) -> int:
    sys.stderr.write(
        "scratchpad_isolation_guard: blocked.\n"
        f"reason: {reason}\n"
        "Canonical scratchpad path: $MINIONS_ROLE_BRANCH/.claude/scratchpad/\n"
        "(Hermetic: $MINIONS_ROLE_HERMETIC_DIR/.claude/scratchpad/.)\n"
        "Forbidden:\n"
        "  - ~/.claude/ (host-shared)\n"
        "  - /Users/mjm/MinionsOS/.claude/ (repo-shared dev workspace)\n"
        "  - projects/project_*/.claude/ (project root)\n"
        "  - branches/<other-role>/.claude/ (cross-role)\n"
        "If a Workflow agent needs scratch, scope it to the canonical path.\n"
    )
    return 2


def _check_path(target: Path, legal_roots: list[Path], context: str) -> int:
    if not _is_dotclaude_path(target):
        return 0
    if _is_legal_scratchpad(target, legal_roots):
        return 0
    return _block(f"{context} -> {target}")


def _check_bash(command: str, legal_roots: list[Path]) -> int:
    """Inspect a Bash command for cd / mkdir / write redirections targeting
    .claude paths outside the legal scratchpad."""
    # cd <target> : reject if target lands in a non-legal .claude path.
    for match in _BASH_CD_RE.finditer(command):
        raw = match.group(1).strip("\"'")
        target = _resolve(raw)
        if target is None:
            continue
        rc = _check_path(target, legal_roots, f"Bash cd into {raw}")
        if rc != 0:
            return rc
    # mkdir [opts] <a> [b ...] : reject if any arg is a non-legal .claude path.
    for match in _BASH_MKDIR_RE.finditer(command):
        for token in shlex.split(match.group(1)):
            target = _resolve(token)
            if target is None:
                continue
            rc = _check_path(target, legal_roots, f"Bash mkdir of {token}")
            if rc != 0:
                return rc
    # Catch-all: > / >> / tee / cp / mv / rsync / install / touch into a
    # path containing .claude. The caller should be using the legal root.
    if _BASH_DOTCLAUDE_WRITE.search(command):
        for token in shlex.split(command, posix=True, comments=False):
            if ".claude" not in token:
                continue
            target = _resolve(token)
            if target is None:
                continue
            rc = _check_path(target, legal_roots, f"Bash write to {token}")
            if rc != 0:
                return rc
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Hostile or malformed payload: fail-closed only when env claims
        # we are inside a Role; otherwise pass through.
        if os.environ.get("MINIONS_ROLE_NAME"):
            sys.stderr.write("scratchpad_isolation_guard: malformed payload\n")
            return 2
        return 0

    tool = payload.get("tool_name", "") or ""
    inp = payload.get("tool_input") or {}

    legal_roots = _legal_roots()
    # If we don't know the role's legal root (developer session outside a
    # Role process), do not enforce — the rule is Role-specific.
    if not legal_roots:
        return 0

    if tool == "Bash":
        cmd = inp.get("command", "") or ""
        return _check_bash(cmd, legal_roots)

    # Path-shaped tools: Write, Edit, NotebookEdit, Read (read can leak too
    # via copy-back), Workflow, Task.
    for key in _PATH_KEYS:
        raw = inp.get(key)
        if not raw:
            continue
        target = _resolve(raw)
        if target is None:
            continue
        rc = _check_path(target, legal_roots, f"{tool} {key}={raw}")
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
