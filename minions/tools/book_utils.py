"""Utility functions extracted from book.py to reduce file size.

These are pure helper functions with no dependencies on Book-specific state.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(tz=UTC).isoformat()


def quoted(s: str) -> str:
    """Quote a string for YAML frontmatter using JSON encoding.

    Always quotes to ensure consistent behavior and avoid YAML edge cases.
    """
    return json.dumps(s, ensure_ascii=False)


def validate_component(label: str, component: str) -> None:
    """Validate a path component (slug, role name, etc) per Book rules.

    Rules:
    - Non-empty
    - Starts with alphanumeric
    - Contains only alphanumeric, underscore, dot, hyphen
    - No path separators

    Raises BookError if invalid.
    """
    import re

    from minions.errors import BookError

    if not component:
        raise BookError(f"{label} must be non-empty")
    if "/" in component or "\\" in component:
        raise BookError(f"{label} must not contain path separators: {component!r}")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", component):
        raise BookError(
            f"{label} must start with alphanumeric and contain only "
            f"alphanumeric/underscore/dot/hyphen: {component!r}"
        )


def atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically via temp file + rename."""
    import contextlib

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.rename(tmp_path, path)
    except Exception:
        with contextlib.suppress(Exception):
            os.close(fd)
        with contextlib.suppress(Exception):
            os.unlink(tmp_path)
        raise
