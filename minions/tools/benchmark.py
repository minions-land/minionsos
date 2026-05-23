"""Benchmark harness: batch-create projects + aggregate results into a leaderboard.

This module provides Gru with the ability to run a benchmark suite (HLE, MMLU,
GPQA, SWE-bench, etc.) by:

1. Creating N projects in parallel, each with a profile-defined deliverable.
2. Seeding each project's ``input/`` directory with one question/task.
3. Aggregating per-project ``mos_evaluate`` results into a single leaderboard.

The harness is intentionally Gru-only (cross-project visibility is Gru's
exclusive surface, per the project's CLAUDE.md). Roles inside individual
benchmark projects do not see the leaderboard or sibling projects.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from minions.errors import ProjectError
from minions.lifecycle.project import project_create
from minions.paths import MINIONS_ROOT, project_dir, project_meta_json
from minions.state.store import StateStore
from minions.tools.evaluator import EvaluateArgs, mos_evaluate

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkTask:
    """One task in a benchmark suite.

    Attributes:
        task_id: Unique identifier (e.g., "hle-task-0042").
        question: The prompt/question text.
        expected: Expected answer (for grader strategies).
        metadata: Extra fields (difficulty, subject, etc.).
    """

    task_id: str
    question: str
    expected: object
    metadata: dict = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """One project's evaluation result in a benchmark run."""

    task_id: str
    port: int
    score: float | None
    verdict: str | None
    details: dict
    project_real_name: str
    error: str | None = None


class BenchmarkRun(BaseModel):
    """A single benchmark run aggregating per-task results."""

    run_id: str
    profile: str
    started_at: str
    completed_at: str | None = None
    tasks: list[dict] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)
    aggregate: dict = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def benchmark_create_projects(
    tasks: list[BenchmarkTask],
    profile: str = "hle-answer",
    name_prefix: str = "bench",
    venue: str | None = None,
    store: StateStore | None = None,
) -> list[tuple[BenchmarkTask, int]]:
    """Create one project per task, seeding each with the task's input.

    Returns list of (task, port) tuples for live projects. Failures are
    logged but don't abort the batch.
    """
    _store = store or StateStore()
    out: list[tuple[BenchmarkTask, int]] = []

    for task in tasks:
        real_name = f"{name_prefix}-{task.task_id}"
        try:
            entry = project_create(
                real_name=real_name,
                venue=venue,
                profile=profile,
                store=_store,
            )
            port = entry.port

            # Seed input/question.md and input/expected.json
            pdir = project_dir(port)
            input_dir = pdir / "input"
            input_dir.mkdir(parents=True, exist_ok=True)

            (input_dir / "question.md").write_text(
                f"# Task {task.task_id}\n\n{task.question}\n",
                encoding="utf-8",
            )
            (input_dir / "expected.json").write_text(
                json.dumps({"answer": task.expected, **task.metadata}, indent=2),
                encoding="utf-8",
            )

            logger.info(
                "benchmark_create_projects: task=%s port=%d profile=%s",
                task.task_id,
                port,
                profile,
            )
            out.append((task, port))
        except Exception as exc:
            logger.error(
                "benchmark_create_projects failed for task=%s: %s",
                task.task_id,
                exc,
            )

    return out


def benchmark_evaluate_all(
    task_ports: list[tuple[BenchmarkTask, int]],
) -> list[BenchmarkResult]:
    """Run mos_evaluate on every (task, port) pair and collect results."""
    results: list[BenchmarkResult] = []

    for task, port in task_ports:
        try:
            meta_path = project_meta_json(port)
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            real_name = meta.get("real_name", f"unknown-{port}")

            eval_result = mos_evaluate(EvaluateArgs(port=port))

            results.append(
                BenchmarkResult(
                    task_id=task.task_id,
                    port=port,
                    score=(
                        float(eval_result.get("score"))
                        if eval_result.get("score") is not None
                        else None
                    ),
                    verdict=str(eval_result.get("verdict") or ""),
                    details=eval_result.get("details", {}),
                    project_real_name=real_name,
                )
            )
        except Exception as exc:
            logger.error(
                "benchmark_evaluate_all failed for task=%s port=%d: %s",
                task.task_id,
                port,
                exc,
            )
            results.append(
                BenchmarkResult(
                    task_id=task.task_id,
                    port=port,
                    score=None,
                    verdict=None,
                    details={},
                    project_real_name=f"port-{port}",
                    error=str(exc),
                )
            )

    return results


def benchmark_aggregate(results: list[BenchmarkResult]) -> dict[str, object]:
    """Compute aggregate statistics from per-task results."""
    total = len(results)
    completed = sum(1 for r in results if r.error is None and r.score is not None)
    correct = sum(1 for r in results if r.score == 1.0)
    incorrect = sum(1 for r in results if r.score == 0.0)
    failed = sum(1 for r in results if r.error is not None)

    accuracy = correct / total if total > 0 else 0.0
    completion_rate = completed / total if total > 0 else 0.0

    # Score distribution
    scores = [r.score for r in results if r.score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "total_tasks": total,
        "completed": completed,
        "correct": correct,
        "incorrect": incorrect,
        "failed": failed,
        "accuracy": accuracy,
        "completion_rate": completion_rate,
        "average_score": avg_score,
    }


def benchmark_save_run(run: BenchmarkRun, output_dir: Path | None = None) -> Path:
    """Persist a benchmark run summary to disk."""
    if output_dir is None:
        output_dir = MINIONS_ROOT / "minions" / "state" / "benchmark_runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_path = output_dir / f"run-{run.run_id}.json"
    run_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Saved benchmark run to %s", run_path)
    return run_path


def benchmark_run_from_jsonl(
    jsonl_path: Path,
    profile: str = "hle-answer",
    name_prefix: str | None = None,
    auto_evaluate: bool = True,
) -> BenchmarkRun:
    """Run a benchmark from a JSONL file with one task per line.

    Each line should be a JSON object with at least:
    - task_id: str
    - question: str
    - expected: any (answer)

    Optional:
    - metadata: dict (extra task info)

    Args:
        jsonl_path: Path to JSONL file with tasks.
        profile: Mission profile name (default: hle-answer).
        name_prefix: Project name prefix (defaults to file stem).
        auto_evaluate: If True, run mos_evaluate after submissions appear.
                       If False, just create projects and return; caller
                       runs evaluation later.

    Returns:
        BenchmarkRun with results (empty if auto_evaluate=False).
    """
    if not jsonl_path.exists():
        raise ProjectError(f"Benchmark JSONL not found: {jsonl_path}")

    tasks: list[BenchmarkTask] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSONL line %d: %s", line_num, exc)
                continue
            tasks.append(
                BenchmarkTask(
                    task_id=str(data.get("task_id") or f"task-{line_num:04d}"),
                    question=str(data.get("question", "")),
                    expected=data.get("expected"),
                    metadata=data.get("metadata", {}) or {},
                )
            )

    run_id = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    prefix = name_prefix or jsonl_path.stem

    run = BenchmarkRun(
        run_id=run_id,
        profile=profile,
        started_at=_now_iso(),
        tasks=[asdict(t) for t in tasks],
    )

    logger.info("benchmark run %s: creating %d projects (profile=%s)", run_id, len(tasks), profile)
    task_ports = benchmark_create_projects(tasks, profile=profile, name_prefix=prefix)

    if auto_evaluate:
        logger.info("benchmark run %s: evaluating %d projects", run_id, len(task_ports))
        results = benchmark_evaluate_all(task_ports)
        run.results = [asdict(r) for r in results]
        run.aggregate = benchmark_aggregate(results)
        run.completed_at = _now_iso()
    else:
        # Record port assignments without evaluation
        run.results = [
            {"task_id": t.task_id, "port": p, "status": "pending_evaluation"} for t, p in task_ports
        ]

    return run


__all__ = [
    "BenchmarkResult",
    "BenchmarkRun",
    "BenchmarkTask",
    "benchmark_aggregate",
    "benchmark_create_projects",
    "benchmark_evaluate_all",
    "benchmark_run_from_jsonl",
    "benchmark_save_run",
]
