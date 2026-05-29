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
    kwargs: dict = {
        "cfg": GruConfig(agent_host="claude"),
        "role_name": "coder",
        "project_port": 37596,
        "project_agent_id": "coder",
        "system_path": system,
        "allowed_tools": "Read,Write",
        "workspace": tmp_path,
        "session_name": "p37596/coder",
    }
    kwargs.update(overrides)
    return build_role_invocation(**kwargs)


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


def test_ultracode_omitted_by_default(tmp_path: Path) -> None:
    # ultracode is opt-in at the builder layer; role_launcher passes the
    # cfg-resolved value. With no override the builder must not emit --settings.
    invocation = _build(tmp_path)
    assert "--settings" not in invocation.command


def test_ultracode_emits_settings_flag(tmp_path: Path) -> None:
    invocation = _build(tmp_path, ultracode=True)
    cmd = invocation.command
    assert "--settings" in cmd
    # The value must be the ultracode JSON literal, NOT an --effort flag:
    # `claude --effort ultracode` is rejected by the CLI validator.
    idx = cmd.index("--settings")
    assert cmd[idx + 1] == '{"ultracode": true}'
    assert "--effort" not in cmd


def test_ultracode_pairs_with_model(tmp_path: Path) -> None:
    invocation = _build(tmp_path, model="claude-opus-4-8[1m]", ultracode=True)
    cmd = invocation.command
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "claude-opus-4-8[1m]"
    assert "--settings" in cmd


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
    assert "mos_draft_summary" in prompt
    assert prompt.index("mos_draft_summary") < prompt.rindex("mos_await_events")


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


def test_invocation_omits_fallback_model_for_long_lived_role(tmp_path: Path) -> None:
    # --fallback-model is a --print-only flag (Claude Code 2.1.152). Long-lived
    # Role processes run interactive; the flag is silently ignored there. The
    # auto-fallback feature is wired into the --print spawn sites instead
    # (minions/tools/review.py and minions/tools/adjudicator.py), so the Role
    # argv must NOT carry it regardless of GruConfig.fallback_model.
    invocation = _build(tmp_path)
    assert "--fallback-model" not in invocation.command
    # Even if a caller threads fallback_model through (back-compat), it must
    # not surface as a CLI flag.
    sig = build_role_invocation.__code__.co_varnames
    assert "fallback_model" not in sig, (
        "build_role_invocation should not accept fallback_model — it is a "
        "--print-only flag and only applies to review.py / adjudicator.py."
    )


# --- ToolSearch cold-start warmup (regression for project_37596 keyword-miss) ---


_WARMUP_HEADER = "Step 0 (warmup, do this BEFORE step 1):"


def _cold_prompt(role: str) -> str:
    return build_forever_loop_prompt(role_name=role, port=37596)


def test_warmup_block_present_for_eacn_roles() -> None:
    for role in ("coder", "ethics", "writer"):
        prompt = _cold_prompt(role)
        assert _WARMUP_HEADER in prompt, f"warmup missing for {role}"
        assert "select:" in prompt
        assert "mos_await_events" in prompt
        assert "mos_draft_summary" in prompt


def test_warmup_block_present_for_noter() -> None:
    prompt = _cold_prompt("noter")
    assert _WARMUP_HEADER in prompt
    assert "select:" in prompt
    # Noter does not use mos_await_events; it uses mos_noter_wait.
    assert "mos_noter_wait" in prompt
    assert "mos_draft_commit_shared" in prompt


def test_warmup_block_handles_expert_name_shapes() -> None:
    # Expert roles ship as bare "expert", "expert-<slug>", or "<slug>-expert".
    # All three must collapse to the same warmup list.
    bare = _cold_prompt("expert")
    prefix = _cold_prompt("expert-gpu-perf")
    suffix = _cold_prompt("theory-normalization-expert")
    for prompt in (bare, prefix, suffix):
        assert _WARMUP_HEADER in prompt
        assert "eacn3_send_message" in prompt
        assert "mos_await_events" in prompt


def test_warmup_block_steers_away_from_keyword_search() -> None:
    # Pitfall: project_37596 / role-expert-gpu-perf.log shows the role doing
    # ToolSearch with keyword "MinionsOS tools" and getting nothing back.
    # The warmup MUST tell the role to use select:<id> and lookup.py, not
    # keyword search, for MinionsOS tools.
    prompt = _cold_prompt("coder")
    assert "MANUAL/scripts/lookup.py" in prompt
    assert "keyword" in prompt.lower()


def test_warmup_block_appears_before_step_1() -> None:
    # Step 0 must come before "1. Call `mos_draft_summary()`" so the role
    # warms schemas before its very first MCP call.
    prompt = _cold_prompt("coder")
    step0 = prompt.index(_WARMUP_HEADER)
    step1 = prompt.index("1. Call `mos_draft_summary()`")
    assert step0 < step1
