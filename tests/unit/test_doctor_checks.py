"""Unit tests for doctor checks and status JSON keys."""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# A bounded wall-clock ceiling on the `mos` subprocess. `mos doctor` / `mos
# status` shell-outs must stay hermetic; if a future change reintroduces a
# live-backend probe the timeout converts an unbounded hang into a fast,
# legible failure instead of stalling the whole unit suite.
_MOS_TIMEOUT = 60.0

_REPO_ROOT = Path(__file__).parent.parent.parent


def _run_mos(args: list[str], env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_overrides or {})}
    return subprocess.run(
        [sys.executable, "-m", "minions.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO_ROOT),
        timeout=_MOS_TIMEOUT,
    )


@contextlib.contextmanager
def _hermetic_root() -> Iterator[str]:
    """Yield a MINIONS_ROOT that mirrors the real repo but has an empty registry.

    ``mos doctor`` reads many ``MINIONS_ROOT``-relative paths (``.codex``,
    ``.mcp.json``, ``mcp-servers/``, ``minions/config/`` …) AND iterates every
    *active* project in ``minions/state/projects.json``, probing each backend
    over HTTP. On a developer host that registry can hold hundreds of live
    projects, so a real-root run fans out into hundreds of 3s HTTP probes and
    appears to hang. We symlink every real top-level entry into a temp root —
    and every ``minions/`` child except ``state`` — then drop in a fresh empty
    ``minions/state``. The doctor sees real config/.codex/.mcp.json but a zero
    -project registry, so it never touches a live backend.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for entry in _REPO_ROOT.iterdir():
            if entry.name == "minions":
                continue
            (root / entry.name).symlink_to(entry)
        pkg = root / "minions"
        pkg.mkdir()
        real_pkg = _REPO_ROOT / "minions"
        for child in real_pkg.iterdir():
            if child.name == "state":
                continue
            (pkg / child.name).symlink_to(child)
        (pkg / "state").mkdir()
        yield str(root)


def _doctor_checks(env_overrides: dict | None = None) -> list[dict]:
    """Run `mos doctor --json` hermetically and return the checks list.

    Runs against a throwaway root with an empty project registry (see
    :func:`_hermetic_root`) so no live EACN3 backend is ever probed, keeping
    the test fast and independent of host state. *env_overrides* still wins for
    any key it sets (e.g. ``MINIONS_AGENT_HOST``).
    """
    with _hermetic_root() as root:
        env = {"MINIONS_ROOT": root, **(env_overrides or {})}
        result = _run_mos(["doctor", "--json"], env)
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
        assert "codex-automation" in names
        assert "codex-mcp-config-mounts-core" in names
        assert "codex-mcp-eacn3-direct" in names
        host = next(c for c in checks if c["name"] == "agent-host")
        assert host["detail"] == "codex"
        direct = next(c for c in checks if c["name"] == "codex-mcp-eacn3-direct")
        assert direct["ok"] is True
        automation = next(c for c in checks if c["name"] == "codex-automation")
        assert automation["ok"] is True


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
        assert isinstance(data, dict)
        assert "projects" in data and isinstance(data["projects"], list)
        assert "retired_ports" in data and isinstance(data["retired_ports"], list)
        for row in data["projects"]:
            for key in (
                "port",
                "real_name",
                "status",
                "current_phase",
                "active_roles",
            ):
                assert key in row, f"Missing key {key!r} in status row"


class TestProjectDirOrphans:
    def test_orphan_detection_flags_unknown_or_missing_meta(self, tmp_path: Path) -> None:
        from minions import cli

        known = tmp_path / "project_37596"
        known.mkdir()
        (known / "meta.json").write_text("{}", encoding="utf-8")
        missing_meta = tmp_path / "project_37597"
        missing_meta.mkdir()
        unknown = tmp_path / "project_37598"
        unknown.mkdir()
        (unknown / "meta.json").write_text("{}", encoding="utf-8")

        orphans = cli._find_orphan_project_dirs(tmp_path, {37596, 37597})
        assert missing_meta in orphans
        assert unknown in orphans
        assert known not in orphans


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


class TestConfigKeyDrift:
    """`mos upgrade` ships new *.yaml.example keys but never merges them into an
    existing live *.yaml. The doctor `config-keys-current` check surfaces that
    gap via `cli._config_key_drift`.
    """

    def test_no_drift_when_keys_match(self, tmp_path: Path) -> None:
        from minions import cli

        (tmp_path / "gru.yaml.example").write_text("a: 1\nb: 2\n")
        (tmp_path / "gru.yaml").write_text("a: 9\nb: 8\n")
        assert cli._config_key_drift(tmp_path) == []

    def test_detects_missing_key(self, tmp_path: Path) -> None:
        from minions import cli

        (tmp_path / "gru.yaml.example").write_text("a: 1\nb: 2\nc: 3\n")
        (tmp_path / "gru.yaml").write_text("a: 1\nb: 2\n")  # missing c
        drift = cli._config_key_drift(tmp_path)
        assert len(drift) == 1
        assert "gru.yaml" in drift[0]
        assert "c" in drift[0]

    def test_ignores_unseeded_target(self, tmp_path: Path) -> None:
        from minions import cli

        # Example exists but no live target yet — install.sh will seed it, so
        # this is not drift.
        (tmp_path / "gru.yaml.example").write_text("a: 1\n")
        assert cli._config_key_drift(tmp_path) == []

    def test_extra_live_keys_are_not_drift(self, tmp_path: Path) -> None:
        from minions import cli

        # Operator added their own key not in the example — that's fine.
        (tmp_path / "gru.yaml.example").write_text("a: 1\n")
        (tmp_path / "gru.yaml").write_text("a: 1\nmy_extra: 5\n")
        assert cli._config_key_drift(tmp_path) == []

    def test_real_config_dir_does_not_crash(self) -> None:
        from minions import cli
        from minions.paths import CONFIG_DIR

        # Should return a list (possibly with real drift) and never raise.
        assert isinstance(cli._config_key_drift(CONFIG_DIR), list)
