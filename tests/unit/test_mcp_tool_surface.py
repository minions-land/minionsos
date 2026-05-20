"""Pin the public MCP tool surface so any drift fails CI loudly.

When a tool is added to a submodule under ``minions/tools/mcp/`` but its
name is not registered in :data:`_MINIONS_MCP_TOOL_NAMES`, role profiles
won't filter it correctly. When the reverse happens, allow-lists keep
referencing a tool that's no longer registered.

This test is also the cheapest place to catch "forgot to import the new
submodule from ``minions.tools.mcp.__init__``" — that bug would silently
drop tools at runtime.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

from minions.scaffold.contracts import list_registered_mcp_tools
from minions.tools.mcp import _MINIONS_MCP_TOOL_NAMES, mcp


def test_registry_matches_decorated_tools() -> None:
    """_MINIONS_MCP_TOOL_NAMES is the source of truth for advertised surface."""
    decorated = set(list_registered_mcp_tools())
    extra = decorated - _MINIONS_MCP_TOOL_NAMES
    missing = _MINIONS_MCP_TOOL_NAMES - decorated
    assert not extra, f"@mcp.tool functions not in _MINIONS_MCP_TOOL_NAMES: {sorted(extra)}"
    assert not missing, f"_MINIONS_MCP_TOOL_NAMES references unregistered tools: {sorted(missing)}"


def test_live_mcp_instance_registers_full_surface() -> None:
    """Importing the package should land every tool on the live FastMCP instance.

    Catches the case where a submodule exists but ``minions/tools/mcp/__init__.py``
    forgot to import it.
    """
    with patch.dict(os.environ, {"MINIONS_DISABLE_MCP_AUTHZ": "1"}, clear=False):
        live = asyncio.run(mcp.list_tools())
        live_names = {t.name for t in live} if not isinstance(live, dict) else set(live.keys())
        assert live_names >= _MINIONS_MCP_TOOL_NAMES, (
            f"FastMCP missing registered tools: {sorted(_MINIONS_MCP_TOOL_NAMES - live_names)}"
        )
