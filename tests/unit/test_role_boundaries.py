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
    """MinionsOS role write boundaries live under ``branches/<role>/`` plus each role's
    artifact subdir. The legacy ``workspace/`` + ``memory/`` layout was retired
    when projects moved to per-role branch worktrees."""

    def test_noter_cannot_write_branches(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["noter"]
        # Noter only owns its own branch scratchpad; it never writes to any
        # other role's branch and does not touch the legacy "workspace/" path.
        assert not any(p.startswith("branches/coder/") for p in allowed)
        assert not any(p.startswith("branches/writer/") for p in allowed)
        assert "artifacts/notes/" in allowed

    def test_reviewer_cannot_write_branches(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["reviewer"]
        assert "artifacts/reviews/" in allowed
        assert not any(p.startswith("branches/coder/") for p in allowed)
        assert not any(p.startswith("branches/writer/") for p in allowed)

    def test_coder_owns_its_branch(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["coder"]
        assert any(p.startswith("branches/coder/") for p in allowed)

    def test_ethics_restricted_to_ethics_artifacts(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["ethics"]
        assert "artifacts/ethics/" in allowed
        # Ethics must not write into any role's branch worktree.
        assert not any(
            p.startswith("branches/") and not p.startswith("branches/ethics/.minionsos/")
            for p in allowed
        )


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


class TestReviewerWhitelistIsolation:
    def test_non_gru_main_roles_can_spawn_subagents(self) -> None:
        for role in ("noter", "coder", "experimenter", "writer", "reviewer", "ethics", "expert"):
            assert "Task" in resolve_whitelist(role, "main")

    def test_reviewer_has_no_write_tools(self) -> None:
        tools = resolve_whitelist("reviewer", "main")
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools

    def test_reviewer_subagent_can_write_reviews(self) -> None:
        """Reviewer subagent executes the writes the main session plans.

        Per the common SYSTEM.md Plan → Dispatch → Verify contract, review
        outputs under artifacts/reviews/ are produced by a subagent, not by
        Reviewer main. The subagent therefore needs Write/Edit; it remains
        EACN-invisible because no eacn3_* tools appear in this whitelist
        (asserted by TestSubagentEacnInvisibility).
        """
        tools = resolve_whitelist("reviewer", "subagent")
        assert "Write" in tools
        assert "Edit" in tools
        # Reviewer subagents must NOT get Bash — review is read + write, not
        # shell execution. They also must not appear on EACN.
        assert "Bash" not in tools

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

    _ALL_ROLES = ("gru", "noter", "coder", "experimenter", "writer", "reviewer", "ethics", "expert")

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
            leaks = [
                t for t in tools
                if t == "mos_project_bridge" or t.startswith("mos_project_")
            ]
            assert not leaks, (
                f"{role} subagent whitelist leaks cross-project coordination tools {leaks}; "
                "these are Gru-main coordination tools, not subagent execution tools."
            )
