"""Phase 3 tests: role classification, boundary enforcement, Reviewer isolation."""

from __future__ import annotations

from minions.config import (
    ROLE_CLASSIFICATION,
    ROLE_WRITE_BOUNDARIES,
    RoleType,
    resolve_whitelist,
)
from minions.lifecycle.role import FIXED_ROLES, _boundary_context, _build_system_prompt
from minions.paths import common_role_system_md


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

    def test_coder_boundary_allows_assigned_system_maintenance(self) -> None:
        ctx = _boundary_context("coder", 37596)
        assert "system-maintenance" in ctx
        assert "MinionsOS repository runtime code" in ctx
        assert "explicitly assigns" in ctx

    def test_unknown_role_returns_generic(self) -> None:
        ctx = _boundary_context("unknown-role", 37596)
        assert len(ctx) > 0


class TestCommonRolePrompt:
    def test_common_role_system_exists(self) -> None:
        path = common_role_system_md()
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "Common Role Contract" in text
        assert "Subagent handoff contract" in text

    def test_role_system_prompt_combines_common_and_role_specific(self) -> None:
        path = _build_system_prompt("coder")
        assert path is not None
        text = path.read_text(encoding="utf-8")
        assert "Common Role Contract" in text
        assert "Coder" in text
        assert "Subagents do not reliably inherit" in text

    def test_coder_system_prompt_mentions_assigned_system_maintenance(self) -> None:
        path = _build_system_prompt("coder")
        assert path is not None
        text = path.read_text(encoding="utf-8")
        assert "system-maintenance code changes" in text
        assert "explicitly assigns" in text
        assert "report it to Gru through EACN" in text


class TestReviewerWhitelistIsolation:
    def test_non_gru_main_roles_can_spawn_subagents(self) -> None:
        for role in ("noter", "coder", "experimenter", "writer", "reviewer", "ethics", "expert"):
            assert "Task" in resolve_whitelist(role, "main")

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


class TestSubagentEacnInvisibility:
    """Subagents must never touch EACN3 — not through MOS Agent Pool, not
    through native eacn3_* tools. Main roles dispatch, subagents execute,
    subagents report back to main, main owns every EACN-facing action. This
    invariant is what lets the main session stay short and token-cheap."""

    _ALL_ROLES = ("gru", "noter", "coder", "experimenter", "writer", "reviewer", "ethics", "expert")

    def test_no_subagent_has_mos_tools(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "subagent")
            mos_leaks = [t for t in tools if t.startswith("mos_")]
            assert not mos_leaks, (
                f"{role} subagent whitelist leaks MOS Agent Pool tools {mos_leaks}; "
                "subagents must be EACN-invisible."
            )

    def test_no_subagent_has_eacn3_tools(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "subagent")
            eacn_leaks = [t for t in tools if t.startswith("eacn3_") or t == "eacn3_*"]
            assert not eacn_leaks, (
                f"{role} subagent whitelist leaks raw EACN3 tools {eacn_leaks}; "
                "subagents must be EACN-invisible."
            )

    def test_no_subagent_has_project_eacn_tools(self) -> None:
        for role in self._ALL_ROLES:
            tools = resolve_whitelist(role, "subagent")
            leaks = [t for t in tools if t.startswith("project_eacn_") or t == "gru_relay"]
            assert not leaks, (
                f"{role} subagent whitelist leaks project-scoped EACN tools {leaks}; "
                "these are Gru-main coordination tools, not subagent execution tools."
            )
