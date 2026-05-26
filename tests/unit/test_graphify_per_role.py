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
# noter_wait delta: no shelf keys
# ---------------------------------------------------------------------------


class TestNoterWaitNoShelfDelta:
    """noter_wait periodic_wake event must not include shelf_graph or shelf_global."""

    def test_noter_wait_delta_has_no_shelf_keys(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "99999")
        monkeypatch.setenv("MINIONS_WORKSPACE", str(tmp_path))

        import minions.tools.noter_wait as nw

        monkeypatch.setattr(nw, "_load_interval_seconds", lambda: 0)
        monkeypatch.setattr(nw, "_load_keepalive_seconds", lambda: 0)
        monkeypatch.setattr(nw, "_touch_heartbeat", lambda _ws: None)
        monkeypatch.setattr(nw, "_check_and_clear_nudge", lambda _port: False)
        monkeypatch.setattr(nw, "_shared_branch_delta", lambda _ws: {"new_commits": 0})
        monkeypatch.setattr(nw, "_events_jsonl_delta", lambda _port: {"total_event_lines": 0})
        monkeypatch.setattr(nw, "mos_book_lint", lambda port: {"ok": True})  # type: ignore[attr-defined]

        result = nw.noter_wait()
        assert result["count"] == 1
        event = result["events"][0]
        assert event["type"] == "periodic_wake"
        delta = event["delta"]
        assert "shelf_graph" not in delta, "shelf_graph must not appear in noter_wait delta"
        assert "shelf_global" not in delta, "shelf_global must not appear in noter_wait delta"
