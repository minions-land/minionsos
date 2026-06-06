"""Tests for mos_draft_unmarked_audit — per-role Draft evidence-tag coverage signal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.config import resolve_server_authz, resolve_whitelist
from minions.tools import draft


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    # Mock in minions.paths since draft_helpers imports from there
    import minions.paths
    monkeypatch.setattr(
        minions.paths,
        "project_shared_subdir",
        lambda p, subdir: tmp_path / f"project_{p}" / "branches" / "main" / subdir,
    )
    monkeypatch.setattr(
        minions.paths,
        "project_shared_draft_json",
        lambda p: tmp_path / f"project_{p}" / "branches" / "main" / "draft" / "draft.json",
    )

    draft_dir = tmp_path / f"project_{port}" / "branches" / "main" / "draft"
    draft_dir.mkdir(parents=True)
    return draft_dir


def _write_draft(draft_dir: Path, nodes: list[dict[str, object]]) -> None:
    payload = {"project_port": 9999, "root_question": "q", "nodes": nodes, "edges": []}
    (draft_dir / "draft.json").write_text(json.dumps(payload), encoding="utf-8")


class TestRoleUnmarkedRatioHelper:
    def test_ratio_counts_only_empty_tags(self):
        nodes = [
            {"id": "R1", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
            {"id": "R2", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
            {"id": "R3", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
            {"id": "R4", "type": "result", "author_role": "expert-a", "evidence_tag": "exp/E1.md"},
            {
                "id": "R5",
                "type": "decision",
                "author_role": "expert-a",
                "evidence_tag": "exp/E2.md",
            },
        ]
        # 3 of 5 claim nodes are unmarked -> 0.6
        assert draft._role_unmarked_ratio(nodes, "expert-a") == 0.6

    def test_min_nodes_guard_returns_none(self):
        nodes = [
            {"id": "R1", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
            {"id": "R2", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
        ]
        assert draft._role_unmarked_ratio(nodes, "expert-a") is None

    def test_non_claim_types_excluded(self):
        # plan / question / context are not claim-bearing; they must not move the ratio.
        nodes = [
            {"id": "R1", "type": "result", "author_role": "expert-a", "evidence_tag": "exp/E1.md"},
            {"id": "R2", "type": "result", "author_role": "expert-a", "evidence_tag": "exp/E2.md"},
            {"id": "R3", "type": "result", "author_role": "expert-a", "evidence_tag": "exp/E3.md"},
            {"id": "P1", "type": "plan", "author_role": "expert-a", "evidence_tag": ""},
            {"id": "Q1", "type": "question", "author_role": "expert-a", "evidence_tag": ""},
        ]
        # only the 3 result nodes count, all marked -> 0.0 (plans/questions ignored)
        assert draft._role_unmarked_ratio(nodes, "expert-a") == 0.0

    def test_whitespace_tag_treated_as_empty(self):
        nodes = [
            {"id": "R1", "type": "result", "author_role": "x", "evidence_tag": "   "},
            {"id": "R2", "type": "result", "author_role": "x", "evidence_tag": "\n"},
            {"id": "R3", "type": "result", "author_role": "x", "evidence_tag": "exp/E.md"},
        ]
        assert draft._role_unmarked_ratio(nodes, "x") == round(2 / 3, 3)


class TestUnmarkedAudit:
    def test_aggregate_flags_above_threshold(self, _isolated_project: Path):
        _write_draft(
            _isolated_project,
            [
                # expert-a: 3/5 unmarked -> 0.6, flagged
                {"id": "R1", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
                {"id": "R2", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
                {"id": "R3", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
                {"id": "R4", "type": "result", "author_role": "expert-a", "evidence_tag": "e"},
                {"id": "R5", "type": "decision", "author_role": "expert-a", "evidence_tag": "e"},
                # ethics: 4 claim nodes all tagged -> 0.0, not flagged
                {"id": "E1", "type": "result", "author_role": "ethics", "evidence_tag": "a"},
                {"id": "E2", "type": "result", "author_role": "ethics", "evidence_tag": "b"},
                {"id": "E3", "type": "decision", "author_role": "ethics", "evidence_tag": "c"},
                {"id": "E4", "type": "insight", "author_role": "ethics", "evidence_tag": "d"},
                # expert: only 2 claim nodes -> None, never flagged
                {"id": "X1", "type": "result", "author_role": "expert", "evidence_tag": ""},
                {"id": "X2", "type": "result", "author_role": "expert", "evidence_tag": ""},
            ],
        )
        out = draft.mos_draft_unmarked_audit()
        assert out["threshold"] == 0.2
        assert out["per_role_unmarked"] == {"expert-a": 0.6, "ethics": 0.0, "expert": None}
        assert out["flagged_roles"] == ["expert-a"]

    def test_threshold_param_changes_flags(self, _isolated_project: Path):
        _write_draft(
            _isolated_project,
            [
                {"id": "R1", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
                {"id": "R2", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
                {"id": "R3", "type": "result", "author_role": "expert-a", "evidence_tag": ""},
                {"id": "R4", "type": "result", "author_role": "expert-a", "evidence_tag": "e"},
                {"id": "R5", "type": "decision", "author_role": "expert-a", "evidence_tag": "e"},
            ],
        )
        # ratio 0.6, threshold 0.7 -> not flagged
        assert draft.mos_draft_unmarked_audit(threshold=0.7)["flagged_roles"] == []

    def test_empty_draft(self, _isolated_project: Path):
        _write_draft(_isolated_project, [])
        out = draft.mos_draft_unmarked_audit()
        assert out["per_role_unmarked"] == {}
        assert out["flagged_roles"] == []


class TestAuthzBoundary:
    def test_ethics_and_gru_allowed(self):
        for role in ("ethics", "gru"):
            assert "mos_draft_unmarked_audit" in resolve_server_authz(role, "main")

    def test_peer_roles_denied(self):
        # Peer Experts must not reach the audit tool server-side.
        for role in ("expert", "expert-a"):
            authz = resolve_server_authz(role, "main")
            # Peer Experts have no explicit audit grant in their server authz list.
            assert "mos_draft_unmarked_audit" not in authz

    def test_present_in_cli_whitelist_for_ethics(self):
        # The unified CLI whitelist grants draft tools via the ``mos_draft_*``
        # wildcard, so the new tool is CLI-visible without an explicit entry.
        from fnmatch import fnmatchcase

        wl = resolve_whitelist("ethics", "main")
        assert any(fnmatchcase("mos_draft_unmarked_audit", p) for p in wl)
