"""Project-path placeholder substitution at the EACN3 boundary.

EACN3's `offline_messages.payload` is persisted as JSON. If roles embed absolute
project paths (e.g. `/.../data/projects/project_<port>/notes.md`) directly in
the payload, the resulting database is not portable: relocating the project or
sharing the worktree breaks role-to-role messaging history.

To fix this, MinionsOS substitutes the literal token `${PROJECT_DIR}` for the
project directory at the outgoing send seam, and hydrates it back to the live
project directory at the incoming read seam. The EACN3 server itself stays
project-agnostic; only the MinionsOS-side client/wrappers know the
port-to-directory mapping.

Substitution is intentionally narrow: a string is rewritten only when it is
exactly the project directory or starts with ``project_dir + os.sep``. Arbitrary
text containing a project path as a substring (e.g. log lines, prose) is left
untouched, so we never mangle free-form content.
"""

from __future__ import annotations

import os
from typing import Any

PROJECT_DIR_PLACEHOLDER = "${PROJECT_DIR}"


def _norm(path: str) -> str:
    return os.path.normpath(path)


def _encode_str(value: str, project_dir_norm: str) -> str:
    # Only rewrite when the string is exactly the project dir or has it as a
    # path prefix (followed by a separator). Substrings inside arbitrary text
    # are deliberately left untouched.
    sep = os.sep
    if value == project_dir_norm:
        return PROJECT_DIR_PLACEHOLDER
    prefix = project_dir_norm + sep
    if value.startswith(prefix):
        return PROJECT_DIR_PLACEHOLDER + sep + value[len(prefix):]
    return value


def _decode_str(value: str, project_dir_norm: str) -> str:
    if value == PROJECT_DIR_PLACEHOLDER:
        return project_dir_norm
    prefix = PROJECT_DIR_PLACEHOLDER + os.sep
    if value.startswith(prefix):
        return project_dir_norm + os.sep + value[len(prefix):]
    # Be lenient: also accept a forward-slash form for cross-platform safety.
    alt_prefix = PROJECT_DIR_PLACEHOLDER + "/"
    if value.startswith(alt_prefix):
        return project_dir_norm + os.sep + value[len(alt_prefix):]
    return value


def encode_project_paths(payload: Any, project_dir: str) -> Any:
    """Recursively replace project-dir prefixes with ``${PROJECT_DIR}``.

    Returns a new structure; the input is not mutated.
    """
    if not project_dir:
        return payload
    project_dir_norm = _norm(project_dir)
    return _walk(payload, lambda s: _encode_str(s, project_dir_norm))


def decode_project_paths(payload: Any, project_dir: str) -> Any:
    """Recursively replace ``${PROJECT_DIR}`` with the live project dir."""
    if not project_dir:
        return payload
    project_dir_norm = _norm(project_dir)
    return _walk(payload, lambda s: _decode_str(s, project_dir_norm))


def _walk(value: Any, fn) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {k: _walk(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    if isinstance(value, tuple):
        return tuple(_walk(v, fn) for v in value)
    return value
