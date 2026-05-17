"""Tests for mos_reset_context — kill-session + watchdog respawn semantics.

Covers:
- reset writes journal + marker file
- reset attempts tmux kill-session (mocked)
- mos_dag_summary surfaces pending_plan nodes at the top
- summary pending_plans is sorted newest-first
- pending_plan flag survives DAG round-trip (append → load → summary)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from minions.tools import exploration_dag, reset


@pytest.fixture
def project_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    port = 39999
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    proj = tmp_path / f"project_{port}"
    (proj / "exploration").mkdir(parents=True)
    return port


def test_reset_writes_journal_entry(project_port: int, tmp_path: Path) -> None:
    """reset must append an op=reset row to journal.jsonl."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = reset.mos_reset_context(reason="task switch")

    assert result["status"] == "reset_acknowledged"
    journal = tmp_path / f"project_{project_port}" / "exploration" / "journal.jsonl"
    assert journal.exists()
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    reset_rows = [r for r in rows if r.get("op") == "reset"]
    assert len(reset_rows) == 1
    assert reset_rows[0]["role"] == "coder"
    assert reset_rows[0]["reason"] == "task switch"


def test_reset_writes_marker_file(project_port: int, tmp_path: Path) -> None:
    """Marker file lets the watchdog distinguish deliberate reset from crash."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        reset.mos_reset_context(reason="batch complete")

    marker = tmp_path / f"project_{project_port}" / "exploration" / ".reset_markers" / "coder"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["reason"] == "batch complete"


def test_reset_invokes_tmux_kill_session(project_port: int) -> None:
    """reset must call tmux kill-session with the canonical session name."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        reset.mos_reset_context(reason="x")

    assert mock_run.called
    argv = mock_run.call_args[0][0]
    assert argv[0] == "tmux"
    assert argv[1] == "kill-session"
    assert "-t" in argv
    assert f"mos-{project_port}-coder" in argv


def test_reset_returns_failure_when_kill_blows_up(project_port: int) -> None:
    """If tmux kill-session raises, reset reports the failure cleanly."""
    with patch("subprocess.run", side_effect=OSError("tmux missing")):
        result = reset.mos_reset_context(reason="y")
    assert result["status"] == "reset_failed"
    assert "tmux missing" in result["error"]


def test_summary_surfaces_pending_plans(project_port: int) -> None:
    """A node with metadata.pending_plan=true must appear in summary.pending_plans."""
    exploration_dag.mos_dag_append(
        nodes=[
            {
                "type": "experiment",
                "text": "Sweep LR for 12B variant",
                "support_status": "unverified",
                "metadata": {"pending_plan": True},
            }
        ]
    )
    summary = exploration_dag.mos_dag_summary()
    assert summary["pending_plans_total"] == 1
    assert len(summary["pending_plans"]) == 1
    assert summary["pending_plans"][0]["text"] == "Sweep LR for 12B variant"
    assert summary["pending_plans"][0]["type"] == "experiment"


def test_summary_pending_plans_newest_first(project_port: int) -> None:
    """Multiple pending plans must be ordered newest-first so post-reset agents
    see the most recent intent first."""
    exploration_dag.mos_dag_append(
        nodes=[
            {
                "type": "experiment",
                "text": "Older plan",
                "support_status": "unverified",
                "created_at": "2026-01-01T00:00:00+00:00",
                "metadata": {"pending_plan": True},
            }
        ]
    )
    exploration_dag.mos_dag_append(
        nodes=[
            {
                "type": "experiment",
                "text": "Newer plan",
                "support_status": "unverified",
                "created_at": "2026-05-17T00:00:00+00:00",
                "metadata": {"pending_plan": True},
            }
        ]
    )
    summary = exploration_dag.mos_dag_summary()
    assert summary["pending_plans"][0]["text"] == "Newer plan"
    assert summary["pending_plans"][1]["text"] == "Older plan"


def test_summary_excludes_executed_pending_plans(project_port: int) -> None:
    """Once a pending plan is annotated to verified/refuted, it stops being
    surfaced as pending — the agent already executed it."""
    res = exploration_dag.mos_dag_append(
        nodes=[
            {
                "type": "experiment",
                "text": "LR sweep done",
                "support_status": "unverified",
                "metadata": {"pending_plan": True},
            }
        ]
    )
    node_id = res["created_node_ids"][0]
    exploration_dag.mos_dag_annotate(
        node_id=node_id, support_status="verified", evidence_tag="commit:abc123"
    )
    summary = exploration_dag.mos_dag_summary()
    assert summary["pending_plans_total"] == 0


def test_summary_ignores_non_pending_unverified_nodes(project_port: int) -> None:
    """Ordinary unverified nodes (no pending_plan flag) must NOT pollute
    pending_plans — that field is reserved for explicit intent."""
    exploration_dag.mos_dag_append(
        nodes=[
            {
                "type": "hypothesis",
                "text": "Some random idea",
                "support_status": "unverified",
            }
        ]
    )
    summary = exploration_dag.mos_dag_summary()
    assert summary["pending_plans_total"] == 0


def test_pending_plan_flag_survives_dag_round_trip(project_port: int, tmp_path: Path) -> None:
    """metadata.pending_plan must persist to dag.json and reload intact."""
    exploration_dag.mos_dag_append(
        nodes=[
            {
                "type": "question",
                "text": "Is FlashAttn-3 stable on H200?",
                "metadata": {"pending_plan": True, "owner": "experimenter"},
            }
        ]
    )
    dag_path = tmp_path / f"project_{project_port}" / "exploration" / "dag.json"
    raw = json.loads(dag_path.read_text())
    node = raw["nodes"][0]
    assert node["metadata"]["pending_plan"] is True
    assert node["metadata"]["owner"] == "experimenter"
