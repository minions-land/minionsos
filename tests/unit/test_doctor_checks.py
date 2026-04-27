"""Unit tests for doctor checks and status JSON keys."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_mos(args: list[str], env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_overrides or {})}
    return subprocess.run(
        [sys.executable, "-m", "minions.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).parent.parent.parent),
    )


def _doctor_checks(env_overrides: dict | None = None) -> list[dict]:
    result = _run_mos(["doctor", "--json"], env_overrides)
    return json.loads(result.stdout)


class TestDoctorModelRegistry:
    def test_model_registry_check_present(self) -> None:
        checks = _doctor_checks()
        names = {c["name"] for c in checks}
        assert "model-registry" in names

    def test_model_registry_ok_with_default(self) -> None:
        checks = _doctor_checks()
        mc = next(c for c in checks if c["name"] == "model-registry")
        assert mc["ok"] is True


class TestDoctorAgentHost:
    def test_agent_host_check_present(self) -> None:
        checks = _doctor_checks()
        names = {c["name"] for c in checks}
        assert "agent-host" in names

    def test_codex_host_reports_codex_cli_and_mcp_config(self) -> None:
        checks = _doctor_checks({"MINIONS_AGENT_HOST": "codex"})
        names = {c["name"] for c in checks}
        assert "codex-cli" in names
        assert "codex-mcp-config-mounts-eacn3" in names
        host = next(c for c in checks if c["name"] == "agent-host")
        assert host["detail"] == "codex"


class TestDoctorDebugFlag:
    def test_debug_flag_check_present(self) -> None:
        checks = _doctor_checks()
        names = {c["name"] for c in checks}
        assert "claude-debug-disabled" in names

    def test_debug_disabled_by_default(self) -> None:
        checks = _doctor_checks(env_overrides={"MINIONS_DEBUG": ""})
        dc = next(c for c in checks if c["name"] == "claude-debug-disabled")
        assert dc["ok"] is True

    def test_debug_enabled_when_env_set(self) -> None:
        checks = _doctor_checks({"MINIONS_DEBUG": "1"})
        dc = next(c for c in checks if c["name"] == "claude-debug-disabled")
        assert dc["ok"] is False


class TestStatusJson:
    def test_status_json_parses_and_has_phase1_keys(self, tmp_path: Path) -> None:
        result = _run_mos(["status", "--json"], {"MINIONS_ROOT": str(tmp_path)})
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        for row in data:
            for key in (
                "port",
                "name",
                "status",
                "backend_alive",
                "agents",
                "queue_depth",
                "recent_failures",
            ):
                assert key in row, f"Missing key {key!r} in status row"


class TestGruLoopDebugFlag:
    def test_debug_flag_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINIONS_DEBUG", raising=False)
        from minions.gru import loop as gru_loop

        importlib.reload(gru_loop)
        assert gru_loop.DEBUG_MODE is False

    def test_debug_flag_on_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINIONS_DEBUG", "1")
        from minions.gru import loop as gru_loop

        importlib.reload(gru_loop)
        assert gru_loop.DEBUG_MODE is True
