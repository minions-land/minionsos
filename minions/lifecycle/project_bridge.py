"""mos_project_bridge: cross-project message bridge via EACN3.

Gru is the only agent that may call this. It posts a formatted message
with source attribution to the destination project's EACN backend via
``POST /api/messages``.

This module re-exports the canonical implementation in
``minions.tools.project_bridge`` so lifecycle code can keep its imports
namespaced under ``minions.lifecycle``.
"""

from __future__ import annotations

from minions.tools.project_bridge import (
    BridgeMode,
    format_bridge_message,
    project_bridge,
)

__all__ = ["BridgeMode", "format_bridge_message", "project_bridge"]
