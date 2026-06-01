"""Backward-compatibility shim for the MinionsOS MCP server.

The server has been split into :mod:`minions.tools.mcp` (a package) so each
domain owns ~100-200 lines instead of all tools sharing one 1700-line
file. External entry points still target this module:

- ``.mcp.json`` → ``python -m minions.tools.mcp_server``
- ``tests/unit/test_mcp_authz.py`` → ``from minions.tools.mcp_server
  import _require_tool_allowed``
- ``tests/unit/test_project_checkpoint.py`` /
  ``tests/unit/test_scaffold_audit.py`` → ``from minions.tools import
  mcp_server``

All those paths keep working via the re-exports below. New code should
import from :mod:`minions.tools.mcp` directly.
"""

from __future__ import annotations

from minions.tools.mcp import (
    _MINIONS_MCP_TOOL_NAMES,
    allowed_tool_names_for_profile,
    configure_mcp_tool_profile,
    main,
    mcp,
)
from minions.tools.mcp._common import (
    _enforce_caller_identity,
    _enforce_caller_project,
    _normalise_role_name,
    _require_tool_allowed,
)

__all__ = [
    "_MINIONS_MCP_TOOL_NAMES",
    "_enforce_caller_identity",
    "_enforce_caller_project",
    "_normalise_role_name",
    "_require_tool_allowed",
    "allowed_tool_names_for_profile",
    "configure_mcp_tool_profile",
    "main",
    "mcp",
]


if __name__ == "__main__":
    main()
