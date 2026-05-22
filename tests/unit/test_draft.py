"""Unit tests for minions.tools.draft."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from minions.tools import draft


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up an isolated project directory for each test."""
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setattr(
        draft,
        "project_shared_subdir",
        lambda p, subdir: tmp_path / f"project_{p}" / "branches" / "shared" / subdir,
    )
    monkeypatch.setattr(
        draft,
        "project_shared_draft_json",
        lambda p: tmp_path / f"project_{p}" / "branches" / "shared" / "draft" / "draft.json",
    )
    draft_dir = tmp_path / f"project_{port}" / "branches" / "shared" / "draft"
    draft_dir.mkdir(parents=True)
    return draft_dir


def _write_legacy_draft(draft_dir: Path, nodes: list[dict[str, object]]) -> None:
    payload = {
        "project_port": 9999,
        "root_question": "legacy graph",
        "nodes": nodes,
        "edges": [],
    }
    (draft_dir / "draft.json").write_text(json.dumps(payload), encoding="utf-8")


class TestMosDraftAppend:
    def test_append_single_node(self):
        result = draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": "Test hypothesis"}])
        assert result["created_node_ids"] == ["H-001"]
        assert result["created_edge_count"] == 0

    def test_append_auto_increments_ids(self):
        draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": "First"}])
        result = draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": "Second"}])
        assert result["created_node_ids"] == ["H-002"]

    def test_append_multiple_types(self):
        result = draft.mos_draft_append(
            nodes=[
                {"type": "hypothesis", "text": "H"},
                {"type": "experiment", "text": "E"},
                {"type": "dead_end", "text": "Dead"},
            ]
        )
        assert result["created_node_ids"] == ["H-001", "E-001", "DEAD-001"]

    def test_append_with_edges(self):
        draft.mos_draft_append(
            nodes=[
                {"type": "hypothesis", "text": "H"},
                {"type": "experiment", "text": "E"},
            ]
        )
        result = draft.mos_draft_append(
            edges=[{"from_id": "H-001", "to_id": "E-001", "relation": "tests"}]
        )
        assert result["created_edge_count"] == 1

    def test_append_custom_type_accepted(self):
        """Custom types are accepted (not rejected) — schema is suggestive."""
        result = draft.mos_draft_append(nodes=[{"type": "observation", "text": "X"}])
        assert result["created_node_ids"] == ["OBS-001"]

    def test_append_stores_provenance_and_confidence(self):
        draft.mos_draft_append(
            nodes=[
                {
                    "type": "hypothesis",
                    "text": "Derived from earlier evidence",
                    "provenance": "inferred",
                    "confidence": 0.42,
                }
            ]
        )
        node = draft.mos_draft_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "inferred"
        assert node["confidence"] == 0.42

    def test_append_defaults_provenance_and_confidence(self):
        draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": "Defaulted"}])
        node = draft.mos_draft_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "extracted"
        assert node["confidence"] == 1.0

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_append_rejects_out_of_range_confidence(self, confidence: float):
        with pytest.raises(ValueError, match=r"Node confidence must be 0\.0-1\.0"):
            draft.mos_draft_append(
                nodes=[{"type": "hypothesis", "text": "Invalid", "confidence": confidence}]
            )

    def test_append_accepts_custom_provenance(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.INFO, logger=draft.logger.name):
            draft.mos_draft_append(
                nodes=[
                    {
                        "type": "hypothesis",
                        "text": "Field note",
                        "provenance": "field-note",
                    }
                ]
            )
        node = draft.mos_draft_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "field-note"
        assert "Custom provenance: field-note" in caplog.text

    def test_journal_written(self, _isolated_project: Path):
        draft.mos_draft_append(nodes=[{"type": "question", "text": "Why?"}])
        journal = _isolated_project / "journal.jsonl"
        assert journal.exists()
        entries = [json.loads(line) for line in journal.read_text().splitlines()]
        assert len(entries) == 1
        assert entries[0]["op"] == "add_node"
        assert entries[0]["node"]["id"] == "Q-001"


class TestMosDraftQuery:
    def test_query_empty_dag(self):
        result = draft.mos_draft_query()
        assert result["nodes"] == []
        assert result["total_matched"] == 0

    def test_query_by_type(self):
        draft.mos_draft_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
            ]
        )
        result = draft.mos_draft_query(node_type="hypothesis")
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "H-001"

    def test_query_by_status(self):
        draft.mos_draft_append(
            nodes=[
                {"type": "hypothesis", "text": "H1", "support_status": "tentative"},
                {"type": "hypothesis", "text": "H2", "support_status": "verified"},
            ]
        )
        result = draft.mos_draft_query(support_status="verified")
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["text"] == "H2"

    def test_query_related_to(self):
        draft.mos_draft_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
                {"type": "result", "text": "R1"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
            ],
        )
        result = draft.mos_draft_query(related_to="H-001")
        ids = {n["id"] for n in result["nodes"]}
        assert "H-001" in ids
        assert "E-001" in ids
        assert "R-001" not in ids

    def test_legacy_dag_without_provenance_confidence_still_works(self, _isolated_project: Path):
        _write_legacy_draft(
            _isolated_project,
            [
                {
                    "id": "H-001",
                    "type": "hypothesis",
                    "text": "Legacy hypothesis",
                    "support_status": "unverified",
                    "author_role": "expert-legacy",
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "evidence_tag": "",
                    "metadata": {},
                }
            ],
        )

        draft.mos_draft_append(
            nodes=[{"type": "result", "text": "New result", "author_role": "coder"}],
            edges=[{"from_id": "H-001", "to_id": "R-001", "relation": "supports"}],
        )
        draft.mos_draft_annotate(node_id="H-001", support_status="tentative")
        summary = draft.mos_draft_summary()
        query = draft.mos_draft_query(related_to="H-001")

        legacy_node = next(node for node in query["nodes"] if node["id"] == "H-001")
        assert "provenance" not in legacy_node
        assert "confidence" not in legacy_node
        assert summary["nodes_by_provenance"]["unknown"] == 1
        assert summary["nodes_by_provenance"]["extracted"] == 1
        assert len(query["nodes"]) == 2


class TestMosDraftAnnotate:
    def test_annotate_status(self):
        draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": "H1"}])
        result = draft.mos_draft_annotate(node_id="H-001", support_status="verified")
        assert result["changes"]["support_status"]["new"] == "verified"
        q = draft.mos_draft_query(node_type="hypothesis")
        assert q["nodes"][0]["support_status"] == "verified"

    def test_annotate_provenance_and_confidence(self, _isolated_project: Path):
        draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": "H1"}])
        result = draft.mos_draft_annotate(
            node_id="H-001",
            provenance="speculative",
            confidence=0.25,
        )
        assert result["changes"]["provenance"]["new"] == "speculative"
        assert result["changes"]["confidence"]["new"] == 0.25

        node = draft.mos_draft_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "speculative"
        assert node["confidence"] == 0.25

        journal = _isolated_project / "journal.jsonl"
        entries = [json.loads(line) for line in journal.read_text().splitlines()]
        assert [entry["field"] for entry in entries[1:]] == ["provenance", "confidence"]

    def test_annotate_nonexistent_raises(self):
        with pytest.raises(ValueError, match="Node not found"):
            draft.mos_draft_annotate(node_id="X-999", support_status="verified")


class TestMosDraftPath:
    def test_path_simple_chain(self):
        draft.mos_draft_append(
            nodes=[
                {"type": "question", "text": "Root Q"},
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
            ],
            edges=[
                {"from_id": "Q-001", "to_id": "H-001", "relation": "refines"},
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
            ],
        )
        result = draft.mos_draft_path(target_node_id="E-001")
        assert len(result["path_nodes"]) == 3
        assert result["path_nodes"][0]["id"] == "Q-001"
        assert result["path_nodes"][-1]["id"] == "E-001"


class TestMosDraftSummary:
    def test_summary_empty(self):
        result = draft.mos_draft_summary()
        assert result["total_nodes"] == 0

    def test_summary_with_data(self):
        draft.mos_draft_append(
            nodes=[
                {"type": "hypothesis", "text": "H1", "support_status": "tentative"},
                {"type": "hypothesis", "text": "H2", "support_status": "verified"},
                {"type": "dead_end", "text": "Failed approach"},
                {"type": "decision", "text": "Use method X"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "H-002", "relation": "refines"},
            ],
        )
        result = draft.mos_draft_summary()
        assert result["total_nodes"] == 4
        assert result["total_edges"] == 1
        assert result["nodes_by_type"]["hypothesis"] == 2
        assert result["dead_end_count"] == 1
        assert len(result["active_hypotheses"]) == 1
        assert result["active_hypotheses"][0]["id"] == "H-001"

    def test_summary_counts_provenance_by_role(self, _isolated_project: Path):
        _write_legacy_draft(
            _isolated_project,
            [
                {
                    "id": "H-001",
                    "type": "hypothesis",
                    "text": "Legacy hypothesis",
                    "support_status": "unverified",
                    "author_role": "expert-old",
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "evidence_tag": "",
                    "metadata": {},
                }
            ],
        )
        draft.mos_draft_append(
            nodes=[
                {
                    "type": "experiment",
                    "text": "Extracted artifact",
                    "author_role": "coder",
                },
                {
                    "type": "insight",
                    "text": "Working hypothesis",
                    "author_role": "expert-foo",
                    "provenance": "speculative",
                    "confidence": 0.3,
                },
                {
                    "type": "result",
                    "text": "Derived result",
                    "author_role": "expert-foo",
                    "provenance": "inferred",
                    "confidence": 0.6,
                },
            ]
        )

        result = draft.mos_draft_summary()
        assert result["nodes_by_provenance"] == {
            "unknown": 1,
            "extracted": 1,
            "speculative": 1,
            "inferred": 1,
        }
        assert result["nodes_by_provenance_role"]["expert-old"]["unknown"] == 1
        assert result["nodes_by_provenance_role"]["coder"]["extracted"] == 1
        assert result["nodes_by_provenance_role"]["expert-foo"] == {
            "speculative": 1,
            "inferred": 1,
        }


class TestLoadDraftRobustness:
    """Boundary cases for _load_draft — corrupt JSON should not crash the role."""

    def test_load_draft_corrupt_json_falls_back_to_stub(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """If draft.json is corrupt, _load_draft warns + returns empty stub
        rather than crashing every Role op. Added in v13.5 after pass-2 audit
        identified this latent gap."""
        port = 9999
        draft_path = draft._draft_path(port)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text("this is not { valid json", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = draft._load_draft(port)

        assert result == {
            "project_port": port,
            "root_question": "",
            "nodes": [],
            "edges": [],
        }
        assert any("corrupt" in rec.message for rec in caplog.records)

    def test_load_draft_missing_file_returns_stub(self, tmp_path: Path):
        """When draft.json doesn't exist yet, _load_draft returns the empty stub."""
        port = 9999
        result = draft._load_draft(port)
        assert result == {
            "project_port": port,
            "root_question": "",
            "nodes": [],
            "edges": [],
        }

    def test_load_draft_valid_json_preserved(self, tmp_path: Path):
        """Valid draft.json is loaded unchanged — sanity check."""
        port = 9999
        draft_path = draft._draft_path(port)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(
                {
                    "project_port": port,
                    "root_question": "Q",
                    "nodes": [{"id": "H-1", "type": "hypothesis"}],
                    "edges": [],
                }
            ),
            encoding="utf-8",
        )

        result = draft._load_draft(port)
        assert result["root_question"] == "Q"
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "H-1"
