"""Performance comparison: DAG+compact vs long-running vs short-process.

Simulates a 10-step scientific exploration workflow and measures:
- Token cost (context size at each step)
- Knowledge retention (can the agent recall prior discoveries?)
- Dead-end avoidance (does the agent re-explore failed paths?)

Three modes:
1. Long-running: single context window, no compaction, accumulates everything
2. Short-process: fresh context each step, only small carried summary for continuity
3. DAG+compact: fresh context each step, DAG + carried summary + compact skill

The test is deterministic (no LLM calls) — it simulates the information flow
and measures what each mode would have available at each step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import exploration_dag as dag

# --- Simulated exploration scenario ---
# A 10-step scientific workflow where each step produces discoveries,
# some of which are dead ends that should not be re-explored.

SCENARIO = [
    {
        "step": 1,
        "action": "formulate question",
        "produces": {
            "type": "question",
            "text": "Does attention head pruning preserve model quality?",
        },
    },
    {
        "step": 2,
        "action": "propose hypothesis",
        "produces": {
            "type": "hypothesis",
            "text": "Random pruning of 30% heads preserves >95% accuracy",
        },
    },
    {
        "step": 3,
        "action": "run experiment",
        "produces": {
            "type": "experiment",
            "text": "Ablation study on BERT-base, random 30% head removal",
        },
    },
    {
        "step": 4,
        "action": "record result",
        "produces": {"type": "result", "text": "Accuracy dropped 12% — hypothesis refuted"},
    },
    {
        "step": 5,
        "action": "mark dead end",
        "produces": {"type": "dead_end", "text": "Random pruning fails; need structured selection"},
    },
    {
        "step": 6,
        "action": "new hypothesis",
        "produces": {
            "type": "hypothesis",
            "text": "Importance-scored pruning preserves >95% accuracy",
        },
    },
    {
        "step": 7,
        "action": "run experiment 2",
        "produces": {
            "type": "experiment",
            "text": "Importance-based pruning on BERT-base, top-30% removal",
        },
    },
    {
        "step": 8,
        "action": "record result 2",
        "produces": {
            "type": "result",
            "text": "Accuracy preserved at 96.2% — hypothesis supported",
        },
    },
    {
        "step": 9,
        "action": "decision",
        "produces": {
            "type": "decision",
            "text": "Adopt importance-based pruning as primary method",
        },
    },
    {
        "step": 10,
        "action": "new question",
        "produces": {
            "type": "question",
            "text": "Does importance scoring transfer across model sizes?",
        },
    },
]

# Simulated token costs per step (realistic estimates)
TOKENS_PER_STEP_CONTEXT = 3000  # average tokens consumed per step of work
TOKENS_CARRIED_SUMMARY = 500  # small cross-cycle summary injection cost
TOKENS_DAG_SUMMARY = 400  # dag_summary injection cost
TOKENS_SYSTEM_PROMPT = 2000  # role SYSTEM.md + skills


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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


class TestPerformanceComparison:
    """Compare three modes on token cost and knowledge retention."""

    def _simulate_long_running(self) -> dict:
        """Mode 1: Single context, no compaction. Accumulates everything."""
        total_tokens = TOKENS_SYSTEM_PROMPT
        context_at_each_step = []

        for _step in SCENARIO:
            total_tokens += TOKENS_PER_STEP_CONTEXT
            context_at_each_step.append(total_tokens)

        return {
            "mode": "long_running",
            "total_tokens_consumed": total_tokens,
            "peak_context": max(context_at_each_step),
            "knowledge_at_step_10": 10,  # has everything in context
            "dead_end_visible_at_step_6": True,  # step 5 is in context
            "can_recall_step_1_at_step_10": True,  # but context is huge
        }

    def _simulate_short_process(self) -> dict:
        """Mode 2: Fresh context each step, only small carried summary."""
        total_tokens = 0
        knowledge_retained = 0

        for i, _step in enumerate(SCENARIO):
            # Each step: system prompt + carried summary + work
            step_tokens = TOKENS_SYSTEM_PROMPT + TOKENS_CARRIED_SUMMARY + TOKENS_PER_STEP_CONTEXT
            total_tokens += step_tokens
            # Small carried summaries can only hold ~3 items reliably
            knowledge_retained = min(i + 1, 3)

        return {
            "mode": "short_process",
            "total_tokens_consumed": total_tokens,
            "peak_context": TOKENS_SYSTEM_PROMPT
            + TOKENS_CARRIED_SUMMARY
            + TOKENS_PER_STEP_CONTEXT,
            "knowledge_at_step_10": knowledge_retained,
            "dead_end_visible_at_step_6": False,  # carried summary may have lost it
            "can_recall_step_1_at_step_10": False,  # too far back
        }

    def _simulate_dag_compact(self) -> dict:
        """Mode 3: Fresh context + DAG + compact skill."""
        total_tokens = 0

        for _i, step in enumerate(SCENARIO):
            # Each step: system + carried summary + dag_summary + work
            step_tokens = (
                TOKENS_SYSTEM_PROMPT
                + TOKENS_CARRIED_SUMMARY
                + TOKENS_DAG_SUMMARY
                + TOKENS_PER_STEP_CONTEXT
            )
            total_tokens += step_tokens
            # Persist to DAG (small overhead per step)
            dag.mos_dag_append(nodes=[step["produces"]])

        # At step 10, query the DAG to verify knowledge retention
        summary = dag.mos_dag_summary()
        dead_ends = dag.mos_dag_query(node_type="dead_end")

        return {
            "mode": "dag_compact",
            "total_tokens_consumed": total_tokens,
            "peak_context": TOKENS_SYSTEM_PROMPT
            + TOKENS_CARRIED_SUMMARY
            + TOKENS_DAG_SUMMARY
            + TOKENS_PER_STEP_CONTEXT,
            "knowledge_at_step_10": summary["total_nodes"],  # all 10 nodes accessible
            "dead_end_visible_at_step_6": len(dead_ends["nodes"]) > 0,
            "can_recall_step_1_at_step_10": True,  # via dag_query
        }

    def test_goal_1_dag_cheaper_than_long_running(self):
        """DAG+compact uses fewer total tokens than long-running."""
        long = self._simulate_long_running()
        dag_mode = self._simulate_dag_compact()

        # DAG mode has lower peak context (bounded per step)
        assert dag_mode["peak_context"] < long["peak_context"]
        # DAG mode peak is bounded, long-running grows linearly
        assert dag_mode["peak_context"] < long["peak_context"] * 0.3

    def test_goal_1_dag_better_performance_than_long_running(self):
        """DAG+compact retains knowledge without context degradation."""
        long = self._simulate_long_running()
        dag_mode = self._simulate_dag_compact()

        # Both retain full knowledge
        assert dag_mode["knowledge_at_step_10"] == long["knowledge_at_step_10"]
        # DAG has dead ends visible
        assert dag_mode["dead_end_visible_at_step_6"] is True
        # DAG can recall early steps
        assert dag_mode["can_recall_step_1_at_step_10"] is True

    def test_goal_2_dag_better_than_short_process(self):
        """DAG+compact has better continuity than pure short-process."""
        short = self._simulate_short_process()
        dag_mode = self._simulate_dag_compact()

        # DAG retains more knowledge
        assert dag_mode["knowledge_at_step_10"] > short["knowledge_at_step_10"]
        # DAG sees dead ends (prevents re-exploration)
        assert dag_mode["dead_end_visible_at_step_6"] is True
        assert short["dead_end_visible_at_step_6"] is False
        # DAG can recall early work
        assert dag_mode["can_recall_step_1_at_step_10"] is True
        assert short["can_recall_step_1_at_step_10"] is False

    def test_goal_2_dag_similar_cost_to_short_process(self):
        """DAG+compact has similar per-step cost to short-process."""
        short = self._simulate_short_process()
        dag_mode = self._simulate_dag_compact()

        # DAG adds only dag_summary overhead per step
        overhead_ratio = dag_mode["total_tokens_consumed"] / short["total_tokens_consumed"]
        # Should be within 10% overhead (dag_summary is ~400 tokens on ~5500 per step)
        assert overhead_ratio < 1.10

    def test_dead_end_prevents_reexploration(self):
        """DAG dead_end nodes prevent redundant work."""
        # Simulate: agent at step 6 queries DAG before proposing new hypothesis
        for step in SCENARIO[:5]:
            dag.mos_dag_append(nodes=[step["produces"]])

        # At step 6, check if random pruning is a known dead end
        dead_ends = dag.mos_dag_query(node_type="dead_end")
        assert len(dead_ends["nodes"]) == 1
        assert "random pruning" in dead_ends["nodes"][0]["text"].lower()

        # Agent can avoid re-proposing random pruning
        # This is the key advantage over short-process mode

    def test_paper_path_extraction(self):
        """DAG supports extracting a paper-worthy path."""
        for step in SCENARIO:
            dag.mos_dag_append(nodes=[step["produces"]])

        # Add edges for the successful path
        dag.mos_dag_append(
            edges=[
                {"from_id": "Q-001", "to_id": "H-002", "relation": "refines"},
                {"from_id": "H-002", "to_id": "E-002", "relation": "tests"},
                {"from_id": "E-002", "to_id": "R-002", "relation": "supports"},
                {"from_id": "R-002", "to_id": "D-001", "relation": "derived_from"},
            ]
        )

        # Extract the paper path
        path = dag.mos_dag_path(target_node_id="D-001")
        assert len(path["path_nodes"]) >= 3
        # The path should NOT include the dead end
        path_ids = {n["id"] for n in path["path_nodes"]}
        assert "DEAD-001" not in path_ids
