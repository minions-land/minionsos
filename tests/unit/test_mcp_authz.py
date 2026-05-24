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
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "coder"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_project_create")


def test_mcp_authz_allows_writer_paper_search_tool() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "writer"}, clear=False):
        _require_tool_allowed("mos_search_arxiv")


def test_mcp_authz_denies_coder_paper_search_tool() -> None:
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "coder"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_search_arxiv")


def test_mcp_authz_allows_coder_experiment_queue_tool() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": "coder"}, clear=False):
        _require_tool_allowed("mos_exp_queue_submit")
        _require_tool_allowed("mos_exp_gpu_pool_set")


def test_mcp_authz_denies_noter_experiment_queue_tool() -> None:
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "noter"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_exp_queue_submit")


def test_mcp_authz_allows_empty_role_for_interactive_or_tests() -> None:
    with patch.dict(os.environ, {"MINIONS_ROLE_NAME": ""}, clear=False):
        _require_tool_allowed("mos_project_create")


def test_mcp_authz_visual_tools_allowed_for_eacn_roles() -> None:
    for role in ("gru", "coder", "writer", "ethics", "expert"):
        with patch.dict(os.environ, {"MINIONS_ROLE_NAME": role}, clear=False):
            _require_tool_allowed("mos_visual_render")
            _require_tool_allowed("mos_visual_inspect")
            _require_tool_allowed("mos_visual_check")


def test_mcp_authz_visual_tools_denied_for_noter() -> None:
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "noter"}, clear=False),
        pytest.raises(PermissionError),
    ):
        _require_tool_allowed("mos_visual_render")


def test_mcp_authz_reel_tools_allowed_for_eacn_roles() -> None:
    """Reel read tools are allowed for all EACN-visible roles (server-side
    authz at the role-private boundary is enforced in reel.py itself, not here)."""
    for role in ("gru", "coder", "writer", "ethics", "expert"):
        with patch.dict(os.environ, {"MINIONS_ROLE_NAME": role}, clear=False):
            _require_tool_allowed("mos_reel_get")
            _require_tool_allowed("mos_reel_window")


def test_mcp_authz_reel_tools_denied_for_noter() -> None:
    """Noter does not capture reels — it observes via events/* and Draft."""
    with (
        patch.dict(os.environ, {"MINIONS_ROLE_NAME": "noter"}, clear=False),
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
        _require_tool_allowed("mos_draft_summary")

    # CLI whitelist must also be non-empty so --allowed-tools can be built.
    whitelist = resolve_whitelist(role_name, "main")
    assert whitelist, f"empty whitelist for role={role_name!r}"
    assert "mos_issue_report" in whitelist


def test_non_expert_role_unchanged() -> None:
    """Sanity: the suffix-form fix must not pull non-expert roles into
    the expert authz bucket."""
    from minions.config import is_expert_role, normalise_role_name

    for role in ["coder", "noter", "writer", "ethics", "gru"]:
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
