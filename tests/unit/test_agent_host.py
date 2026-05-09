"""Unit tests for provider-neutral agent-host command builders."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.config import GruConfig
from minions.lifecycle.agent_host import build_role_invocation
from minions.paths import MINIONS_ROOT


def test_claude_role_invocation_preserves_legacy_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINIONS_AGENT_HOST", raising=False)
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")
    invocation = build_role_invocation(
        cfg=GruConfig(agent_host="claude"),
        role_name="coder",
        project_port=37596,
        system_path=system,
        allowed_tools="Read,Write",
        message="hello",
        workspace=tmp_path,
    )
    assert invocation.host_name == "claude"
    assert invocation.cwd == tmp_path
    assert invocation.stdin_text == "hello"
    assert invocation.command[:5] == ["uv", "run", "--project", str(MINIONS_ROOT), "claude"]
    assert "--append-system-prompt" in invocation.command
    assert "--allowed-tools" in invocation.command
    assert "--permission-mode" in invocation.command
    assert "-p" in invocation.command


def test_codex_role_invocation_uses_exec_stdin_and_defers_system_to_agents_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINIONS_AGENT_HOST", raising=False)
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")
    invocation = build_role_invocation(
        cfg=GruConfig(agent_host="codex", codex_model="gpt-test"),
        role_name="coder",
        project_port=37596,
        system_path=system,
        allowed_tools="Read,Write",
        message="event payload",
        workspace=tmp_path,
    )
    assert invocation.host_name == "codex"
    assert invocation.command[:2] == ["codex", "exec"]
    assert invocation.command[-1] == "-"
    assert "--ask-for-approval" not in invocation.command
    assert "--sandbox" not in invocation.command
    assert "--dangerously-bypass-approvals-and-sandbox" in invocation.command
    assert "-c" in invocation.command
    assert 'model_reasoning_effort="xhigh"' in invocation.command
    assert "--model" in invocation.command
    assert "gpt-test" in invocation.command
    assert "--append-system-prompt" not in invocation.command
    assert "--allowed-tools" not in invocation.command
    # SYSTEM.md must NOT be inlined in stdin; it reaches Codex via
    # <workspace>/AGENTS.md (auto-discovered) so rules live in the host
    # instruction layer outside the conversation body.
    assert "role system" not in invocation.stdin_text
    assert "# Role System Prompt" not in invocation.stdin_text
    assert "AGENTS.md" in invocation.stdin_text
    assert "event payload" in invocation.stdin_text
    assert f"Workspace: `{tmp_path}`" in invocation.stdin_text
    assert "MinionsOS contract labels" in invocation.stdin_text
    assert "`Task` means the current host's native subagent/delegation capability" in (
        invocation.stdin_text
    )
    # Subprocess cwd must be the workspace so Codex auto-discovery finds
    # AGENTS.md, and resume filters match this role's session.
    assert invocation.cwd == tmp_path


def test_codex_role_invocation_can_disable_bypass_with_danger_full_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINIONS_AGENT_HOST", raising=False)
    invocation = build_role_invocation(
        cfg=GruConfig(
            agent_host="codex",
            codex_bypass_approvals_and_sandbox=False,
            codex_sandbox="danger-full-access",
            codex_approval_policy="never",
        ),
        role_name="coder",
        project_port=37596,
        system_path=None,
        allowed_tools="Read,Write",
        message="event payload",
        workspace=tmp_path,
    )
    assert "--dangerously-bypass-approvals-and-sandbox" not in invocation.command
    assert "--sandbox" in invocation.command
    assert "danger-full-access" in invocation.command
    assert 'approval_policy="never"' in invocation.command
