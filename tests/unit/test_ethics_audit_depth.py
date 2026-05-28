from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETHICS_SYSTEM = ROOT / "minions" / "roles" / "ethics" / "SYSTEM.md"


def test_ethics_prompt_mentions_book_query_tool() -> None:
    assert "mos_book_query" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_hot_get_tool() -> None:
    assert "mos_book_hot_get" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_cluster_threshold() -> None:
    assert "≥3 distinct Book clusters" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_hub_page_escalation() -> None:
    assert "hub page" in ETHICS_SYSTEM.read_text(encoding="utf-8")


def test_ethics_prompt_mentions_audit_depth_section() -> None:
    assert "Audit depth by structural impact" in ETHICS_SYSTEM.read_text(encoding="utf-8")
