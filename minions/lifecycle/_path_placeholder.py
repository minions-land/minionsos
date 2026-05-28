"""Path placeholder substitution for EACN3 payloads.

The ``offline_messages.payload`` column in ``eacn3.db`` is persisted as JSON.
If roles embed absolute paths (e.g. ``~/.minions/projects/project_37596/...``)
the DB row is no longer portable across hosts/users (issue #47).

We apply a two-sided substitution at the EACN3 boundary:

* Outgoing: replace any string that is *exactly* the project directory or that
  starts with ``project_dir + os.sep`` with ``${PROJECT_DIR}`` (+ the tail).
* Incoming: replace ``${PROJECT_DIR}`` (anywhere) back with the live
  ``project_dir``.

The encoder is intentionally conservative: it only touches strings that *are*
a project path, not arbitrary text that happens to mention one. So
``"see /.../project_37596/notes.md for details"`` is left alone -- only a bare
``"/.../project_37596/notes.md"`` gets rewritten. This avoids corrupting prose
or partial paths embedded inside larger strings.
"""

from __future__ import annotations

import os
from typing import Any

PROJECT_DIR_PLACEHOLDER = "${PROJECT_DIR}"


def _canon(path: str) -> str:
    return os.path.normpath(path)


def encode_project_paths(payload: Any, project_dir: str) -> Any:
    """Recursively replace project_dir-prefixed strings with the placeholder.

    Only strings that equal ``project_dir`` or start with ``project_dir + os.sep``
    are rewritten. Substrings embedded inside arbitrary text are not touched.
    """
    if not project_dir:
        return payload
    pdir = _canon(project_dir)
    return _encode(payload, pdir)


def _encode(value: Any, pdir: str) -> Any:
    if isinstance(value, str):
        if value == pdir:
            return PROJECT_DIR_PLACEHOLDER
        # Normalize only enough to compare a prefix; we don't normalize the
        # whole string because that would alter user content (collapse `//`,
        # strip trailing `/`, etc.).
        prefix = pdir + os.sep
        if value.startswith(prefix):
            return PROJECT_DIR_PLACEHOLDER + os.sep + value[len(prefix):]
        return value
    if isinstance(value, dict):
        return {k: _encode(v, pdir) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode(v, pdir) for v in value]
    if isinstance(value, tuple):
        return tuple(_encode(v, pdir) for v in value)
    return value


def decode_project_paths(payload: Any, project_dir: str) -> Any:
    """Recursively replace ``${PROJECT_DIR}`` with the live project directory."""
    if not project_dir:
        return payload
    pdir = _canon(project_dir)
    return _decode(payload, pdir)


def _decode(value: Any, pdir: str) -> Any:
    if isinstance(value, str):
        if PROJECT_DIR_PLACEHOLDER in value:
            return value.replace(PROJECT_DIR_PLACEHOLDER, pdir)
        return value
    if isinstance(value, dict):
        return {k: _decode(v, pdir) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v, pdir) for v in value]
    if isinstance(value, tuple):
        return tuple(_decode(v, pdir) for v in value)
    return value
