"""Unit tests for the Python-side Experimenter queue scheduler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minions.tools.experiment_scheduler import ExperimentScheduler, QueueUnit


class FakeExperimentBackend:
    def __init__(self) -> None:
        self.launched: list[dict[str, Any]] = []
        self.statuses: dict[str, dict[str, Any]] = {}

    def query_gpus(self, _target_id: str) -> list[dict[str, int]]:
        return [
            {"id": 0, "total_mb": 20000, "free_mb": 20000, "used_mb": 0},
            {"id": 1, "total_mb": 20000, "free_mb": 20000, "used_mb": 0},
        ]

    def exp_run(self, target_id: str, cmd: str, gpu_ids: list[int] | None) -> dict[str, Any]:
        run_id = f"run-{len(self.launched)}"
        record = {
            "run_id": run_id,
            "target_id": target_id,
            "cmd": cmd,
            "gpu_ids": gpu_ids,
            "pid": 1000 + len(self.launched),
            "log_path": f"logs/{run_id}.log",
        }
        self.launched.append(record)
        self.statuses[run_id] = {"state": "running", "log_tail": ""}
        return record

    def exp_status(self, _target_id: str, run_id: str) -> dict[str, Any]:
        return self.statuses[run_id]


def _scheduler(tmp_path: Path, backend: FakeExperimentBackend) -> ExperimentScheduler:
    return ExperimentScheduler(
        db_path=tmp_path / "scheduler.sqlite",
        target_ids=["local"],
        query_gpus_fn=backend.query_gpus,
        exp_run_fn=backend.exp_run,
        exp_status_fn=backend.exp_status,
    )


def test_new_batches_merge_into_project_global_pending_pool(tmp_path: Path) -> None:
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)

    first = sched.submit(
        [
            QueueUnit(cmd="python train.py --seed 1", reserve_mb=12000),
            QueueUnit(cmd="python train.py --seed 2", reserve_mb=12000),
        ],
        batch_id="batch-a",
    )
    assert len(first["reconcile"]["launched"]) == 2
    assert backend.launched[0]["gpu_ids"] == [0]
    assert backend.launched[1]["gpu_ids"] == [1]

    second = sched.submit(
        [QueueUnit(cmd="python train.py --seed 3", reserve_mb=12000)],
        batch_id="batch-b",
    )
    assert second["reconcile"]["launched"] == []
    assert sched.status()["summary"] == {"pending": 1, "running": 2}

    backend.statuses["run-1"] = {"state": "exited", "exit_code": 0, "log_tail": "done"}
    reconciled = sched.reconcile()

    assert len(reconciled["completed"]) == 1
    assert len(reconciled["launched"]) == 1
    assert reconciled["launched"][0]["batch_id"] == "batch-b"
    assert reconciled["launched"][0]["gpu_ids"] == [1]
    assert sched.status()["summary"] == {"done": 1, "running": 2}


def test_gpu_pool_can_block_and_later_release_explicit_gpu_unit(tmp_path: Path) -> None:
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)

    sched.set_gpu_pool(target_id="local", allowed_gpu_ids=[0], reconcile=False)
    submitted = sched.submit(
        [QueueUnit(cmd="python train.py --device cuda:0", gpu_ids=[1], reserve_mb=12000)],
        batch_id="batch-gpu-1",
    )

    assert submitted["reconcile"]["launched"] == []
    assert sched.status("batch-gpu-1")["summary"] == {"pending": 1}

    released = sched.set_gpu_pool(target_id="local", allowed_gpu_ids="all", reconcile=True)

    assert len(released["reconcile"]["launched"]) == 1
    assert released["reconcile"]["launched"][0]["gpu_ids"] == [1]
    assert sched.status("batch-gpu-1")["summary"] == {"running": 1}


def test_oom_requeues_once_then_launches_on_any_available_gpu(tmp_path: Path) -> None:
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)

    sched.submit(
        [QueueUnit(cmd="python train.py --large", reserve_mb=12000, max_retries=1)],
        batch_id="batch-oom",
    )
    backend.statuses["run-0"] = {
        "state": "exited",
        "exit_code": 1,
        "log_tail": "RuntimeError: CUDA out of memory",
    }

    reconciled = sched.reconcile("batch-oom")

    assert len(reconciled["failed"]) == 1
    assert len(reconciled["launched"]) == 1
    assert reconciled["launched"][0]["run_id"] == "run-1"
    assert sched.status("batch-oom")["summary"] == {"running": 1}
