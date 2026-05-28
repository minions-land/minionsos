from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolOutputDigest:
    tool_name: str
    args_hash: str
    output_chars: int
    truncated: bool
