"""Unit tests for the Python-side Coder experiment queue scheduler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minions.tools.experiment_scheduler import ExperimentScheduler, QueueUnit


class FakeExperimentBackend:
    def __init__(self) -> None:
        self.launched: list[dict[str, Any]] = []
        self.statuses: dict[str, dict[str, Any]] = {}
        self.killed: list[str] = []

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

    def exp_kill(self, _target_id: str, run_id: str) -> dict[str, Any]:
        self.killed.append(run_id)
        return {"killed": True}


def _scheduler(tmp_path: Path, backend: FakeExperimentBackend) -> ExperimentScheduler:
    return ExperimentScheduler(
        db_path=tmp_path / "scheduler.sqlite",
        target_ids=["local"],
        query_gpus_fn=backend.query_gpus,
        exp_run_fn=backend.exp_run,
        exp_status_fn=backend.exp_status,
        exp_kill_fn=backend.exp_kill,
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


def test_plan_dry_run_predicts_placements_without_writing(tmp_path: Path) -> None:
    """plan() should predict placement for each unit and not touch the queue."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)

    plan = sched.plan(
        [
            QueueUnit(cmd="python a.py", reserve_mb=12000),
            QueueUnit(cmd="python b.py", reserve_mb=12000),
            QueueUnit(cmd="python c.py", reserve_mb=12000),
        ]
    )

    # First two fit on the two GPUs in the fake fleet; third unit is blocked
    # because both GPUs already speculatively reserved 12 GB and only 8 GB
    # remain (fake fleet has 20 GB / GPU).
    assert plan["summary"] == {"fits": 2, "blocked": 1, "total": 3}
    assert plan["placements"][0]["status"] == "fits"
    assert plan["placements"][1]["status"] == "fits"
    assert plan["placements"][2]["status"] == "blocked"
    # Sanity: nothing was queued or launched.
    assert backend.launched == []
    assert sched.status()["summary"] == {}


def test_reconcile_emits_placement_summary_with_skew_warning(tmp_path: Path) -> None:
    """Placement summary should flag obvious pile-ups for the skill layer."""

    class _SkewedBackend(FakeExperimentBackend):
        # exp_run ignores caller's gpu_ids and always writes [0]; this lets the
        # test force every launch onto GPU 0 even though the scheduler chose
        # different cards. The skew detector compares launched gpu_ids, so we
        # also override the scheduler-side launched record to all be GPU 0.
        pass

    backend = _SkewedBackend()
    sched = _scheduler(tmp_path, backend)
    res = sched.submit(
        [
            QueueUnit(cmd="a", gpu_ids=[0], reserve_mb=4000),
            QueueUnit(cmd="b", gpu_ids=[0], reserve_mb=4000),
        ],
        batch_id="skew",
    )
    placement = res["reconcile"]["placement"]
    assert "skew_warning" in placement
    assert placement["skew_warning"]
    assert "local:[0]" in placement["skew_warning"]


def test_oom_escalates_reserve_mb_on_requeue(tmp_path: Path) -> None:
    """An OOM should bump reserve_mb on the unit so the retry needs more headroom."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)

    sched.submit(
        [QueueUnit(cmd="python big.py", reserve_mb=10000, max_retries=2)],
        batch_id="batch-esc",
    )
    backend.statuses["run-0"] = {
        "state": "exited",
        "exit_code": 137,  # SIGKILL — pure exit-code OOM signal, no log needle
        "log_tail": "",
    }
    reconciled = sched.reconcile("batch-esc")

    assert reconciled["failed"][0]["oom"] is True
    assert reconciled["failed"][0]["next_status"] == "pending"
    bumped = reconciled["failed"][0]["reserve_mb"]
    assert bumped is not None and bumped > 10000


def test_active_targets_prefers_ssh_when_present() -> None:
    """If any SSH target is configured, local targets are excluded from the fleet."""
    from minions.config import (
        ExperimentTargetsConfig,
        LocalTarget,
        SSHTarget,
    )

    cfg = ExperimentTargetsConfig(
        targets=[
            LocalTarget(id="local", type="local", workdir="/tmp/exp"),
            SSHTarget(id="rig", type="ssh", host="user@rig", key="/k", workdir="/data/exp"),
        ]
    )
    active = cfg.active_targets()
    assert [t.id for t in active] == ["rig"]

    local_only = ExperimentTargetsConfig(
        targets=[LocalTarget(id="local", type="local", workdir="/tmp/exp")]
    )
    assert [t.id for t in local_only.active_targets()] == ["local"]


def test_kill_minus_9_detected_and_requeued(tmp_path: Path) -> None:
    """exit_code=-9 (wrapper PID gone before .exit written) → OOM-style requeue.

    Real-host run with kill -9 -- -<pgid> showed scheduler hung forever in
    'running' because the .exit file never got written. exp_status now probes
    /proc/<pid> and returns -9 when the wrapper is dead — exit code -9 is in
    OOM_EXIT_CODES so the scheduler requeues with escalated reserve.
    """
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)
    sched.submit(
        [QueueUnit(cmd="sleep 600", reserve_mb=4096, max_retries=2)],
        batch_id="batch-killed",
    )
    backend.statuses["run-0"] = {
        "state": "exited",
        "exit_code": -9,  # sentinel for "wrapper killed before writing .exit"
        "log_tail": "",
    }
    rec = sched.reconcile("batch-killed")
    assert rec["failed"][0]["oom"] is True
    assert rec["failed"][0]["next_status"] == "pending"
    assert rec["failed"][0]["reserve_mb"] is not None
    assert rec["failed"][0]["reserve_mb"] > 4096
    # Scheduler should have launched the retry in the same reconcile pass.
    assert len(rec["launched"]) == 1
    assert rec["launched"][0]["unit_id"] == rec["failed"][0]["unit_id"]


def test_plan_spreads_small_units_across_idle_gpus(tmp_path: Path) -> None:
    """plan() should not pile small units onto the fattest GPU.

    Real-host run with 8xA100 saw 4 of 8 small units land on GPU 3 because
    the old tie-break was 'fattest free first' and a 4 GB reservation didn't
    knock GPU 3 out of first place. Spread-first means an idle GPU always
    beats a GPU that already has a (live or speculative) run on it.
    """

    class _MultiGpuBackend(FakeExperimentBackend):
        def query_gpus(self, _target_id: str):  # type: ignore[override]
            # 4 GPUs with the same free VRAM — the old algorithm would pile
            # everything onto GPU 0 because tie-break fell to gpu_id ascending.
            return [{"id": i, "total_mb": 80000, "free_mb": 80000, "used_mb": 0} for i in range(4)]

    backend = _MultiGpuBackend()
    sched = ExperimentScheduler(
        db_path=tmp_path / "spread.sqlite",
        target_ids=["local"],
        query_gpus_fn=backend.query_gpus,
        exp_run_fn=backend.exp_run,
        exp_status_fn=backend.exp_status,
    )
    plan = sched.plan([QueueUnit(cmd=f"echo {i}", reserve_mb=4096) for i in range(4)])
    chosen = [tuple(p["gpu_ids"]) for p in plan["placements"] if p["status"] == "fits"]
    assert plan["summary"] == {"fits": 4, "blocked": 0, "total": 4}
    assert len(set(chosen)) == 4, f"expected 4 distinct GPUs, got {chosen}"


def test_drain_lets_running_jobs_finish_but_blocks_new_placements(tmp_path: Path) -> None:
    """drain (default): in-flight runs are not touched, new units skip the drained card."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)

    # Fill GPU 0 and GPU 1 with a long-running job each.
    sched.submit(
        [QueueUnit(cmd=f"sleep 99 # seed-{i}", reserve_mb=12000) for i in range(2)],
        batch_id="pre-drain",
    )
    assert sched.status()["summary"] == {"running": 2}

    # Drain GPU 1 — the run on it must NOT be killed.
    res = sched.set_gpu_pool(target_id="local", allowed_gpu_ids=[0], evict=False)
    assert backend.killed == [], "drain mode must not kill any run"
    # No 'evicted' key in drain mode.
    assert "evicted" not in res
    # Submit a new unit. It must NOT land on GPU 1 (drained); it should
    # remain pending because GPU 0 is also busy.
    sched.submit(
        [QueueUnit(cmd="echo new", reserve_mb=12000)],
        batch_id="post-drain",
    )
    pending = [u for u in sched.status("post-drain")["units"] if u["status"] == "pending"]
    assert len(pending) == 1
    assert "no_capacity" in (pending[0]["last_error"] or "")


def test_evict_kills_running_jobs_and_requeues_units_without_burning_retries(
    tmp_path: Path,
) -> None:
    """evict=True: SIGTERM the run on the removed GPU, reset unit to pending, no retry burn."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)
    sched.submit(
        [QueueUnit(cmd=f"sleep 99 # seed-{i}", reserve_mb=8000, max_retries=1) for i in range(2)],
        batch_id="evict-batch",
    )
    # Both GPUs are running. Capture their attempts pre-evict.
    pre_attempts = {u["unit_id"]: u["attempts"] for u in sched.status("evict-batch")["units"]}
    assert pre_attempts and all(a == 1 for a in pre_attempts.values())

    # Evict GPU 1.
    res = sched.set_gpu_pool(
        target_id="local",
        allowed_gpu_ids=[0],
        evict=True,
        reconcile=False,  # check the eviction state before any reconcile relaunches
    )
    assert "evicted" in res
    evicted = res["evicted"]
    assert len(evicted) == 1
    assert evicted[0]["evicted_from_gpus"] == [1]
    assert backend.killed == [evicted[0]["run_id"]]

    units = {u["unit_id"]: u for u in sched.status("evict-batch")["units"]}
    evicted_unit = units[evicted[0]["unit_id"]]
    assert evicted_unit["status"] == "pending"
    # Eviction must NOT burn a retry attempt.
    assert evicted_unit["attempts"] == pre_attempts[evicted[0]["unit_id"]] - 1
    # The other GPU's run is still untouched.
    other_unit_id = next(uid for uid in pre_attempts if uid != evicted[0]["unit_id"])
    assert units[other_unit_id]["status"] == "running"

    # Reconcile now: the evicted unit must be requeued on GPU 0 (the only
    # remaining allowed card). GPU 1 is banned. The original GPU 0 run still
    # holds its reservation but the fake fleet has 20 GB / GPU and the units
    # only ask for 8 GB each, so a second 8 GB unit fits.
    rec = sched.reconcile("evict-batch")
    assert len(rec["launched"]) == 1
    assert rec["launched"][0]["gpu_ids"] == [0]
    assert rec["launched"][0]["unit_id"] == evicted[0]["unit_id"]
    assert sched.status("evict-batch")["summary"] == {"running": 2}

    # Free GPU 0 by simulating its job exiting; reconcile should mark
    # everything done.
    other_run_id = next(
        r["run_id"]
        for r in sched.status("evict-batch")["runs"]
        if r["state"] == "running" and r["unit_id"] != evicted[0]["unit_id"]
    )
    backend.statuses[other_run_id] = {"state": "exited", "exit_code": 0, "log_tail": ""}
    rec2 = sched.reconcile("evict-batch")
    assert len(rec2["completed"]) == 1
    assert sched.status("evict-batch")["summary"] == {"done": 1, "running": 1}


def test_evict_does_not_escalate_reserve_mb(tmp_path: Path) -> None:
    """Eviction is operator-driven, not OOM. reserve_mb must NOT increase."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)
    sched.submit(
        [QueueUnit(cmd="sleep 99", reserve_mb=12000, gpu_ids=[1])],
        batch_id="reserve-check",
    )
    sched.set_gpu_pool(target_id="local", allowed_gpu_ids=[0], evict=True, reconcile=False)
    # Unit is pinned to GPU 1 (now removed) so it stays pending after eviction.
    units_full = sched.status("reserve-check")["units"]
    assert all(u["status"] == "pending" for u in units_full)
    # The evicted run row must record the SIGTERM sentinel — NOT an OOM exit
    # code, so the OOM escalation path is provably untouched.
    runs = sched.status("reserve-check")["runs"]
    evicted_run = next(r for r in runs if r["state"] == "evicted")
    assert evicted_run["exit_code"] == -15


def test_zombie_reaper_transitions_dead_pid_to_done(tmp_path: Path) -> None:
    """GitHub Issue #18: a run row whose PID is dead must transition to exited.

    Builds a scheduler with NO injected callbacks (so the reaper engages),
    pre-populates a unit + a `running` run with a guaranteed-dead PID, and
    asserts that reconcile() reaps it.
    """
    sched = ExperimentScheduler(
        db_path=tmp_path / "scheduler.sqlite",
        target_ids=["local"],
    )
    # Seed unit + zombie run row directly, bypassing exp_run.
    log_path = tmp_path / "logs" / "run-dead.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch()
    exit_path = log_path.with_suffix(".exit")
    exit_path.write_text("0")  # Clean exit code 0 on disk.
    # Pick a PID essentially guaranteed not to exist on this host.
    dead_pid = 2**22 - 1
    with sched._tx() as conn:
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO batches(batch_id, status, created_at, updated_at) "
            "VALUES (?, 'pending', ?, ?)",
            ("b1", now, now),
        )
        conn.execute(
            "INSERT INTO units(unit_id, batch_id, cmd, priority, attempts, max_retries, "
            "target_id, gpu_ids_json, reserve_mb, min_free_mb, status, last_error, "
            "active_run_id, metadata_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, 1, 3, ?, '[]', 0, 0, 'running', NULL, ?, '{}', ?, ?)",
            ("u-dead", "b1", "echo hi", "local", "r-dead", now, now),
        )
        conn.execute(
            "INSERT INTO runs(run_id, unit_id, batch_id, target_id, gpu_ids_json, pid, "
            "log_path, state, started_at, updated_at) "
            "VALUES (?, ?, ?, ?, '[]', ?, ?, 'running', ?, ?)",
            ("r-dead", "u-dead", "b1", "local", dead_pid, str(log_path), now, now),
        )

    with sched._tx() as conn:
        reaped = sched._reap_zombie_runs(conn)
    reaped_ids = [r["run_id"] for r in reaped]
    assert "r-dead" in reaped_ids
    reap = next(r for r in reaped if r["run_id"] == "r-dead")
    assert reap["exit_code"] == 0
    assert reap["next_status"] == "done"

    # The unit moved to done and active_run_id cleared.
    summary = sched.status("b1")["summary"]
    assert summary == {"done": 1}


def test_zombie_reaper_records_minus_9_when_exit_file_missing(tmp_path: Path) -> None:
    sched = ExperimentScheduler(
        db_path=tmp_path / "scheduler.sqlite",
        target_ids=["local"],
    )
    log_path = tmp_path / "logs" / "run-killed.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch()
    # Intentionally NO .exit file — simulates kill -9 before exit-marker landed.
    dead_pid = 2**22 - 2
    with sched._tx() as conn:
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO batches(batch_id, status, created_at, updated_at) "
            "VALUES (?, 'pending', ?, ?)",
            ("b1", now, now),
        )
        conn.execute(
            "INSERT INTO units(unit_id, batch_id, cmd, priority, attempts, max_retries, "
            "target_id, gpu_ids_json, reserve_mb, min_free_mb, status, last_error, "
            "active_run_id, metadata_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, 1, 3, ?, '[]', 0, 0, 'running', NULL, ?, '{}', ?, ?)",
            ("u-killed", "b1", "echo hi", "local", "r-killed", now, now),
        )
        conn.execute(
            "INSERT INTO runs(run_id, unit_id, batch_id, target_id, gpu_ids_json, pid, "
            "log_path, state, started_at, updated_at) "
            "VALUES (?, ?, ?, ?, '[]', ?, ?, 'running', ?, ?)",
            ("r-killed", "u-killed", "b1", "local", dead_pid, str(log_path), now, now),
        )

    with sched._tx() as conn:
        reaped = sched._reap_zombie_runs(conn)
    reap = next(r for r in reaped if r["run_id"] == "r-killed")
    assert reap["exit_code"] == -9
    assert reap["next_status"] == "failed"
    summary = sched.status("b1")["summary"]
    assert summary == {"failed": 1}


def test_zombie_reaper_skipped_when_pid_alive(tmp_path: Path) -> None:
    """Live PIDs must NOT be reaped — guards against false-positive kills."""
    import os

    sched = ExperimentScheduler(
        db_path=tmp_path / "scheduler.sqlite",
        target_ids=["local"],
    )
    log_path = tmp_path / "logs" / "run-alive.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch()
    alive_pid = os.getpid()  # This test process is guaranteed alive.
    with sched._tx() as conn:
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO batches(batch_id, status, created_at, updated_at) "
            "VALUES (?, 'pending', ?, ?)",
            ("b1", now, now),
        )
        conn.execute(
            "INSERT INTO units(unit_id, batch_id, cmd, priority, attempts, max_retries, "
            "target_id, gpu_ids_json, reserve_mb, min_free_mb, status, last_error, "
            "active_run_id, metadata_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, 1, 3, ?, '[]', 0, 0, 'running', NULL, ?, '{}', ?, ?)",
            ("u-alive", "b1", "echo hi", "local", "r-alive", now, now),
        )
        conn.execute(
            "INSERT INTO runs(run_id, unit_id, batch_id, target_id, gpu_ids_json, pid, "
            "log_path, state, started_at, updated_at) "
            "VALUES (?, ?, ?, ?, '[]', ?, ?, 'running', ?, ?)",
            ("r-alive", "u-alive", "b1", "local", alive_pid, str(log_path), now, now),
        )

    with sched._tx() as conn:
        reaped = sched._reap_zombie_runs(conn)
    assert reaped == []


# ---------------------------------------------------------------------------
# Issue #25 — operator-mode visibility
# ---------------------------------------------------------------------------


def test_status_records_last_reconcile_at(tmp_path: Path) -> None:
    """Every reconcile() must persist a timestamp so operator-mode
    callers can see how stale the queue's last refresh was (Issue #25)."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)
    pre = sched.status()
    assert pre["last_reconcile_at"] is None  # never reconciled
    sched.submit(
        [QueueUnit(cmd="echo a", gpus_needed=1, min_free_mb=1000)],
        requester="coder",
    )
    post = sched.status()
    assert post["last_reconcile_at"] is not None


def test_gpu_idle_warning_fires_when_pending_no_capacity_with_idle_gpus(
    tmp_path: Path,
) -> None:
    """The motivating Issue #25 signature: queue says ``no_capacity`` but
    ``nvidia-smi`` reports 0 MiB used — the only way out without daemon
    mode used to be a manual reconcile."""
    backend = FakeExperimentBackend()
    sched = _scheduler(tmp_path, backend)
    # Force every pending unit into no_capacity by demanding more memory
    # than any GPU has, then directly stamp last_error='no_capacity: ...'
    # for one pending unit so the warning has something to grip on.
    sched.submit(
        [QueueUnit(cmd="echo a", gpus_needed=1, min_free_mb=99_999_999)],
        requester="coder",
        reconcile=False,
    )
    # The submit reconciles by default; with min_free_mb impossibly high,
    # _pick_candidate fails and last_error is set to no_capacity.
    sched.reconcile()
    pre = sched.status()
    pending = [u for u in pre["units"] if u["status"] == "pending"]
    assert pending, "expected at least one pending unit"
    assert (pending[0]["last_error"] or "").startswith("no_capacity")
    # Backend reports both GPUs idle (used_mb=0) — the warning must fire.
    assert pre["gpu_idle_warning"]
    assert "0 MiB used" in pre["gpu_idle_warning"]


def test_gpu_idle_warning_silent_when_gpus_busy(tmp_path: Path) -> None:
    """If GPUs are actually being used, no_capacity is a real verdict and
    the warning must NOT fire."""

    class BusyBackend(FakeExperimentBackend):
        def query_gpus(self, _target_id: str) -> list[dict[str, int]]:
            return [
                {"id": 0, "total_mb": 20000, "free_mb": 1000, "used_mb": 19000},
                {"id": 1, "total_mb": 20000, "free_mb": 1000, "used_mb": 19000},
            ]

    backend = BusyBackend()
    sched = _scheduler(tmp_path, backend)
    sched.submit(
        [QueueUnit(cmd="echo a", gpus_needed=1, min_free_mb=10_000)],
        requester="coder",
    )
    pre = sched.status()
    pending = [u for u in pre["units"] if u["status"] == "pending"]
    assert pending
    assert pre["gpu_idle_warning"] == ""
