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
