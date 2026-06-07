"""Unit tests for the fire-and-poll Expert experiment tool surface."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from minions.tools.experiment_ssh import (
    ExpListArgs,
    ExpQueueStatusArgs,
    ExpRunArgs,
    ExpStatusArgs,
    ExpWaitArgs,
    exp_list,
    exp_run,
    exp_status,
    exp_wait,
)


@pytest.fixture()
def local_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create a local experiment target rooted at *tmp_path* and make it discoverable."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    (workdir / "logs").mkdir()

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "experiment_targets.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "targets": [
                    {"id": "t-local", "type": "local", "workdir": str(workdir)},
                ]
            }
        )
    )

    # Redirect the config dir used by minions.config loaders.
    import minions.config as mc
    import minions.paths as mp

    monkeypatch.setattr(mp, "CONFIG_DIR", cfg_dir, raising=True)
    monkeypatch.setattr(mc, "CONFIG_DIR", cfg_dir, raising=True)
    return "t-local"


class TestFireAndPoll:
    def test_exp_run_returns_immediately_with_run_id(self, local_target: str) -> None:
        result = exp_run(ExpRunArgs(target_id=local_target, cmd="sleep 0.3 && echo done"))
        assert result["run_id"].startswith("exp-")
        assert result["target_id"] == local_target
        assert result["pid"] > 0
        log_path = Path(result["log_path"])
        # Log path must exist (nohup created it).
        for _ in range(20):
            if log_path.exists():
                break
            time.sleep(0.05)
        assert log_path.exists()

    def test_exp_status_transitions_running_to_exited(self, local_target: str) -> None:
        run = exp_run(ExpRunArgs(target_id=local_target, cmd="sleep 0.3 && echo done"))
        run_id = run["run_id"]

        # Immediately after launch it should be running.
        status_early = exp_status(ExpStatusArgs(target_id=local_target, run_id=run_id))
        assert status_early["state"] in {"running", "exited"}

        # Wait for it to finish.
        final = exp_wait(ExpWaitArgs(target_id=local_target, run_id=run_id, timeout=10))
        assert final["state"] == "exited"
        assert final["exit_code"] == 0
        assert "done" in final["log_tail"]

    def test_exp_list_returns_known_run(self, local_target: str) -> None:
        run = exp_run(ExpRunArgs(target_id=local_target, cmd="echo hi"))
        runs = exp_list(ExpListArgs(target_id=local_target))
        run_ids = [r["run_id"] for r in runs]
        assert run["run_id"] in run_ids
        listed = next(r for r in runs if r["run_id"] == run["run_id"])
        assert listed["target_id"] == local_target
        assert "gpu_ids" in listed
        assert listed["pid"] > 0
        assert listed["log_path"].endswith(f"{run['run_id']}.log")

    def test_gpu_ids_exports_cuda_visible_devices(self, local_target: str) -> None:
        """GitHub Issue #19: subprocess must actually receive CUDA_VISIBLE_DEVICES.

        The pre-fix code prefixed the cmd string with `CUDA_VISIBLE_DEVICES=1 `
        which was unreliable across the nohup/setsid chain. The fix uses
        `export` inside the launched subshell. We verify by having the
        command itself echo its CUDA_VISIBLE_DEVICES into the log.
        """
        run = exp_run(
            ExpRunArgs(
                target_id=local_target,
                cmd='sleep 0.1 && echo "CVD=${CUDA_VISIBLE_DEVICES}"',
                gpu_ids=[1],
            )
        )
        final = exp_wait(ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10))
        assert final["state"] == "exited"
        assert final["exit_code"] == 0
        log_path = Path(run["log_path"])
        for _ in range(20):
            if "CVD=" in log_path.read_text():
                break
            time.sleep(0.05)
        assert "CVD=1" in log_path.read_text()

    def test_gpu_ids_multiple_devices_exported(self, local_target: str) -> None:
        run = exp_run(
            ExpRunArgs(
                target_id=local_target,
                cmd='sleep 0.1 && echo "CVD=${CUDA_VISIBLE_DEVICES}"',
                gpu_ids=[2, 3],
            )
        )
        final = exp_wait(ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10))
        assert final["state"] == "exited"
        log_path = Path(run["log_path"])
        for _ in range(20):
            if "CVD=" in log_path.read_text():
                break
            time.sleep(0.05)
        assert "CVD=2,3" in log_path.read_text()

    def test_no_gpu_ids_leaves_cuda_visible_devices_unset(
        self, local_target: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
        run = exp_run(
            ExpRunArgs(
                target_id=local_target,
                cmd='sleep 0.1 && echo "CVD=${CUDA_VISIBLE_DEVICES:-unset}"',
            )
        )
        final = exp_wait(ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10))
        assert final["state"] == "exited"
        log_path = Path(run["log_path"])
        for _ in range(20):
            if "CVD=" in log_path.read_text():
                break
            time.sleep(0.05)
        assert "CVD=unset" in log_path.read_text()


class TestCmdTokenExpansion:
    """GitHub Issue #24: cmd string must expand {project_workspace}."""

    def test_unresolved_cmd_token_raises(
        self, local_target: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from minions.errors import ConfigError

        monkeypatch.delenv("MINIONS_PROJECT_PORT", raising=False)
        with pytest.raises(ConfigError, match="MINIONS_PROJECT_PORT"):
            exp_run(
                ExpRunArgs(
                    target_id=local_target,
                    cmd="echo {project_workspace}/training.log",
                )
            )

    def test_resolved_cmd_token_expands(
        self, local_target: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Use a port whose project workspace path has a deterministic shape.
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
        run = exp_run(
            ExpRunArgs(
                target_id=local_target,
                cmd='sleep 0.1 && echo "RESOLVED={project_workspace}"',
            )
        )
        final = exp_wait(ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10))
        assert final["state"] == "exited"
        log_path = Path(run["log_path"])
        for _ in range(20):
            if "RESOLVED=" in log_path.read_text():
                break
            time.sleep(0.05)
        log = log_path.read_text()
        # The token must be expanded (no literal {project_workspace}) AND
        # the expansion must include the project_37596 path component.
        assert "{project_workspace}" not in log
        assert "project_37596" in log


# ---------------------------------------------------------------------------
# Issue #25 — operator-mode auto-reconcile in exp_queue_status
# ---------------------------------------------------------------------------


class _OperatorBackend:
    """Stub experiment backend with idle GPUs and a no-op run launcher."""

    def query_gpus(self, _target_id: str) -> list[dict[str, int]]:
        return [
            {"id": 0, "total_mb": 20000, "free_mb": 20000, "used_mb": 0},
            {"id": 1, "total_mb": 20000, "free_mb": 20000, "used_mb": 0},
        ]

    def exp_run(self, target_id: str, cmd: str, gpu_ids: list[int] | None) -> dict:
        return {
            "run_id": "run-0",
            "target_id": target_id,
            "cmd": cmd,
            "gpu_ids": gpu_ids,
            "pid": 1234,
            "log_path": "/tmp/run-0.log",
        }

    def exp_status(self, _t: str, _r: str) -> dict:
        return {"state": "running", "log_tail": ""}

    def exp_kill(self, _t: str, _r: str) -> dict:
        return {"killed": True}


class TestQueueStatusAutoReconcile:
    """Issue #25: status() must run a reconcile when the queue is stale.

    Operator-mode (no ./gru daemon) used to silently stall: the queue
    sat at no_capacity for hours while real GPUs were idle. status()
    is the natural read surface to drive a refresh from."""

    def test_stale_status_triggers_reconcile_and_dispatches_pending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from minions.tools import experiment_scheduler as sched_mod
        from minions.tools import experiment_ssh as ssh_mod
        from minions.tools.experiment_scheduler import ExperimentScheduler, QueueUnit

        backend = _OperatorBackend()
        db_path = tmp_path / "scheduler.sqlite"

        def fake_scheduler(_port: int | None = None) -> ExperimentScheduler:
            return ExperimentScheduler(
                db_path=db_path,
                target_ids=["local"],
                query_gpus_fn=backend.query_gpus,
                exp_run_fn=backend.exp_run,
                exp_status_fn=backend.exp_status,
                exp_kill_fn=backend.exp_kill,
            )

        monkeypatch.setattr(ssh_mod, "_scheduler", fake_scheduler)
        # Make every prior reconcile look stale so the auto-reconcile fires.
        monkeypatch.setattr(ssh_mod, "_stale_reconcile_seconds", lambda: 0)

        # Seed the queue with a pending unit that *can* be placed on the
        # idle GPUs, but rewind the scheduler's last_reconcile_at to a
        # time long enough ago that _is_stale() returns True.
        sched = fake_scheduler()
        sched.submit(
            [QueueUnit(cmd="echo a", gpus_needed=1, min_free_mb=1000)],
            requester="expert",
            reconcile=False,
        )
        # Force a stale timestamp directly via the meta table.
        with sched._tx() as conn:
            sched._set_meta(conn, "last_reconcile_at", "2020-01-01T00:00:00+00:00")

        result = ssh_mod.exp_queue_status(ExpQueueStatusArgs())

        # The auto-reconcile must have launched the pending unit.
        # Successful launch transitions the unit to 'launching' or 'running'.
        unit_states = {u["status"] for u in result["units"]}
        assert unit_states & {"launching", "running"}, (
            f"expected launching/running after auto-reconcile, got {unit_states}"
        )
        # The post-reconcile timestamp must be fresher than the seeded stale one.
        assert result["last_reconcile_at"] != "2020-01-01T00:00:00+00:00"

        # Restore unused-import warning suppressors.
        _ = sched_mod

    def test_fresh_status_does_not_trigger_reconcile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When last_reconcile_at is recent, status() should be a pure read.

        Otherwise every status call would be a launch storm — the daemon
        and the operator both call status; back-to-back calls must not
        each fire a reconcile.
        """
        from minions.tools import experiment_ssh as ssh_mod
        from minions.tools.experiment_scheduler import ExperimentScheduler, QueueUnit

        backend = _OperatorBackend()
        db_path = tmp_path / "scheduler.sqlite"
        launch_count = {"n": 0}

        def counting_run(*args, **kwargs):
            launch_count["n"] += 1
            return backend.exp_run(*args, **kwargs)

        def fake_scheduler(_port: int | None = None) -> ExperimentScheduler:
            return ExperimentScheduler(
                db_path=db_path,
                target_ids=["local"],
                query_gpus_fn=backend.query_gpus,
                exp_run_fn=counting_run,
                exp_status_fn=backend.exp_status,
                exp_kill_fn=backend.exp_kill,
            )

        monkeypatch.setattr(ssh_mod, "_scheduler", fake_scheduler)
        # Long stale window — fresh reconciles count as fresh.
        monkeypatch.setattr(ssh_mod, "_stale_reconcile_seconds", lambda: 3600)

        sched = fake_scheduler()
        sched.submit(
            [QueueUnit(cmd="echo a", gpus_needed=1, min_free_mb=1000)],
            requester="expert",
        )
        # The submit reconciled and launched once.
        assert launch_count["n"] == 1

        # A status call right after must NOT re-launch.
        ssh_mod.exp_queue_status(ExpQueueStatusArgs())
        ssh_mod.exp_queue_status(ExpQueueStatusArgs())
        assert launch_count["n"] == 1
