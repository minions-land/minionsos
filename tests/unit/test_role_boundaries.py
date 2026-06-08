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

    def test_no_experimenter_role(self) -> None:
        """Expert owns experiment execution; there is no separate experimenter role."""
        assert "experimenter" not in ROLE_CLASSIFICATION

    def test_ethics_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["ethics"] == RoleType.eacn_visible

    def test_expert_is_eacn_visible(self) -> None:
        assert ROLE_CLASSIFICATION["expert"] == RoleType.eacn_visible

    def test_current_fixed_roles_are_classified(self) -> None:
        assert {"gru", "ethics", "expert"}.issubset(ROLE_CLASSIFICATION)
        assert set(FIXED_ROLES).issubset(ROLE_CLASSIFICATION)


class TestWriteBoundaries:
    """MinionsOS role write boundaries live under each role branch plus allowed
    ``branches/main/<subdir>/`` publish surfaces."""

    def test_expert_owns_its_branch(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["expert"]
        assert any(p.startswith("branches/<expert>/") for p in allowed)

    def test_ethics_restricted_to_ethics_branch_and_shared_surface(self) -> None:
        allowed = ROLE_WRITE_BOUNDARIES["ethics"]
        assert any(p.startswith("branches/ethics/") for p in allowed)
        assert any(p.startswith("branches/main/ethics/") for p in allowed)
        # Ethics must not write into any other role's branch worktree.
        assert not any(
            p.startswith("branches/")
            and not p.startswith("branches/ethics/")
            and not p.startswith("branches/main/")
            for p in allowed
        )

    def test_no_role_writes_review_artifacts(self) -> None:
        """branches/main/reviews/ is owned exclusively by mos_review_run."""
        for role, allowed in ROLE_WRITE_BOUNDARIES.items():
            assert not any(p.startswith("branches/main/reviews/") for p in allowed), (
                f"role {role!r} declares write access to branches/main/reviews/; "
                "that surface is owned by mos_review_run only."
            )


class TestBoundaryContext:
    def test_gru_boundary_mentions_human_side(self) -> None:
        ctx = _boundary_context("gru", 37596)
        assert "human-side" in ctx.lower() or "human_side" in ctx.lower()

    def test_ethics_boundary_mentions_evidence(self) -> None:
        ctx = _boundary_context("ethics", 37596)
        assert "evidence" in ctx.lower()

    def test_expert_boundary_allows_own_branch(self) -> None:
        ctx = _boundary_context("expert", 37596)
        # Expert's write boundary in MinionsOS is its role branch.
        assert "branches/<expert>/" in ctx

    def test_expert_boundary_allows_assigned_system_maintenance(self) -> None:
        ctx = _boundary_context("expert", 37596)
        assert "system-maintenance" in ctx
        assert "MinionsOS" in ctx
        assert "explicitly assigns" in ctx

    def test_unknown_role_returns_generic(self) -> None:
        ctx = _boundary_context("unknown-role", 37596)
        assert len(ctx) > 0


class TestEthicsWhitelist:
    def test_non_gru_main_roles_can_spawn_subagents(self) -> None:
        for role in ("ethics", "expert"):
            assert "Task" in resolve_whitelist(role, "main")

    def test_ethics_has_write_tools_but_not_bash(self) -> None:
        """Ethics (merged curator+auditor) has Write/Edit for its subagent workflow
        but not Bash — execution stays with Expert/Gru subagents."""
        from minions.config import resolve_server_authz

        authz = resolve_server_authz("ethics", "main")
        assert "Write" in authz
        assert "Edit" in authz
        assert "Bash" not in authz


class TestSubagentEacnInvisibility:
    """Subagents must never touch EACN3 through any surface. Main roles
    dispatch, subagents execute, subagents report back to main, main owns
    every EACN-facing action. This invariant is what lets the main session
    stay short and token-cheap."""

    _ALL_ROLES = ("gru", "ethics", "expert")

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


class TestIssueReportUniversallyAllowed:
    """`mos_issue_report` is the runtime escape hatch for "the scaffolding
    is broken / unclear / missing". It must be reachable from every Role
    and every subagent, otherwise reports get lost behind boundary errors
    at exactly the moments we most need them filed."""

    _ALL_ROLES = ("gru", "ethics", "expert")

    def test_main_roles_can_report(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "main")
            assert "mos_issue_report" in tools, (
                f"{role}/main missing mos_issue_report — Roles must always be "
                "able to file scaffolding issues."
            )

    def test_subagents_can_report(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "subagent")
            assert "mos_issue_report" in tools, (
                f"{role}/subagent missing mos_issue_report — subagents that "
                "hit broken scaffolding must be able to file too."
            )
