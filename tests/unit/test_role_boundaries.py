"""Phase 3 tests: role classification, boundary enforcement, Reviewer isolation."""

from __future__ import annotations

from minions.config import (
    ROLE_CLASSIFICATION,
    ROLE_WRITE_BOUNDARIES,
    RoleType,
    resolve_whitelist,
)
from minions.lifecycle.role import FIXED_ROLES, _boundary_context


class TestRoleType:
    def test_enum_values(self) -> None:
        assert RoleType.human_side.value == "human_side"
        assert RoleType.eacn_visible.value == "eacn_visible"

    def test_all_fixed_roles_classified(self) -> None:
        for role in FIXED_ROLES:
            assert role in ROLE_CLASSIFICATION, f"{role} missing from ROLE_CLASSIFICATION"
        assert "gru" in ROLE_CLASSIFICATION

    def test_gru_is_human_side(self) -> None:
        assert ROLE_CLASSIFICATION["gru"] == RoleType.human_side

    def test_noter_is_human_side(self) -> None:
        assert ROLE_CLASSIFICATION["noter"] == RoleType.human_side

    def test_coder_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["coder"] == RoleType.eacn_visible

    def test_experimenter_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["experimenter"] == RoleType.eacn_visible

    def test_reviewer_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["reviewer"] == RoleType.eacn_visible

    def test_ethics_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["ethics"] == RoleType.eacn_visible

    def test_expert_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["expert"] == RoleType.eacn_visible


class TestWriteBoundaries:
    def test_noter_cannot_write_workspace(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["noter"]
        assert "workspace/" not in allowed
        assert "artifacts/notes/" in allowed

    def test_reviewer_cannot_write_workspace(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["reviewer"]
        assert "workspace/" not in allowed

    def test_coder_can_write_workspace(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["coder"]
        assert "workspace/" in allowed

    def test_ethics_restricted_to_ethics_artifacts(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["ethics"]
        assert "artifacts/ethics/" in allowed
        assert "workspace/" not in allowed


class TestBoundaryContext:
    def test_gru_boundary_mentions_human_side(self) -> None:
        ctx = _boundary_context("gru", 37596)
        assert "human-side" in ctx.lower() or "human_side" in ctx.lower()

    def test_noter_boundary_mentions_human_side(self) -> None:
        ctx = _boundary_context("noter", 37596)
        assert "human-side" in ctx.lower() or "human_side" in ctx.lower()

    def test_reviewer_boundary_mentions_isolation(self) -> None:
        ctx = _boundary_context("reviewer", 37596)
        assert "pdf" in ctx.lower() or "submission" in ctx.lower()

    def test_reviewer_boundary_forbids_internal(self) -> None:
        ctx = _boundary_context("reviewer", 37596)
        assert "internal" in ctx.lower() or "artifacts" in ctx.lower()

    def test_ethics_boundary_mentions_evidence(self) -> None:
        ctx = _boundary_context("ethics", 37596)
        assert "evidence" in ctx.lower()

    def test_coder_boundary_allows_workspace(self) -> None:
        ctx = _boundary_context("coder", 37596)
        assert "workspace" in ctx.lower()

    def test_unknown_role_returns_generic(self) -> None:
        ctx = _boundary_context("unknown-role", 37596)
        assert len(ctx) > 0


class TestReviewerWhitelistIsolation:
    def test_reviewer_has_no_write_tools(self) -> None:
        tools = resolve_whitelist("reviewer", "main")
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools

    def test_reviewer_subagent_has_no_write_tools(self) -> None:
        tools = resolve_whitelist("reviewer", "subagent")
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools

    def test_ethics_has_no_write_tools(self) -> None:
        tools = resolve_whitelist("ethics", "main")
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools
