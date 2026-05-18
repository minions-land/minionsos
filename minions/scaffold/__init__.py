"""MinionsOS development scaffold.

Two surfaces:

* :mod:`minions.scaffold.generators` emits stub files for the five extension
  points listed in ``minions/CLAUDE.md`` (Role, Role skill, review template,
  Expert domain, MCP tool) plus a checklist of *manual* follow-up edits the
  generator cannot safely make on its own (whitelist updates, table rows,
  test coverage). Generation deliberately stops at the boundary of "code that
  must be reviewed" — it never silently mutates ``minions/config/__init__.py``,
  ``minions/lifecycle/role.py``, or root ``CLAUDE.md``.

* :mod:`minions.scaffold.audit` cross-checks the contract surfaces that
  ``CLAUDE.md`` declares against what the codebase actually contains: the
  role whitelist, publish-policy table, FIXED_ROLES, role boundary text,
  ``.mcp.json`` server registry, and the ``mcp-servers/README.md`` registry.

The CLI is wired in :mod:`minions.scaffold.cli` and exposed as
``mos scaffold`` / ``mos audit``.
"""

from __future__ import annotations

from minions.scaffold.audit import Issue
from minions.scaffold.contracts import EXTENSION_POINTS, ExtensionPoint

__all__ = ["EXTENSION_POINTS", "ExtensionPoint", "Issue"]
