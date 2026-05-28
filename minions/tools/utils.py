"""Shared utility functions for MinionsOS tools."""

from __future__ import annotations

import re

from minions.config import slugify

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi_escapes(text: str) -> str:
    """Strip ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


__all__ = ["slugify", "strip_ansi_escapes"]
