"""Tests for advertised MCP tool profiles."""

from __future__ import annotations

import os
from unittest.mock import patch

from minions.tools import mcp_server
from minions.tools.eacn3_mcp_proxy import (
    allowed_tool_names_for_profile as allowed_eacn3_tools_for_profile,
)
from minions.tools.eacn3_mcp_proxy import allowed_tool_surface, filter_tools
from minions.tools.mcp_server import allowed_tool_names_for_profile


def test_codex_gru_profile_exposes_only_gru_minions_tools() -> None:
    tools = allowed_tool_names_for_profile(profile="codex", role="gru")

    assert "project_create" in tools
    assert "project_kill" in tools
    assert "spawn_role" in tools
    assert "gru_inbox_poll" in tools
    assert "project_eacn_send_message" in tools
    assert "mos_await_events" in tools
    assert "mos_send_message" in tools
    assert "mos_create_task" in tools
    assert "exp_run" not in tools
    assert "search_arxiv" not in tools
    # Sanity ceiling: Gru keeps its lifecycle + project_eacn + mos_* + relay.
    # Bump when Gru legitimately gains another non-experiment/paper tool.
    assert len(tools) < 30


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


def test_eacn3_minions_role_profile_filters_by_active_role() -> None:
    """For a role wake, the proxy mirrors the role's eacn3_* whitelist.

    Internal roles no longer drain queues directly, so ``eacn3_await_events``
    and ``eacn3_send_message`` must be hidden from them; the role uses
    ``mos_*`` (provided by the minionsos MCP server) instead. Non-destructive
    reads and the non-drain writes the whitelist permits stay available.
    """
    child_tools = [
        {"name": name}
        for name in (
            "eacn3_await_events",
            "eacn3_next",
            "eacn3_get_events",
            "eacn3_send_message",
            "eacn3_create_task",
            "eacn3_get_task",
            "eacn3_get_messages",
            "eacn3_list_tasks",
            "eacn3_submit_bid",
            "eacn3_submit_result",
            "eacn3_cluster_status",
        )
    ]

    with patch.dict(
        os.environ,
        {
            "EACN3_MCP_PROFILE": "minions-role",
            "MINIONS_ROLE_NAME": "coder",
            "MINIONS_AGENT_TYPE": "main",
        },
        clear=False,
    ):
        exact, patterns = allowed_tool_surface()
        filtered = filter_tools(child_tools, exact, patterns)

    names = {tool["name"] for tool in filtered}
    assert "eacn3_await_events" not in names
    assert "eacn3_next" not in names
    assert "eacn3_get_events" not in names
    assert "eacn3_send_message" not in names
    assert "eacn3_create_task" not in names
    assert "eacn3_get_task" in names
    assert "eacn3_get_messages" in names
    assert "eacn3_list_tasks" in names
    assert "eacn3_submit_bid" in names
    assert "eacn3_submit_result" in names
    assert "eacn3_cluster_status" in names


def test_eacn3_minions_role_profile_gru_keeps_full_eacn3_surface() -> None:
    """Gru's whitelist is ``eacn3_*`` (wildcard). The proxy must honour it."""
    child_tools = [
        {"name": "eacn3_await_events"},
        {"name": "eacn3_send_message"},
        {"name": "eacn3_create_task"},
        {"name": "eacn3_cluster_status"},
    ]

    with patch.dict(
        os.environ,
        {
            "EACN3_MCP_PROFILE": "minions-role",
            "MINIONS_ROLE_NAME": "gru",
            "MINIONS_AGENT_TYPE": "main",
        },
        clear=False,
    ):
        exact, patterns = allowed_tool_surface()
        filtered = filter_tools(child_tools, exact, patterns)

    names = {tool["name"] for tool in filtered}
    assert names == {
        "eacn3_await_events",
        "eacn3_send_message",
        "eacn3_create_task",
        "eacn3_cluster_status",
    }


def test_eacn3_minions_role_profile_falls_back_to_full_without_role_env() -> None:
    """Running the proxy outside a role wake (dev interactive `codex`)."""
    child_tools = [
        {"name": "eacn3_await_events"},
        {"name": "eacn3_cluster_status"},
    ]

    with patch.dict(os.environ, {"EACN3_MCP_PROFILE": "minions-role"}, clear=False):
        os.environ.pop("MINIONS_ROLE_NAME", None)
        exact, patterns = allowed_tool_surface()
        filtered = filter_tools(child_tools, exact, patterns)

    assert filtered == child_tools


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
