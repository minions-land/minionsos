"""Unit tests for minions.tools.exploration_dag."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from minions.tools import exploration_dag as dag


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up an isolated project directory for each test."""
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setattr(
        dag,
        "project_shared_subdir",
        lambda p, subdir: tmp_path / f"project_{p}" / "branches" / "shared" / subdir,
    )
    monkeypatch.setattr(
        dag,
        "project_shared_dag_json",
        lambda p: tmp_path
        / f"project_{p}"
        / "branches"
        / "shared"
        / "exploration"
        / "dag.json",
    )
    exploration_dir = tmp_path / f"project_{port}" / "branches" / "shared" / "exploration"
    exploration_dir.mkdir(parents=True)
    return exploration_dir


def _write_legacy_dag(exploration_dir: Path, nodes: list[dict[str, object]]) -> None:
    payload = {
        "project_port": 9999,
        "root_question": "legacy graph",
        "nodes": nodes,
        "edges": [],
    }
    (exploration_dir / "dag.json").write_text(json.dumps(payload), encoding="utf-8")


class TestMosDagAppend:
    def test_append_single_node(self):
        result = dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "Test hypothesis"}])
        assert result["created_node_ids"] == ["H-001"]
        assert result["created_edge_count"] == 0

    def test_append_auto_increments_ids(self):
        dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "First"}])
        result = dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "Second"}])
        assert result["created_node_ids"] == ["H-002"]

    def test_append_multiple_types(self):
        result = dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H"},
                {"type": "experiment", "text": "E"},
                {"type": "dead_end", "text": "Dead"},
            ]
        )
        assert result["created_node_ids"] == ["H-001", "E-001", "DEAD-001"]

    def test_append_with_edges(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H"},
                {"type": "experiment", "text": "E"},
            ]
        )
        result = dag.mos_dag_append(
            edges=[{"from_id": "H-001", "to_id": "E-001", "relation": "tests"}]
        )
        assert result["created_edge_count"] == 1

    def test_append_custom_type_accepted(self):
        """Custom types are accepted (not rejected) — schema is suggestive."""
        result = dag.mos_dag_append(nodes=[{"type": "observation", "text": "X"}])
        assert result["created_node_ids"] == ["OBS-001"]

    def test_append_stores_provenance_and_confidence(self):
        dag.mos_dag_append(
            nodes=[
                {
                    "type": "hypothesis",
                    "text": "Derived from earlier evidence",
                    "provenance": "inferred",
                    "confidence": 0.42,
                }
            ]
        )
        node = dag.mos_dag_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "inferred"
        assert node["confidence"] == 0.42

    def test_append_defaults_provenance_and_confidence(self):
        dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "Defaulted"}])
        node = dag.mos_dag_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "extracted"
        assert node["confidence"] == 1.0

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_append_rejects_out_of_range_confidence(self, confidence: float):
        with pytest.raises(ValueError, match="Node confidence must be 0.0-1.0"):
            dag.mos_dag_append(
                nodes=[{"type": "hypothesis", "text": "Invalid", "confidence": confidence}]
            )

    def test_append_accepts_custom_provenance(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.INFO, logger=dag.logger.name):
            dag.mos_dag_append(
                nodes=[
                    {
                        "type": "hypothesis",
                        "text": "Field note",
                        "provenance": "field-note",
                    }
                ]
            )
        node = dag.mos_dag_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "field-note"
        assert "Custom provenance: field-note" in caplog.text

    def test_journal_written(self, _isolated_project: Path):
        dag.mos_dag_append(nodes=[{"type": "question", "text": "Why?"}])
        journal = _isolated_project / "journal.jsonl"
        assert journal.exists()
        entries = [json.loads(line) for line in journal.read_text().splitlines()]
        assert len(entries) == 1
        assert entries[0]["op"] == "add_node"
        assert entries[0]["node"]["id"] == "Q-001"


class TestMosDagQuery:
    def test_query_empty_dag(self):
        result = dag.mos_dag_query()
        assert result["nodes"] == []
        assert result["total_matched"] == 0

    def test_query_by_type(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
            ]
        )
        result = dag.mos_dag_query(node_type="hypothesis")
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "H-001"

    def test_query_by_status(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1", "support_status": "tentative"},
                {"type": "hypothesis", "text": "H2", "support_status": "verified"},
            ]
        )
        result = dag.mos_dag_query(support_status="verified")
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["text"] == "H2"

    def test_query_related_to(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
                {"type": "result", "text": "R1"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
            ],
        )
        result = dag.mos_dag_query(related_to="H-001")
        ids = {n["id"] for n in result["nodes"]}
        assert "H-001" in ids
        assert "E-001" in ids
        assert "R-001" not in ids

    def test_legacy_dag_without_provenance_confidence_still_works(
        self, _isolated_project: Path
    ):
        _write_legacy_dag(
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

        dag.mos_dag_append(
            nodes=[{"type": "result", "text": "New result", "author_role": "coder"}],
            edges=[{"from_id": "H-001", "to_id": "R-001", "relation": "supports"}],
        )
        dag.mos_dag_annotate(node_id="H-001", support_status="tentative")
        summary = dag.mos_dag_summary()
        query = dag.mos_dag_query(related_to="H-001")

        legacy_node = next(node for node in query["nodes"] if node["id"] == "H-001")
        assert "provenance" not in legacy_node
        assert "confidence" not in legacy_node
        assert summary["nodes_by_provenance"]["unknown"] == 1
        assert summary["nodes_by_provenance"]["extracted"] == 1
        assert len(query["nodes"]) == 2


class TestMosDagAnnotate:
    def test_annotate_status(self):
        dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "H1"}])
        result = dag.mos_dag_annotate(node_id="H-001", support_status="verified")
        assert result["changes"]["support_status"]["new"] == "verified"
        q = dag.mos_dag_query(node_type="hypothesis")
        assert q["nodes"][0]["support_status"] == "verified"

    def test_annotate_provenance_and_confidence(self, _isolated_project: Path):
        dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "H1"}])
        result = dag.mos_dag_annotate(
            node_id="H-001",
            provenance="speculative",
            confidence=0.25,
        )
        assert result["changes"]["provenance"]["new"] == "speculative"
        assert result["changes"]["confidence"]["new"] == 0.25

        node = dag.mos_dag_query(node_type="hypothesis")["nodes"][0]
        assert node["provenance"] == "speculative"
        assert node["confidence"] == 0.25

        journal = _isolated_project / "journal.jsonl"
        entries = [json.loads(line) for line in journal.read_text().splitlines()]
        assert [entry["field"] for entry in entries[1:]] == ["provenance", "confidence"]

    def test_annotate_nonexistent_raises(self):
        with pytest.raises(ValueError, match="Node not found"):
            dag.mos_dag_annotate(node_id="X-999", support_status="verified")


class TestMosDagPath:
    def test_path_simple_chain(self):
        dag.mos_dag_append(
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
        result = dag.mos_dag_path(target_node_id="E-001")
        assert len(result["path_nodes"]) == 3
        assert result["path_nodes"][0]["id"] == "Q-001"
        assert result["path_nodes"][-1]["id"] == "E-001"


class TestMosDagSummary:
    def test_summary_empty(self):
        result = dag.mos_dag_summary()
        assert result["total_nodes"] == 0

    def test_summary_with_data(self):
        dag.mos_dag_append(
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
        result = dag.mos_dag_summary()
        assert result["total_nodes"] == 4
        assert result["total_edges"] == 1
        assert result["nodes_by_type"]["hypothesis"] == 2
        assert result["dead_end_count"] == 1
        assert len(result["active_hypotheses"]) == 1
        assert result["active_hypotheses"][0]["id"] == "H-001"

    def test_summary_counts_provenance_by_role(self, _isolated_project: Path):
        _write_legacy_dag(
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
        dag.mos_dag_append(
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

        result = dag.mos_dag_summary()
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
