"""MCP server registry singleton.

Holds the :data:`mcp` :class:`FastMCP` instance, separated from
:mod:`minions.tools.mcp` (``__init__.py``) so :mod:`minions.tools.mcp._common`
can import it without forming a package-init circular import.
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("minions")

__all__ = ["mcp"]
