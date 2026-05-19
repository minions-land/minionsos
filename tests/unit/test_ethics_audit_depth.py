from __future__ import annotations

from pathlib import Path

from minions.config import resolve_whitelist

ROOT = Path(__file__).resolve().parents[2]
ETHICS_SYSTEM = ROOT / "minions" / "roles" / "ethics" / "SYSTEM.md"


def test_ethics_prompt_mentions_graph_query_tool() -> None:
    assert "mcp__graphify__query_graph" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_god_nodes_tool() -> None:
    assert "mcp__graphify__god_nodes" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_community_threshold() -> None:
    assert "≥3 communities" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_god_node_escalation() -> None:
    assert "god-node" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_audit_depth_section() -> None:
    assert "Audit depth by structural impact" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_main_whitelist_includes_graph_depth_tools() -> None:
    tools = set(resolve_whitelist("ethics", "main"))

    assert "mcp__graphify__query_graph" in tools
    assert "mcp__graphify__god_nodes" in tools
