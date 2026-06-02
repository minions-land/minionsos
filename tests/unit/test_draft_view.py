"""mos_draft_view subsumes the 4 retired Draft read tools (regression guard).

The role-facing Draft read surface was collapsed to one tool, mos_draft_view,
and hot.md was removed. This pins that the unified view answers every question
the old summary / query / relevant / topic_index answered, on a realistic
multi-role Draft — so cold-start orientation never silently regresses.

A measured, runnable version lives at docs/Reconstruction/verify_draft_view.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import draft


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    port = 9911
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setattr(
        draft,
        "project_shared_subdir",
        lambda p, s: tmp_path / f"project_{p}" / "branches" / "shared" / s,
    )
    monkeypatch.setattr(
        draft,
        "project_shared_draft_json",
        lambda p: tmp_path / f"project_{p}" / "branches" / "shared" / "draft" / "draft.json",
    )
    (tmp_path / f"project_{port}" / "branches" / "shared" / "draft").mkdir(parents=True)
    return port


def _seed():
    draft.mos_draft_append(
        nodes=[
            {
                "id": "H-001",
                "type": "hypothesis",
                "text": "Residual connections enable deep nets",
                "support_status": "verified",
                "author_role": "expert-ml",
                "confidence": 0.9,
                "created_at": "2026-06-01T10:00:00",
            },
            {
                "id": "E-001",
                "type": "experiment",
                "text": "Train ResNet-50 vs plain-34 on ImageNet",
                "support_status": "verified",
                "author_role": "expert-ml",
                "confidence": 0.85,
                "created_at": "2026-06-01T11:00:00",
            },
            {
                "id": "R-001",
                "type": "result",
                "text": "ResNet-50 hit 76.1%, plain-34 diverged",
                "support_status": "verified",
                "author_role": "expert-ml",
                "confidence": 0.95,
                "created_at": "2026-06-01T12:00:00",
            },
            {
                "id": "DEAD-001",
                "type": "dead_end",
                "text": "Plain-34 without residuals diverged",
                "support_status": "verified",
                "author_role": "ethics",
                "confidence": 1.0,
                "created_at": "2026-06-01T12:30:00",
            },
            {
                "id": "H-002",
                "type": "hypothesis",
                "text": "Batch size barely affects accuracy",
                "support_status": "unverified",
                "author_role": "expert-ml",
                "confidence": 0.4,
                "created_at": "2026-06-01T14:00:00",
            },
            {
                "id": "Q-001",
                "type": "question",
                "text": "Sweep learning rate next?",
                "support_status": "unverified",
                "author_role": "expert-ml",
                "confidence": 0.5,
                "created_at": "2026-06-01T15:00:00",
                "metadata": {"pending_plan": True},
            },
        ],
        edges=[
            {"from_id": "E-001", "to_id": "H-001", "relation": "tests"},
            {"from_id": "R-001", "to_id": "E-001", "relation": "derived_from"},
            {"from_id": "DEAD-001", "to_id": "H-001", "relation": "supports"},
        ],
    )


def test_view_orients_like_summary():
    _seed()
    v = draft.mos_draft_view()
    assert v["totals"]["nodes"] == 6
    assert v["pending_plans_total"] == 1 and v["pending_plans"][0]["id"] == "Q-001"
    assert v["nodes"][0]["id"] == "Q-001"  # newest-first
    assert v["nodes_by_type"]["hypothesis"] == 2


def test_view_filters_like_query():
    _seed()
    assert all(
        n["author_role"] == "expert-ml" for n in draft.mos_draft_view(by_role="expert-ml")["nodes"]
    )
    assert all(
        n["support_status"] == "verified"
        for n in draft.mos_draft_view(by_status="verified")["nodes"]
    )
    assert [n["id"] for n in draft.mos_draft_view(by_type="dead_end")["nodes"]] == ["DEAD-001"]


def test_view_neighbourhood_like_related_to():
    _seed()
    nbr = {n["id"] for n in draft.mos_draft_view(related_to="H-001")["nodes"]}
    assert {"H-001", "E-001", "DEAD-001"} <= nbr


def test_view_relevance_like_relevant():
    _seed()
    top = [
        n["id"]
        for n in draft.mos_draft_view(query="residual ResNet deep network", sort="relevance")[
            "nodes"
        ]
    ]
    assert "H-001" in top and "R-001" in top
    assert "H-002" not in top[:2]  # unrelated ranks lower, not a dump


def test_view_cold_start_needs_no_hot_md():
    """A single no-arg call reconstructs orientation — the role needs no hot.md."""
    _seed()
    cold = draft.mos_draft_view()
    assert cold["pending_plans_total"] == 1
    assert cold["totals"]["nodes"] == 6
    assert len(cold["nodes"]) > 0
