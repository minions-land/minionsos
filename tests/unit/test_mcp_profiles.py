"""Tests for advertised MCP tool profiles."""

from __future__ import annotations

import os
from unittest.mock import patch

from minions.tools import mcp_server
from minions.tools.eacn3_mcp_proxy import (
    allowed_tool_names_for_profile as allowed_eacn3_tools_for_profile,
)
from minions.tools.eacn3_mcp_proxy import filter_tools
from minions.tools.mcp_server import allowed_tool_names_for_profile


def test_codex_gru_profile_exposes_only_gru_minions_tools() -> None:
    tools = allowed_tool_names_for_profile(profile="codex", role="gru")

    assert "project_create" in tools
    assert "project_kill" in tools
    assert "spawn_role" in tools
    assert "gru_inbox_poll" in tools
    assert "project_eacn_send_message" in tools
    assert "exp_run" not in tools
    assert "search_arxiv" not in tools
    assert len(tools) < 20


def test_codex_writer_profile_keeps_paper_tools_not_project_tools() -> None:
    tools = allowed_tool_names_for_profile(profile="codex", role="writer")

    assert "search_arxiv" in tools
    assert "read_arxiv_paper" in tools
    assert "project_create" not in tools
    assert "spawn_role" not in tools


def test_full_profile_keeps_all_minions_tools() -> None:
    tools = allowed_tool_names_for_profile(profile="full", role="coder")

    assert "project_create" in tools
    assert "exp_run" in tools
    assert "search_arxiv" in tools


def test_eacn3_codex_core_profile_filters_large_tools() -> None:
    tools = allowed_eacn3_tools_for_profile(profile="codex-core")

    assert tools is not None
    assert "eacn3_next" in tools
    assert "eacn3_create_task" in tools
    assert "eacn3_cluster_status" not in tools
    assert "eacn3_deposit" not in tools


def test_eacn3_proxy_filters_tool_descriptors() -> None:
    filtered = filter_tools(
        [
            {"name": "eacn3_next", "description": "core"},
            {"name": "eacn3_cluster_status", "description": "diagnostic"},
        ],
        {"eacn3_next"},
    )

    assert filtered == [{"name": "eacn3_next", "description": "core"}]


def test_eacn3_unknown_profile_fails_closed() -> None:
    with patch.dict(os.environ, {"EACN3_MCP_PROFILE": "typo"}, clear=False):
        assert allowed_eacn3_tools_for_profile() == set()


def test_gru_start_monitor_detects_launcher_sidecar(tmp_path, monkeypatch) -> None:
    (tmp_path / "gru-monitor.pid").write_text("12345", encoding="utf-8")
    (tmp_path / "gru-monitor.host").write_text("codex", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(mcp_server.os, "kill", lambda pid, sig: None)

    with patch.dict(
        os.environ,
        {"MINIONS_ROLE_NAME": "gru", "MINIONS_AGENT_HOST": "codex"},
        clear=False,
    ):
        result = mcp_server.gru_start_monitor()

    assert result["started"] is False
    assert result["already_running"] is True
    assert result["external"] is True
    assert result["pid"] == 12345
    assert result["host"] == "codex"
    assert result["host_mismatch"] is False
