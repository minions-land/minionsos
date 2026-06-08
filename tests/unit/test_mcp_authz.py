"""Tests for MinionsOS MCP server-side role authorization."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from minions.tools.mcp_server import _require_tool_allowed


def test_mcp_authz_allows_gru_project_tool() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "gru"}, clear=False):
        _require_tool_allowed("mos_project_create")


def test_mcp_authz_denies_role_project_tool() -> None:
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "ethics"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_project_create")


def test_mcp_authz_allows_expert_paper_search_tool() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "expert"}, clear=False):
        _require_tool_allowed("mos_search_arxiv")


def test_mcp_authz_allows_ethics_paper_search_tool() -> None:
    """Ethics (merged curator+auditor) now holds paper-search for citation
    authenticity audits."""
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "ethics"}, clear=False):
        _require_tool_allowed("mos_search_arxiv")


def test_mcp_authz_allows_expert_experiment_queue_tool() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "expert"}, clear=False):
        _require_tool_allowed("mos_exp_queue_submit")
        _require_tool_allowed("mos_exp_gpu_pool_set")


def test_mcp_authz_denies_ethics_experiment_queue_tool() -> None:
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "ethics"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_exp_queue_submit")


def test_mcp_authz_allows_empty_role_for_interactive_or_tests() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": ""}, clear=False):
        _require_tool_allowed("mos_project_create")


def test_mcp_authz_visual_tools_allowed_for_eacn_roles() -> None:
    for role in ("gru", "ethics", "expert"):
        with patch.dict(os.environ, {"MINIONS_ROLE_NAME": role}, clear=False):
            _require_tool_allowed("mos_visual_render")
            _require_tool_allowed("mos_visual_inspect")
            _require_tool_allowed("mos_visual_check")


def test_mcp_authz_visual_tools_denied_for_unknown_role() -> None:
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "observer"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_visual_render")


def test_mcp_authz_reel_tools_allowed_for_eacn_roles() -> None:
    """Reel read tools are allowed for all EACN-visible roles (server-side
    authz at the role-private boundary is enforced in reel.py itself, not here)."""
    for role in ("gru", "ethics", "expert"):
        with patch.dict(os.environ, {"MINIONS_ROLE_NAME": role}, clear=False):
            _require_tool_allowed("mos_reel_get")
            _require_tool_allowed("mos_reel_window")


def test_mcp_authz_reel_tools_denied_for_observatory() -> None:
    """Observatory processes do not capture reels."""
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "observatory"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_reel_get")


# ---------------------------------------------------------------------------
# GitHub Issue #1 — suffix-form expert role names must collapse to "expert"
# in BOTH the CLI whitelist and server-side authz. Without this, _require_tool_allowed
# falls through to the empty-list branch and the entire tool surface is denied,
# trapping the role's event loop.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_name",
    [
        "expert",  # bare authz key
        "expert-foo",  # prefix form (default register_expert shape)
        "foo-expert",  # suffix form — was broken in v15.6 and earlier
        "theory-normalization-expert",  # the exact name that triggered Issue #1
    ],
)
def test_expert_authz_works_for_all_three_name_shapes(role_name: str) -> None:
    """All three accepted Expert name shapes must resolve to a non-empty
    authz list AND a non-empty CLI whitelist.

    The pre-v15.7 bug: only `expert` and `expert-<slug>` collapsed to the
    `expert` authz key; `<slug>-expert` fell through to the empty list,
    silently denying every tool including `mos_issue_report` itself.
    """
    from minions.config import is_expert_role, normalise_role_name, resolve_whitelist

    # Normaliser smoke check.
    assert is_expert_role(role_name)
    assert normalise_role_name(role_name) == "expert"

    # Server-side authz: a universal tool like `mos_issue_report` must pass.
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": role_name}, clear=False):
        _require_tool_allowed("mos_issue_report")
        # Also event-loop tools — these are the ones that were silently denied.
        _require_tool_allowed("mos_await_events")
        _require_tool_allowed("mos_draft_view")

    # CLI whitelist must also be non-empty so --allowed-tools can be built.
    whitelist = resolve_whitelist(role_name, "main")
    assert whitelist, f"empty whitelist for role={role_name!r}"
    assert "mos_issue_report" in whitelist


def test_non_expert_role_unchanged() -> None:
    """Sanity: the suffix-form fix must not pull non-expert roles into
    the expert authz bucket."""
    from minions.config import is_expert_role, normalise_role_name

    for role in ["observer", "ethics", "gru"]:
        assert not is_expert_role(role)
        assert normalise_role_name(role) == role


def test_register_expert_with_suffix_name_resolves_authz() -> None:
    """End-to-end: register_expert(name='theory-normalization-expert') must
    produce a role whose tool surface is non-empty in both layers.
    """
    from minions.config import resolve_server_authz, resolve_whitelist

    name = "theory-normalization-expert"
    assert resolve_whitelist(name, "main"), "CLI whitelist empty for suffix-form expert"
    assert resolve_server_authz(name, "main"), "Server authz empty for suffix-form expert"


# ---------------------------------------------------------------------------
# Gru EACN boundary — Gru observes + direct-messages, never posts/bids tasks.
# ---------------------------------------------------------------------------


GRU_EACN_FORBIDDEN = [
    "eacn3_create_task",
    "eacn3_submit_bid",
    "eacn3_submit_result",
    "eacn3_select_result",
    "eacn3_close_task",
    "eacn3_reject_task",
    "eacn3_create_subtask",
    "eacn3_update_deadline",
    "eacn3_update_discussions",
    "eacn3_team_setup",
    "eacn3_team_status",
    "eacn3_team_retry_ack",
    "eacn3_invite_agent",
    "eacn3_claim_agent",
    "eacn3_confirm_budget",
    "eacn3_deposit",
    "eacn3_get_balance",
]

GRU_EACN_ALLOWED_OUT = [
    "eacn3_send_message",
]

GRU_EACN_ALLOWED_READ = [
    "eacn3_get_messages",
    "eacn3_get_events",
    "eacn3_list_tasks",
    "eacn3_get_task",
    "eacn3_list_agents",
    "eacn3_get_agent",
    "eacn3_health",
]


@pytest.mark.parametrize("tool_name", GRU_EACN_ALLOWED_OUT + GRU_EACN_ALLOWED_READ)
def test_gru_eacn_observe_and_direct_message_allowed(tool_name: str) -> None:
    """Gru's narrowed EACN surface still covers observation + direct messaging."""
    from fnmatch import fnmatchcase

    from minions.config import resolve_server_authz

    patterns = resolve_server_authz("gru", "main")
    assert any(fnmatchcase(tool_name, p) for p in patterns), (
        f"Gru should be allowed to call {tool_name!r}; "
        "patterns were: " + ", ".join(patterns)
    )


@pytest.mark.parametrize("tool_name", GRU_EACN_FORBIDDEN)
def test_gru_eacn_task_post_forbidden(tool_name: str) -> None:
    """Gru is the to-human window + bridge; tasks/bids/results are Role-only.

    Coda-epilogue p37596 incident 2026-05-26: a Gru that mis-read its own
    boundary attempted ``eacn3_create_task`` to seed a discussion, was
    blocked, then escalated to a direct HTTP POST (which the user
    forbade). The boundary must reject the call at the MCP layer so Gru
    falls back to the correct surface (``eacn3_send_message``) instead
    of inventing a workaround.
    """
    from fnmatch import fnmatchcase

    from minions.config import resolve_server_authz

    patterns = resolve_server_authz("gru", "main")
    assert not any(fnmatchcase(tool_name, p) for p in patterns), (
        f"Gru must NOT be allowed to call {tool_name!r}; "
        "patterns were: " + ", ".join(patterns)
    )


def test_gru_eacn_no_wildcard_in_server_authz() -> None:
    """The bare ``eacn3_*`` wildcard must not appear in Gru's authz row.

    The wildcard is fine in the unified CLI whitelist (KV-cache parity
    across roles), but the server-side authz row is the real boundary.
    """
    from minions.config import resolve_server_authz

    patterns = resolve_server_authz("gru", "main")
    assert "eacn3_*" not in patterns, (
        "Gru server-authz still grants the bare eacn3_* wildcard; "
        "use the explicit _GRU_EACN_TOOLS allowlist instead."
    )
