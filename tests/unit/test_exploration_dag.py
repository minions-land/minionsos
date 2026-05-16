"""Unit tests for minions.tools.exploration_dag."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.tools import exploration_dag as dag


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up an isolated project directory for each test."""
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setattr(
        "minions.tools.exploration_dag.project_dir",
        lambda p: tmp_path / f"project_{p}",
    )
    exploration_dir = tmp_path / f"project_{port}" / "exploration"
    exploration_dir.mkdir(parents=True)
    return exploration_dir


class TestMosDagAppend:
    def test_append_single_node(self):
        result = dag.mos_dag_append(
            nodes=[{"type": "hypothesis", "text": "Test hypothesis"}]
        )
        assert result["created_node_ids"] == ["H-001"]
        assert result["created_edge_count"] == 0

    def test_append_auto_increments_ids(self):
        dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "First"}])
        result = dag.mos_dag_append(
            nodes=[{"type": "hypothesis", "text": "Second"}]
        )
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


class TestMosDagAnnotate:
    def test_annotate_status(self):
        dag.mos_dag_append(nodes=[{"type": "hypothesis", "text": "H1"}])
        result = dag.mos_dag_annotate(node_id="H-001", support_status="verified")
        assert result["changes"]["support_status"]["new"] == "verified"
        q = dag.mos_dag_query(node_type="hypothesis")
        assert q["nodes"][0]["support_status"] == "verified"

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
