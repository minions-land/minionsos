#!/usr/bin/env python3
"""PreToolUse hook for Write / Edit / Bash.

Defends MinionsOS Role processes against the runtime attacks the scaffold
audit cannot statically detect (R1, R3, R5 in the red-team report):

  - **R1 / R5**: a role with Bash access could ``git checkout`` another
    role's branch and write directly, bypassing ``mos_publish_to_shared``
    and its per-role subdir policy.
  - **R3**: a role with Write access could overwrite ``.mcp.json`` to
    point an MCP server at a malicious binary, or rewrite files inside
    ``mcp-servers/`` to compromise the next role respawn.

The hook reads the active role from ``MINIONS_ROLE_NAME`` and resolves the
role's allowed write roots from the project workspace layout. Writes
outside the role's branch (or to the trust-root files: ``.mcp.json``,
``mcp-servers/``, ``minions/config/``) are rejected with exit 2.

The hook is pessimistic by design: when in doubt, it blocks. Genuine
cross-role artifacts must travel through ``mos_publish_to_shared``; system
    maintenance edits to ``minions/`` itself are allowed only when the role's
    SYSTEM.md explicitly grants the system-maintenance scope, controlled by the
    ``MINIONS_ALLOW_SYSTEM_MAINT`` env var the launcher sets when Gru/the
    author scopes a maintenance task.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

# Trust-root paths every role is forbidden from writing without explicit
# system-maintenance scope. Relative paths are resolved against MINIONS_ROOT.
_TRUST_ROOTS: tuple[str, ...] = (
    ".mcp.json",
    "mcp-servers/",
    "minions/config/",
    ".claude/",
)

_GIT_WRITE_VERBS = re.compile(
    r"(?:^|[\s;|&])git\b[^;|&]*?\b(?:add|commit|reset|checkout|restore|rm|mv|"
    r"stash|push|merge|rebase|cherry-pick|am|apply|switch)\b"
)


def _project_root() -> Path:
    here = Path(__file__).resolve()
    return here.parent.parent.parent


def _allowed_role_roots(role: str, project_port: str) -> list[Path]:
    """Return the absolute paths the role is allowed to write to."""
    repo = _project_root()
    if not project_port or role in {"", "gru"}:
        # Gru and out-of-project sessions get the whole repo.
        return [repo]
    project_dir = repo / f"project_{project_port}"
    branch_dir_name = role
    # Accept all three expert-name shapes: expert / expert-<slug> / <slug>-expert.
    is_expert = role == "expert" or role.startswith("expert-") or role.endswith("-expert")
    if is_expert:
        branch_dir_name = role
    return [
        project_dir / "branches" / branch_dir_name,
        project_dir / "branches" / "main"
        if role == "gru"
        else project_dir / "branches" / branch_dir_name,
    ]


def _is_under(path: Path, roots: list[Path]) -> bool:
    try:
        target = path.resolve()
    except OSError:
        target = path
    for root in roots:
        try:
            target.relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def _trust_root_paths(repo: Path) -> list[Path]:
    return [(repo / r).resolve() for r in _TRUST_ROOTS]


def _block(reason: str) -> None:
    sys.stderr.write(f"[write-boundary] BLOCKED: {reason}\n")
    sys.exit(2)


def _check_path(target: Path, role: str, project_port: str) -> None:
    repo = _project_root()
    target = (target if target.is_absolute() else repo / target).resolve()

    # Trust-root protection (R3): no role may write .mcp.json / mcp-servers /
    # config without system-maintenance scope.
    if any(_path_starts_with(target, root) for root in _trust_root_paths(repo)):
        if os.environ.get("MINIONS_ALLOW_SYSTEM_MAINT", "").strip() == "1":
            return
        _block(
            f"path {target} is a trust root; system-maintenance scope required."
            " Ask Gru or the author to set MINIONS_ALLOW_SYSTEM_MAINT=1 for the"
            " specific scoped task."
        )

    # Role write boundary (R1 / R5): writes must land under the role's branch.
    roots = _allowed_role_roots(role, project_port)
    if not _is_under(target, roots):
        _block(
            f"path {target} is outside role {role!r}'s write boundary"
            f" ({[str(r) for r in roots]}). Use mos_publish_to_shared"
            " to land cross-role artifacts."
        )


def _path_starts_with(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _check_bash(command: str, role: str, project_port: str) -> None:
    if not _GIT_WRITE_VERBS.search(command):
        return
    # Best-effort cwd detection: if the command sets cwd via `git -C <dir>`
    # or a leading `cd <dir> && ...`, target that dir.
    cwd_match = re.search(r"git\s+-C\s+(\S+)", command)
    if cwd_match:
        target = Path(_unquote(cwd_match.group(1)))
        _check_path(target, role, project_port)
        return
    cd_match = re.search(r"\bcd\s+(\S+)", command)
    if cd_match:
        target = Path(_unquote(cd_match.group(1)))
        _check_path(target, role, project_port)
        return
    # Fall back to the process cwd; if we can't resolve, conservatively block
    # cross-branch git verbs.
    try:
        target = Path.cwd()
    except OSError:
        target = _project_root()
    _check_path(target, role, project_port)


def _unquote(token: str) -> str:
    parts = shlex.split(token)
    return parts[0] if parts else token


def main() -> None:
    if os.environ.get("MINIONS_DISABLE_WRITE_BOUNDARY", "").strip() == "1":
        return
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    if not role:
        return  # Not running as a role process; let it through.
    project_port = os.environ.get("MINIONS_PROJECT_PORT", "").strip()

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return
    tool = payload.get("tool_name") or payload.get("tool") or ""
    inp = payload.get("tool_input") or payload.get("arguments") or {}

    if tool in {"Write", "Edit"}:
        path = inp.get("file_path") or inp.get("path") or ""
        if path:
            _check_path(Path(path), role, project_port)
    elif tool == "Bash":
        cmd = inp.get("command") or ""
        if cmd:
            _check_bash(cmd, role, project_port)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive: never crash a tool call
        sys.stderr.write(f"[write-boundary] hook error (allowing): {exc}\n")
        sys.exit(0)
