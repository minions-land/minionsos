"""Unit tests for the fire-and-poll Coder experiment tool surface."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from minions.tools.experiment_ssh import (
    ExpListArgs,
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
        final = exp_wait(
            ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10)
        )
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
        final = exp_wait(
            ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10)
        )
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
        final = exp_wait(
            ExpWaitArgs(target_id=local_target, run_id=run["run_id"], timeout=10)
        )
        assert final["state"] == "exited"
        log_path = Path(run["log_path"])
        for _ in range(20):
            if "CVD=" in log_path.read_text():
                break
            time.sleep(0.05)
        assert "CVD=unset" in log_path.read_text()
