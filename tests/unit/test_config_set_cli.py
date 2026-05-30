"""Unit tests for `mos config set` — the gru.yaml write path the TUI uses.

`mos config set <key> <value>` is the only sanctioned write into gru.yaml
(the TUI settings panel shells out to it). These pin its guardrails:
  - only the scalar allowlist is writable (no structural config),
  - the context_pressure_medium < high invariant is enforced,
  - a valid write round-trips and is readable by load_gru_config.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import minions.cli as cli

runner = CliRunner()


@pytest.fixture
def _tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the CLI's CONFIG_DIR at a temp dir so writes don't touch the repo."""
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    return tmp_path


def _read(gru_yaml: Path) -> dict:
    return yaml.safe_load(gru_yaml.read_text(encoding="utf-8")) or {}


class TestConfigSet:
    def test_valid_write_persists_and_roundtrips(self, _tmp_config: Path) -> None:
        result = runner.invoke(cli.app, ["config", "set", "context_pressure_high_tokens", "250000"])
        assert result.exit_code == 0, result.output
        data = _read(_tmp_config / "gru.yaml")
        assert data["context_pressure_high_tokens"] == 250000

    def test_rejects_non_allowlisted_key(self, _tmp_config: Path) -> None:
        result = runner.invoke(cli.app, ["config", "set", "roles_active", "foo"])
        assert result.exit_code != 0
        assert "not a settable config key" in result.output
        # Nothing written.
        assert not (_tmp_config / "gru.yaml").exists()

    def test_rejects_non_int_value(self, _tmp_config: Path) -> None:
        result = runner.invoke(cli.app, ["config", "set", "context_pressure_high_tokens", "lots"])
        assert result.exit_code != 0
        assert "not a valid int" in result.output

    def test_enforces_medium_below_high(self, _tmp_config: Path) -> None:
        # Seed a high of 200K, then try to set medium >= high.
        runner.invoke(cli.app, ["config", "set", "context_pressure_high_tokens", "200000"])
        result = runner.invoke(
            cli.app, ["config", "set", "context_pressure_medium_tokens", "250000"]
        )
        assert result.exit_code != 0
        assert "must be <" in result.output
        # The bad medium must NOT have been written.
        data = _read(_tmp_config / "gru.yaml")
        assert data.get("context_pressure_medium_tokens", 0) != 250000

    def test_preserves_other_keys(self, _tmp_config: Path) -> None:
        gru_yaml = _tmp_config / "gru.yaml"
        gru_yaml.write_text(
            "cache_keepalive_seconds: 240\nallow_web_search: true\n", encoding="utf-8"
        )
        result = runner.invoke(
            cli.app, ["config", "set", "context_pressure_medium_tokens", "150000"]
        )
        assert result.exit_code == 0, result.output
        data = _read(gru_yaml)
        # New key written, prior keys preserved.
        assert data["context_pressure_medium_tokens"] == 150000
        assert data["cache_keepalive_seconds"] == 240
        assert data["allow_web_search"] is True

    def test_set_value_is_loadable_by_gru_config(self, _tmp_config: Path) -> None:
        runner.invoke(cli.app, ["config", "set", "context_pressure_high_tokens", "300000"])
        from minions.config import load_gru_config

        cfg = load_gru_config(_tmp_config)
        assert cfg.context_pressure_high_tokens == 300000
