"""Whitelist resolver for MCP tool access control."""
from __future__ import annotations

from minions.config import resolve_whitelist
from minions.errors import RoleError


def resolve_allowed_tools(role: str) -> frozenset[str]:
    """Return the frozenset of allowed tool names for *role* (main agent).

    Raises ``RoleError`` if *role* is not in the whitelist registry.
    """
    tools = resolve_whitelist(role, "main")
    if not tools:
        raise RoleError(f"No whitelist entry for role {role!r}.")
    return frozenset(tools)
