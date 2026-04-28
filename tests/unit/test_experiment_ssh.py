"""Unit tests for the fire-and-poll Experimenter tool surface."""

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
