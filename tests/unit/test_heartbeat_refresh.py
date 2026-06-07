"""Tests for the heartbeat_refresh PreToolUse hook (GitHub Issue #4 fix)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK = REPO_ROOT / "minions" / "hooks" / "heartbeat_refresh.py"


def _run(stdin: str = "{}", env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=proc_env,
        check=False,
    )


def test_heartbeat_written_when_role_env_present(tmp_path: Path) -> None:
    """The happy path: role env + workspace → heartbeat file appears with
    a fresh ISO timestamp + the role identity."""
    workspace = tmp_path / "branches" / "expert"
    workspace.mkdir(parents=True)

    result = _run(
        env={
            "MINIONS_ROLE_NAME": "expert",
            "MINIONS_WORKSPACE": str(workspace),
            "MINIONS_AGENT_ID": "expert",
        }
    )
    assert result.returncode == 0
    hb = workspace / ".minionsos" / "heartbeat"
    assert hb.is_file()
    payload = json.loads(hb.read_text(encoding="utf-8"))
    assert payload["role"] == "expert"
    assert payload["agent_id"] == "expert"
    assert payload["source"] == "pretool_hook"
    assert "T" in payload["alive_at"]  # ISO-8601 with time component


def test_heartbeat_no_op_when_role_missing(tmp_path: Path) -> None:
    """Outside a Role process, the hook is a silent no-op (no exception,
    no stray files). MinionsOS Role launcher always sets MINIONS_ROLE_NAME;
    this protects local dev sessions where the env is absent."""
    result = _run(env={"MINIONS_WORKSPACE": str(tmp_path)})
    assert result.returncode == 0
    assert not (tmp_path / ".minionsos").exists()


def test_heartbeat_no_op_when_workspace_missing(tmp_path: Path) -> None:
    """If MINIONS_WORKSPACE points at a non-existent dir, the hook still
    exits 0 — never block a tool call over a stale env."""
    bogus = tmp_path / "does-not-exist"
    result = _run(
        env={
            "MINIONS_ROLE_NAME": "expert",
            "MINIONS_WORKSPACE": str(bogus),
        }
    )
    assert result.returncode == 0
    assert not bogus.exists()


def test_heartbeat_overwrites_each_call(tmp_path: Path) -> None:
    """Every tool call should overwrite (not append) the heartbeat file
    so the file size stays bounded and the latest timestamp is always
    on top."""
    workspace = tmp_path / "branches" / "ethics"
    workspace.mkdir(parents=True)
    env = {
        "MINIONS_ROLE_NAME": "ethics",
        "MINIONS_WORKSPACE": str(workspace),
        "MINIONS_AGENT_ID": "ethics",
    }
    _run(env=env)
    first = json.loads((workspace / ".minionsos" / "heartbeat").read_text(encoding="utf-8"))
    _run(env=env)
    second = json.loads((workspace / ".minionsos" / "heartbeat").read_text(encoding="utf-8"))
    # Both reads should parse cleanly — no JSONL accumulation.
    assert isinstance(first, dict) and isinstance(second, dict)
    # alive_at must be >= the previous one (clocks tick forward).
    assert second["alive_at"] >= first["alive_at"]
