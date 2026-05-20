"""Unit tests for the long-lived Claude agent-host invocation builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.config import GruConfig
from minions.lifecycle.agent_host import build_forever_loop_prompt, build_role_invocation
from minions.paths import MINIONS_ROOT


def _build(tmp_path: Path, **overrides) -> object:
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")
    return build_role_invocation(
        cfg=overrides.pop("cfg", GruConfig(agent_host="claude")),
        role_name=overrides.pop("role_name", "coder"),
        project_port=overrides.pop("project_port", 37596),
        project_agent_id=overrides.pop("project_agent_id", "coder"),
        system_path=overrides.pop("system_path", system),
        allowed_tools=overrides.pop("allowed_tools", "Read,Write"),
        workspace=overrides.pop("workspace", tmp_path),
        session_name=overrides.pop("session_name", "p37596/coder"),
    )


def test_claude_invocation_basic_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIONS_AGENT_HOST", raising=False)
    invocation = _build(tmp_path)
    assert invocation.host_name == "claude"
    assert invocation.cwd == tmp_path
    assert invocation.command[:5] == ["uv", "run", "--project", str(MINIONS_ROOT), "claude"]
    assert "--append-system-prompt" in invocation.command
    assert "--allowed-tools" in invocation.command
    assert "--permission-mode" in invocation.command
    assert "bypassPermissions" in invocation.command
    # Long-lived form: no -p / --print (those exit after one turn).
    assert "-p" not in invocation.command
    assert "--print" not in invocation.command


def test_claude_invocation_carries_session_name(tmp_path: Path) -> None:
    invocation = _build(tmp_path, session_name="p37596/coder")
    assert "--name" in invocation.command
    assert "p37596/coder" in invocation.command
    assert invocation.session_name == "p37596/coder"


def test_initial_prompt_drives_forever_loop(tmp_path: Path) -> None:
    invocation = _build(tmp_path, role_name="writer")
    prompt = invocation.initial_prompt
    assert "writer" in prompt
    assert "mos_await_events" in prompt
    # Gru priority is non-negotiable.
    assert "Gru" in prompt
    assert "FIRST" in prompt
    # The loop must terminate every cycle with another mos_await_events call.
    flat = " ".join(prompt.split())
    assert "event loop runs forever" in flat
    assert "Do not emit a final assistant turn that does not end with `mos_await_events()`" in flat
    # Subagent dispatch path is named.
    assert "Task" in prompt or "subagent" in prompt.lower()
    # Cold start: orient on the DAG before calling mos_await_events.
    assert "mos_scratchpad_summary" in prompt
    assert prompt.index("mos_scratchpad_summary") < prompt.rindex("mos_await_events")


def test_forever_loop_prompt_is_role_specific() -> None:
    coder = build_forever_loop_prompt(role_name="coder")
    writer = build_forever_loop_prompt(role_name="writer")
    assert "`coder`" in coder
    assert "`writer`" in writer
    assert coder != writer


def test_invocation_omits_resume_by_default(tmp_path: Path) -> None:
    invocation = _build(tmp_path)
    # Cold start (the default) must NEVER carry --resume; that flag is
    # only meaningful when there's a prior session to reattach to.
    assert "--resume" not in invocation.command


def test_invocation_appends_resume_when_requested(tmp_path: Path) -> None:
    system = tmp_path / "SYSTEM.md"
    system.write_text("role system", encoding="utf-8")
    invocation = build_role_invocation(
        cfg=GruConfig(agent_host="claude"),
        role_name="coder",
        project_port=37596,
        project_agent_id="coder",
        system_path=system,
        allowed_tools="Read,Write",
        workspace=tmp_path,
        session_name="p37596/coder",
        resume=True,
    )
    # When resume=True, --resume must appear AND its value must be the
    # same human-readable session_name we set with --name (Claude Code
    # accepts session titles as a --resume value).
    assert "--resume" in invocation.command
    resume_index = invocation.command.index("--resume")
    assert invocation.command[resume_index + 1] == "p37596/coder"
    # And --name is still there with the same value, so the two flags are
    # consistent.
    assert "--name" in invocation.command
    name_index = invocation.command.index("--name")
    assert invocation.command[name_index + 1] == "p37596/coder"
