"""Phase 3 tests: role classification, boundary enforcement, write boundaries."""

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

    def test_experimenter_removed(self) -> None:
        """Experimenter role has been retired; its tools moved to Coder."""
        assert "experimenter" not in ROLE_CLASSIFICATION

    def test_ethics_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["ethics"] == RoleType.eacn_visible

    def test_expert_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["expert"] == RoleType.eacn_visible

    def test_reviewer_not_a_role(self) -> None:
        """Review is run by the mos_review_run MCP tool, not by a Role."""
        assert "reviewer" not in ROLE_CLASSIFICATION
        assert "reviewer" not in FIXED_ROLES


class TestWriteBoundaries:
    """MinionsOS role write boundaries live under each role branch plus allowed
    ``branches/shared/<subdir>/`` publish surfaces."""

    def test_noter_cannot_write_branches(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["noter"]
        # Noter owns its own drafts and the curated shared notes/DAG surfaces;
        # it never writes to any other role's branch.
        assert not any(p.startswith("branches/coder/") for p in allowed)
        assert not any(p.startswith("branches/writer/") for p in allowed)
        assert any(p.startswith("branches/noter/") for p in allowed)
        assert any(p.startswith("branches/shared/notes/") for p in allowed)
        assert any("branches/shared/exploration/dag.json" in p for p in allowed)

    def test_coder_owns_its_branch(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["coder"]
        assert any(p.startswith("branches/coder/") for p in allowed)

    def test_ethics_restricted_to_ethics_branch_and_shared_surface(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["ethics"]
        assert any(p.startswith("branches/ethics/") for p in allowed)
        assert any(p.startswith("branches/shared/ethics/") for p in allowed)
        # Ethics must not write into any other role's branch worktree.
        assert not any(
            p.startswith("branches/")
            and not p.startswith("branches/ethics/")
            and not p.startswith("branches/shared/")
            for p in allowed
        )

    def test_no_role_writes_review_artifacts(self) -> None:
        """branches/shared/reviews/ is owned exclusively by mos_review_run."""
        for role, allowed in ROLE_WRITE_BOUNDARIES.items():
            assert not any(p.startswith("branches/shared/reviews/") for p in allowed), (
                f"role {role!r} declares write access to branches/shared/reviews/; "
                "that surface is owned by mos_review_run only."
            )


class TestBoundaryContext:
    def test_gru_boundary_mentions_human_side(self) -> None:
        ctx = _boundary_context("gru", 37596)
        assert "human-side" in ctx.lower() or "human_side" in ctx.lower()

    def test_noter_boundary_mentions_observer(self) -> None:
        ctx = _boundary_context("noter", 37596)
        assert "observer" in ctx.lower()
        assert "not on eacn3" in ctx.lower()
        assert "mos_noter_wait" in ctx

    def test_ethics_boundary_mentions_evidence(self) -> None:
        ctx = _boundary_context("ethics", 37596)
        assert "evidence" in ctx.lower()

    def test_coder_boundary_allows_own_branch(self) -> None:
        ctx = _boundary_context("coder", 37596)
        # Coder's write boundary in MinionsOS is its role branch, not the legacy
        # "workspace/" path.
        assert "branches/coder/" in ctx

    def test_coder_boundary_allows_assigned_system_maintenance(self) -> None:
        ctx = _boundary_context("coder", 37596)
        assert "system-maintenance" in ctx
        assert "MinionsOS repository runtime code" in ctx
        assert "explicitly assigns" in ctx

    def test_unknown_role_returns_generic(self) -> None:
        ctx = _boundary_context("unknown-role", 37596)
        assert len(ctx) > 0


class TestEthicsWhitelist:
    def test_non_gru_main_roles_can_spawn_subagents(self) -> None:
        for role in ("noter", "coder", "writer", "ethics", "expert"):
            assert "Task" in resolve_whitelist(role, "main")

    def test_ethics_has_no_write_tools(self) -> None:
        tools = resolve_whitelist("ethics", "main")
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools


class TestSubagentEacnInvisibility:
    """Subagents must never touch EACN3 through any surface. Main roles
    dispatch, subagents execute, subagents report back to main, main owns
    every EACN-facing action. This invariant is what lets the main session
    stay short and token-cheap."""

    _ALL_ROLES = ("gru", "noter", "coder", "writer", "ethics", "expert")

    def test_no_subagent_has_eacn3_tools(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "subagent")
            eacn_leaks = [t for t in tools if t.startswith("eacn3_") or t == "eacn3_*"]
            assert not eacn_leaks, (
                f"{role} subagent whitelist leaks raw EACN3 tools {eacn_leaks}; "
                "subagents must be EACN-invisible."
            )

    def test_no_subagent_has_cross_project_tools(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "subagent")
            leaks = [t for t in tools if t == "mos_project_bridge" or t.startswith("mos_project_")]
            assert not leaks, (
                f"{role} subagent whitelist leaks cross-project coordination tools {leaks}; "
                "these are Gru-main coordination tools, not subagent execution tools."
            )
