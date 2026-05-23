"""Unit tests for benchmark harness (v15-δ)."""

from __future__ import annotations

import json

import pytest

from minions.tools.benchmark import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    benchmark_aggregate,
    benchmark_save_run,
)


def test_benchmark_task_dataclass():
    """BenchmarkTask should hold task data."""
    task = BenchmarkTask(
        task_id="hle-0001",
        question="What is 2+2?",
        expected=4,
        metadata={"difficulty": "easy"},
    )
    assert task.task_id == "hle-0001"
    assert task.expected == 4
    assert task.metadata["difficulty"] == "easy"


def test_benchmark_aggregate_all_correct():
    """All correct results should yield 100% accuracy."""
    results = [
        BenchmarkResult(
            task_id="t1",
            port=8001,
            score=1.0,
            verdict="correct",
            details={},
            project_real_name="bench-t1",
        ),
        BenchmarkResult(
            task_id="t2",
            port=8002,
            score=1.0,
            verdict="correct",
            details={},
            project_real_name="bench-t2",
        ),
    ]
    agg = benchmark_aggregate(results)
    assert agg["total_tasks"] == 2
    assert agg["completed"] == 2
    assert agg["correct"] == 2
    assert agg["incorrect"] == 0
    assert agg["failed"] == 0
    assert agg["accuracy"] == 1.0
    assert agg["completion_rate"] == 1.0


def test_benchmark_aggregate_mixed():
    """Mixed results should compute correct rates."""
    results = [
        BenchmarkResult(
            task_id="t1",
            port=8001,
            score=1.0,
            verdict="correct",
            details={},
            project_real_name="bench-t1",
        ),
        BenchmarkResult(
            task_id="t2",
            port=8002,
            score=0.0,
            verdict="incorrect",
            details={},
            project_real_name="bench-t2",
        ),
        BenchmarkResult(
            task_id="t3",
            port=8003,
            score=None,
            verdict=None,
            details={},
            project_real_name="bench-t3",
            error="timeout",
        ),
    ]
    agg = benchmark_aggregate(results)
    assert agg["total_tasks"] == 3
    assert agg["completed"] == 2
    assert agg["correct"] == 1
    assert agg["incorrect"] == 1
    assert agg["failed"] == 1
    assert agg["accuracy"] == pytest.approx(1 / 3)
    assert agg["completion_rate"] == pytest.approx(2 / 3)


def test_benchmark_aggregate_empty():
    """Empty results should not crash."""
    agg = benchmark_aggregate([])
    assert agg["total_tasks"] == 0
    assert agg["accuracy"] == 0.0


def test_benchmark_run_model():
    """BenchmarkRun should validate."""
    run = BenchmarkRun(
        run_id="20260523-120000",
        profile="hle-answer",
        started_at="2026-05-23T12:00:00+00:00",
    )
    assert run.run_id == "20260523-120000"
    assert run.profile == "hle-answer"
    assert run.tasks == []
    assert run.results == []


def test_benchmark_save_run(tmp_path):
    """benchmark_save_run should serialize run to JSON."""
    run = BenchmarkRun(
        run_id="test-001",
        profile="hle-answer",
        started_at="2026-05-23T12:00:00+00:00",
        completed_at="2026-05-23T12:30:00+00:00",
        tasks=[{"task_id": "t1", "question": "Q1", "expected": 42}],
        results=[{"task_id": "t1", "port": 8001, "score": 1.0}],
        aggregate={"accuracy": 1.0, "total_tasks": 1},
    )

    path = benchmark_save_run(run, output_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "test-001"
    assert data["aggregate"]["accuracy"] == 1.0


def test_benchmark_run_from_jsonl_missing_file(tmp_path):
    """Missing JSONL should raise ProjectError."""
    from minions.errors import ProjectError
    from minions.tools.benchmark import benchmark_run_from_jsonl

    nonexistent = tmp_path / "nonexistent.jsonl"

    with pytest.raises(ProjectError, match="not found"):
        benchmark_run_from_jsonl(nonexistent, auto_evaluate=False)


def test_benchmark_run_from_jsonl_parses_tasks(tmp_path, monkeypatch):
    """JSONL parser should handle valid lines and skip malformed ones."""
    jsonl = tmp_path / "tasks.jsonl"
    jsonl.write_text(
        '{"task_id": "t1", "question": "Q1?", "expected": 42}\n'
        '{"task_id": "t2", "question": "Q2?", "expected": "hello"}\n'
        "# this is a comment\n"
        "\n"
        "malformed json line {{}\n",
        encoding="utf-8",
    )

    # Mock benchmark_create_projects so we don't actually start backends
    created_tasks: list[BenchmarkTask] = []

    def mock_create(tasks, profile, name_prefix=None, **kwargs):
        created_tasks.extend(tasks)
        return []

    from minions.tools import benchmark

    monkeypatch.setattr(benchmark, "benchmark_create_projects", mock_create)

    run = benchmark.benchmark_run_from_jsonl(jsonl, profile="hle-answer", auto_evaluate=False)

    # Should parse 2 valid tasks (skip comment + empty + malformed)
    assert len(created_tasks) == 2
    assert created_tasks[0].task_id == "t1"
    assert created_tasks[0].expected == 42
    assert created_tasks[1].task_id == "t2"
    assert run.profile == "hle-answer"
    assert len(run.tasks) == 2
