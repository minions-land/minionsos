"""Tests for durable workspace checkpoints and local/remote git behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from minions.config import resolve_whitelist
from minions.lifecycle import project as project_mod
from minions.state.store import ProjectEntry, RoleEntry, StateStore
from minions.tools import mcp_server


@dataclass
class FakeRunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@pytest.fixture(autouse=True)
def _isolate_runtime_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "minions.lifecycle.project.project_main_workspace",
        lambda port: tmp_path / f"project_{port}" / "workspace" / "main",
    )
    monkeypatch.setattr(
        "minions.lifecycle.project.project_role_workspace",
        lambda port, role_name: tmp_path / f"project_{port}" / "workspace" / "roles" / role_name,
    )
    monkeypatch.setattr(
        "minions.lifecycle.project.project_session_ledger",
        lambda port: tmp_path / f"project_{port}" / "state" / "session-ledger.json",
    )
    monkeypatch.setattr("minions.lifecycle.project._is_git_work_tree", lambda path: True)


def _make_store(tmp_path: Path, push_target: str | None = None) -> StateStore:
    (tmp_path / "project_37596" / "workspace" / "main").mkdir(parents=True, exist_ok=True)
    (tmp_path / "project_37596" / "workspace" / "roles" / "coder").mkdir(
        parents=True,
        exist_ok=True,
    )
    store = StateStore(root=tmp_path / "state")
    store.add_project(
        ProjectEntry(
            port=37596,
            real_name="checkpoint-project",
            status="active",
            created="2026-05-01T00:00:00Z",
            current_branch="minionsos/project-37596",
            github_push_target=push_target,
            github_push_branch_prefix="minionsos",
            active_roles=[
                RoleEntry(
                    name="coder",
                    state="active",
                    workspace_path=str(
                        tmp_path / "project_37596" / "workspace" / "roles" / "coder"
                    ),
                    workspace_branch="minionsos/project-37596-coder",
                    session_name="p37596/coder",
                    github_push_target=push_target,
                )
            ],
        )
    )
    return store


def test_local_checkpoint_commits_without_push(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = _make_store(tmp_path)
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd, cwd=None, capture_output=None, text=None):
        calls.append((list(cmd), cwd))
        if cmd == ["git", "status", "--porcelain"]:
            return FakeRunResult(0, stdout=" M workspace/main.py\n")
        if cmd == ["git", "add", "-A"]:
            return FakeRunResult(0)
        if cmd[:2] == ["git", "commit"]:
            return FakeRunResult(0, stdout="[main abc123] checkpoint\n")
        if cmd == ["git", "rev-parse", "HEAD"]:
            return FakeRunResult(0, stdout="abc123\n")
        raise AssertionError(f"Unexpected git command: {cmd}")

    monkeypatch.setattr(project_mod.subprocess, "run", fake_run)

    out = project_mod.project_checkpoint_workspace(
        37596,
        message="checkpoint(main): local durable checkpoint",
        store=store,
    )

    assert out["commit_sha"] == "abc123"
    assert out["pushed"] is False
    assert out["push_target"] is None
    assert out["local_branch"] == "minionsos/project-37596"
    assert [cmd for cmd, _cwd in calls] == [
        ["git", "status", "--porcelain"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", "checkpoint(main): local durable checkpoint"],
        ["git", "rev-parse", "HEAD"],
    ]

    ledger = json.loads(
        (tmp_path / "project_37596" / "state" / "session-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["checkpoints"][0]["session_name"] == "p37596/main"
    assert ledger["checkpoints"][0]["pushed"] is False


def test_role_checkpoint_pushes_to_namespaced_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = _make_store(tmp_path, push_target="git@github.com:Minions-Land/MinionsOS")
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, capture_output=None, text=None):
        calls.append(list(cmd))
        if cmd == ["git", "status", "--porcelain"]:
            return FakeRunResult(0, stdout=" M workspace/roles/coder/report.md\n")
        if cmd == ["git", "add", "-A"]:
            return FakeRunResult(0)
        if cmd[:2] == ["git", "commit"]:
            return FakeRunResult(0, stdout="[coder def456] checkpoint\n")
        if cmd == ["git", "rev-parse", "HEAD"]:
            return FakeRunResult(0, stdout="def456\n")
        if cmd[:2] == ["git", "push"]:
            return FakeRunResult(0, stdout="ok\n")
        raise AssertionError(f"Unexpected git command: {cmd}")

    monkeypatch.setattr(project_mod.subprocess, "run", fake_run)

    out = project_mod.project_checkpoint_workspace(
        37596,
        role_name="coder",
        message="checkpoint(coder): durable role checkpoint",
        store=store,
    )

    assert out["commit_sha"] == "def456"
    assert out["pushed"] is True
    assert out["push_branch"] == "minionsos/p37596/coder"
    assert calls[-1] == [
        "git",
        "push",
        "git@github.com:Minions-Land/MinionsOS",
        "HEAD:minionsos/p37596/coder",
    ]
    assert "mos_project_checkpoint_workspace" in resolve_whitelist("coder", "main")
    ledger = json.loads(
        (tmp_path / "project_37596" / "state" / "session-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["checkpoints"][0]["role_name"] == "coder"
    assert ledger["checkpoints"][0]["pushed"] is True


def test_checkpoint_tool_wrapper_delegates_to_lifecycle(monkeypatch: pytest.MonkeyPatch):
    out = {"port": 37596, "ok": True}

    monkeypatch.setattr(mcp_server, "_project_checkpoint_workspace", lambda *a, **kw: out)

    result = mcp_server.mos_project_checkpoint_workspace(
        mcp_server.ProjectCheckpointArgs(port=37596, role_name="coder", message="hi")
    )

    assert result is out
