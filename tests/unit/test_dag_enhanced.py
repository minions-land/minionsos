"""Tests for new DAG features: communities, god_nodes, edge strength, token budget."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import exploration_dag as dag


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setattr(
        "minions.tools.exploration_dag.project_dir",
        lambda p: tmp_path / f"project_{p}",
    )
    exploration_dir = tmp_path / f"project_{port}" / "exploration"
    exploration_dir.mkdir(parents=True)
    return exploration_dir


class TestEdgeStrength:
    def test_default_strength_is_one(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
            ],
            edges=[{"from_id": "H-001", "to_id": "E-001", "relation": "tests"}],
        )
        result = dag.mos_dag_query(related_to="H-001")
        edge = result["edges"][0]
        assert edge.get("strength", 1.0) == 1.0

    def test_custom_strength(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
            ],
            edges=[{"from_id": "H-001", "to_id": "E-001", "relation": "tests", "strength": 0.7}],
        )
        result = dag.mos_dag_query(related_to="H-001")
        edge = result["edges"][0]
        assert edge["strength"] == 0.7

    def test_path_prefers_strong_edges(self):
        """Dijkstra should prefer the path through high-strength edges."""
        dag.mos_dag_append(
            nodes=[
                {"type": "question", "text": "Root"},
                {"type": "hypothesis", "text": "H1"},
                {"type": "hypothesis", "text": "H2"},
                {"type": "result", "text": "R1"},
            ],
            edges=[
                # Direct path: Root -> H1 -> R1 (weak edges)
                {"from_id": "Q-001", "to_id": "H-001", "relation": "refines", "strength": 0.3},
                {"from_id": "H-001", "to_id": "R-001", "relation": "supports", "strength": 0.3},
                # Indirect path: Root -> H2 -> R1 (strong edges)
                {"from_id": "Q-001", "to_id": "H-002", "relation": "refines", "strength": 0.9},
                {"from_id": "H-002", "to_id": "R-001", "relation": "supports", "strength": 0.9},
            ],
        )
        result = dag.mos_dag_path(target_node_id="R-001")
        path_ids = [n["id"] for n in result["path_nodes"]]
        # Should go through H-002 (strong) not H-001 (weak)
        assert "H-002" in path_ids
        assert "H-001" not in path_ids


class TestCommunities:
    def test_empty_dag(self):
        result = dag.mos_dag_communities()
        assert result["total_communities"] == 0
        assert result["communities"] == []

    def test_single_community(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
                {"type": "result", "text": "R1"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
                {"from_id": "E-001", "to_id": "R-001", "relation": "supports"},
            ],
        )
        result = dag.mos_dag_communities()
        # All connected nodes should be in one community
        assert result["total_communities"] == 1
        assert result["communities"][0]["size"] == 3

    def test_two_disconnected_communities(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
                {"type": "hypothesis", "text": "H2"},
                {"type": "experiment", "text": "E2"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
                {"from_id": "H-002", "to_id": "E-002", "relation": "tests"},
            ],
        )
        result = dag.mos_dag_communities()
        assert result["total_communities"] == 2

    def test_cross_community_edges(self):
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "H1"},
                {"type": "experiment", "text": "E1"},
                {"type": "hypothesis", "text": "H2"},
                {"type": "experiment", "text": "E2"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
                {"from_id": "H-002", "to_id": "E-002", "relation": "tests"},
                {"from_id": "H-001", "to_id": "H-002", "relation": "contradicts"},
            ],
        )
        result = dag.mos_dag_communities()
        # The contradicts edge crosses communities (if they stay separate)
        # or merges them (label propagation may merge)
        # Either way, the structure should be valid
        assert result["total_communities"] >= 1


class TestGodNodes:
    def test_empty_dag(self):
        result = dag.mos_dag_god_nodes()
        assert result["god_nodes"] == []

    def test_identifies_hub(self):
        # Create a star topology: H-001 connects to everything
        dag.mos_dag_append(
            nodes=[
                {"type": "hypothesis", "text": "Central hypothesis"},
                {"type": "experiment", "text": "E1"},
                {"type": "experiment", "text": "E2"},
                {"type": "result", "text": "R1"},
                {"type": "citation", "text": "C1"},
            ],
            edges=[
                {"from_id": "H-001", "to_id": "E-001", "relation": "tests"},
                {"from_id": "H-001", "to_id": "E-002", "relation": "tests"},
                {"from_id": "H-001", "to_id": "R-001", "relation": "supports"},
                {"from_id": "H-001", "to_id": "C-001", "relation": "cites"},
            ],
        )
        result = dag.mos_dag_god_nodes(top_n=3)
        assert len(result["god_nodes"]) >= 1
        # H-001 should be the top god node (highest degree + cross-type)
        assert result["god_nodes"][0]["id"] == "H-001"
        assert result["god_nodes"][0]["degree"] == 4

    def test_top_n_limits_output(self):
        dag.mos_dag_append(
            nodes=[{"type": "hypothesis", "text": f"H{i}"} for i in range(10)],
        )
        result = dag.mos_dag_god_nodes(top_n=3)
        assert len(result["god_nodes"]) <= 3


class TestTokenBudget:
    def test_query_respects_budget(self):
        # Create many nodes
        dag.mos_dag_append(
            nodes=[{"type": "hypothesis", "text": f"Hypothesis number {i}"} for i in range(100)],
        )
        # With a very small budget, should truncate
        result = dag.mos_dag_query(max_tokens=200)
        assert result.get("truncated") is True
        assert len(result["nodes"]) < 100

    def test_query_no_truncation_when_small(self):
        dag.mos_dag_append(
            nodes=[{"type": "hypothesis", "text": "H1"}],
        )
        result = dag.mos_dag_query(max_tokens=2000)
        assert result.get("truncated") is not True
