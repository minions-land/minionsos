"""MinionsOS MCP server — split across domain submodules.

This package owns the singleton :data:`mcp` :class:`FastMCP` instance and
imports every domain submodule so each ``@mcp.tool()`` registration runs
at package load. Tools, helpers, and arg models live in the submodules;
this file only wires the registry and exposes the public surface.

Legacy ``from minions.tools.mcp_server import …`` paths remain valid via
the shim at :mod:`minions.tools.mcp_server`.
"""

from __future__ import annotations

import logging

from minions.logging_setup import configure_logging
from minions.tools.mcp._registry import mcp

configure_logging()
logger = logging.getLogger(__name__)

# Importing submodules triggers @mcp.tool() side effects.
from minions.tools.mcp import (  # noqa: E402, F401
    evaluator_tools,
    experiment_tools,
    memory_tools,
    paper_tools,
    project_tools,
    publish_tools,
    reel_tools,
    role_evolution_tools,
    runtime_tools,
    signboard_tools,
    spawn_tools,
    visual_tools,
)
from minions.tools.mcp._common import (  # noqa: E402
    _MINIONS_MCP_TOOL_NAMES,
    allowed_tool_names_for_profile,
    configure_mcp_tool_profile,
)


def main() -> None:
    """Run the MCP server over stdio."""
    configure_mcp_tool_profile()
    mcp.run()


__all__ = [
    "_MINIONS_MCP_TOOL_NAMES",
    "allowed_tool_names_for_profile",
    "configure_mcp_tool_profile",
    "main",
    "mcp",
]
