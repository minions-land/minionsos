"""Smoke test for Role-spawn sidecar lock integration.

Verifies that ``launch_role_process`` writes a locked entry to the global
title-registry under the same UUID it passes to ``claude --session-id``.

This test does NOT spawn a real claude process — it stubs the tmux spawn
helper so the launcher returns without forking. That's deliberate: the
contract we want to pin is the *registry write*, not Claude Code itself.

Cleanup discipline: any tmux session created during the test is killed in
the finally block, even on assertion failure. The test never starts real
``claude`` processes, so there are no orphan / zombie risks beyond tmux.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from minions.lifecycle import sidecar_lock


def _kill_tmux_sessions(prefix: str) -> None:
    """Kill any tmux session whose name starts with *prefix*. Best-effort."""
    if not _have_tmux():
        return
    try:
        result = subprocess.run(["tmux", "ls"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return
    for line in (result.stdout or "").splitlines():
        name = line.split(":", 1)[0]
        if name.startswith(prefix):
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, check=False)


def _have_tmux() -> bool:
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


@pytest.fixture
def fake_claude_home(tmp_path: Path, monkeypatch):
    """Point the sidecar lock at a temporary Claude home for the test."""
    home = tmp_path / "claude_home"
    home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return home


def test_launch_role_process_locks_registry(fake_claude_home: Path, tmp_path: Path, monkeypatch):
    """launch_role_process should pre-allocate a UUID and lock the registry."""
    # Stub heavy launcher internals: we want to verify the lock happens, not
    # actually spawn claude.
    captured: dict[str, object] = {}

    from minions.lifecycle import role_launcher
    from minions.state.store import RoleEntry

    def fake_have_tmux() -> bool:
        return True

    def fake_has_session(name: str) -> bool:
        return False

    def fake_spawn_tmux(**kwargs):
        captured["argv"] = list(kwargs.get("argv") or [])
        captured["session_name"] = kwargs.get("session_name")

    monkeypatch.setattr(role_launcher, "_have_tmux", fake_have_tmux)
    monkeypatch.setattr(role_launcher, "_tmux_has_session", fake_has_session)
    monkeypatch.setattr(role_launcher, "_spawn_tmux", fake_spawn_tmux)

    # Stub out paths that would touch disk under the test repo.
    workspace = tmp_path / "fake_workspace"
    workspace.mkdir()
    log_dir = tmp_path / "logs"

    monkeypatch.setattr(role_launcher, "project_role_workspace", lambda port, role: workspace)
    monkeypatch.setattr(role_launcher, "project_workspace", lambda port: workspace)
    monkeypatch.setattr(role_launcher, "project_role_log", lambda port, role: log_dir / "role.log")
    monkeypatch.setattr(
        role_launcher, "project_session_name", lambda port, role: f"mos-{port}-{role}"
    )

    # Stub gru config + system prompt + role-system paths to avoid touching the real install.
    from minions.config import GruConfig

    fake_cfg = GruConfig()

    monkeypatch.setattr(role_launcher, "load_gru_config", lambda: fake_cfg)
    monkeypatch.setattr(role_launcher, "_combined_system_prompt", lambda *a, **kw: None)
    monkeypatch.setattr(role_launcher, "_role_system_paths", lambda *a, **kw: [])
    monkeypatch.setattr(role_launcher, "_role_model", lambda cfg, role: None)

    # Stub _role_env so it doesn't try to write reel dirs etc.
    monkeypatch.setattr(role_launcher, "_role_env", lambda **kw: {"FAKE": "1"})

    role_entry = RoleEntry(
        name="coder",
        state="active",
        eacn_agent_id="agent-coder-test",
        workspace_path=str(workspace),
        session_name="mos-9991-coder",
    )

    prefix = "mos-9991-"
    try:
        result = role_launcher.launch_role_process(role_entry, project_port=9991)

        # The launcher should have started a session.
        assert result["started"] is True
        assert result["session_name"] == "mos-9991-coder"

        # The argv should include --session-id with a valid UUID.
        argv = captured.get("argv") or []
        assert "--session-id" in argv, f"--session-id missing from argv: {argv}"
        sid_index = argv.index("--session-id")
        sid = argv[sid_index + 1]
        uuid.UUID(sid)  # raises if not a valid UUID

        # The registry should now contain a locked entry under that sid.
        registry = fake_claude_home / "title-registry.json"
        assert registry.exists(), "title-registry.json was not created"
        data = json.loads(registry.read_text(encoding="utf-8"))
        assert sid in data, f"session_id {sid} missing from registry"
        entry = data[sid]
        assert entry["locked"] is True
        assert entry["title"] == "mos-9991-coder"
        assert entry["source"] == "minionsos"
    finally:
        # Hard cleanup: even though _spawn_tmux is stubbed, _kill_tmux_sessions
        # is a defensive sweep in case future changes start a real session.
        _kill_tmux_sessions(prefix)
        # Drop the registry file the test created.
        for f in fake_claude_home.iterdir():
            if f.is_file():
                f.unlink()


def test_sidecar_lock_helper_exposed():
    """The sidecar_lock module must expose its public surface for callers."""
    assert callable(sidecar_lock.allocate_session_id)
    assert callable(sidecar_lock.lock_session_title)
    assert "allocate_session_id" in sidecar_lock.__all__
    assert "lock_session_title" in sidecar_lock.__all__
