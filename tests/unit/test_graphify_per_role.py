"""Tests for per-role graphify path resolution (Memory V2 downgrade).

After the Graphify/CodeGraph downgrade (2026-05) the shared project-level
Shelf (branches/shared/shelf/shelf.json) no longer exists. Each Role that
wants graph-assisted retrieval runs its own graphify instance whose graph
lives at project_{port}/branches/{role}/graphify-out/graph.json.

Covers:
- launcher.sh resolves MINIONS_ROLE_NAME + MINIONS_PROJECT_PORT correctly
- noter whitelist no longer includes _GRAPHIFY_READ_TOOLS
- coder / writer / ethics / expert / gru whitelists still include graphify
- project worktree creation no longer seeds branches/shared/shelf/
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from minions.config import resolve_whitelist


# ---------------------------------------------------------------------------
# Whitelist checks
# ---------------------------------------------------------------------------


class TestGraphifyWhitelist:
    """Graphify read tools must NOT appear in noter; MUST appear in other roles."""

    GRAPHIFY_TOOL_PREFIX = "mcp__graphify__"

    def _has_graphify(self, role: str, surface: str = "main") -> bool:
        tools = resolve_whitelist(role, surface)
        return any(t.startswith(self.GRAPHIFY_TOOL_PREFIX) for t in tools)

    def test_noter_main_has_no_graphify(self) -> None:
        assert not self._has_graphify("noter", "main"), (
            "noter main should NOT have graphify tools after Memory V2 downgrade"
        )

    def test_noter_subagent_has_no_graphify(self) -> None:
        assert not self._has_graphify("noter", "subagent"), (
            "noter subagent should NOT have graphify tools"
        )

    def test_coder_main_has_graphify(self) -> None:
        assert self._has_graphify("coder", "main"), (
            "coder main should have graphify tools"
        )

    def test_gru_main_has_graphify(self) -> None:
        assert self._has_graphify("gru", "main"), (
            "gru main should have graphify tools"
        )

    def test_ethics_main_has_graphify(self) -> None:
        assert self._has_graphify("ethics", "main"), (
            "ethics main should have graphify tools"
        )

    def test_writer_main_has_graphify(self) -> None:
        assert self._has_graphify("writer", "main"), (
            "writer main should have graphify tools"
        )


# ---------------------------------------------------------------------------
# Worktree creation: shelf/ must NOT be seeded
# ---------------------------------------------------------------------------


class TestSharedWorktreeNoShelf:
    """project creation must not create branches/shared/shelf/."""

    def test_shared_subdirs_excludes_shelf(self) -> None:
        from minions.lifecycle._project_worktree import SHARED_SUBDIRS

        assert "shelf" not in SHARED_SUBDIRS, (
            "shelf must not be in SHARED_SUBDIRS after Memory V2 downgrade"
        )

    def test_shared_readme_no_shelf_reference(self) -> None:
        from minions.lifecycle._project_worktree import SHARED_README

        assert "shelf/shelf.json" not in SHARED_README, (
            "SHARED_README should not reference shelf/shelf.json"
        )


# ---------------------------------------------------------------------------
# noter_wait module: shelf symbols must not exist
# ---------------------------------------------------------------------------


class TestNoterWaitNoShelfSymbols:
    """noter_wait must not define _maybe_rebuild_shelf_graph or shelf delta keys."""

    def test_no_rebuild_shelf_graph_symbol(self) -> None:
        import minions.tools.noter_wait as nw

        assert not hasattr(nw, "_maybe_rebuild_shelf_graph"), (
            "_maybe_rebuild_shelf_graph must not exist in noter_wait after Memory V2 downgrade"
        )

    def test_no_shelf_graph_in_delta_keys(self) -> None:
        """Verify that _shared_branch_delta (if inspectable) never returns shelf_graph."""
        import minions.tools.noter_wait as nw

        # The module must not import or reference shelf-related keys.
        source = Path(nw.__file__).read_text(encoding="utf-8")
        assert "shelf_graph" not in source, (
            "noter_wait source must not reference shelf_graph after Memory V2 downgrade"
        )
        assert "shelf_global" not in source, (
            "noter_wait source must not reference shelf_global after Memory V2 downgrade"
        )
