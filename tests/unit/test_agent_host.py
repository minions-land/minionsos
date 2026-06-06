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
        "role_name": "expert",
        "project_port": 37596,
        "project_agent_id": "expert",
        "system_path": system,
        "allowed_tools": "Read,Write",
        "workspace": tmp_path,
        "session_name": "p37596/expert",
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
    invocation = _build(tmp_path, session_name="p37596/expert")
    assert "--name" in invocation.command
    assert "p37596/expert" in invocation.command
    assert invocation.session_name == "p37596/expert"


def test_initial_prompt_drives_forever_loop(tmp_path: Path) -> None:
    invocation = _build(tmp_path, role_name="expert")
    prompt = invocation.initial_prompt
    assert "expert" in prompt
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
    assert "mos_draft_view" in prompt
    assert prompt.index("mos_draft_view") < prompt.rindex("mos_await_events")


def test_forever_loop_prompt_is_role_specific() -> None:
    expert = build_forever_loop_prompt(role_name="expert")
    ethics = build_forever_loop_prompt(role_name="ethics")
    assert "`expert`" in expert
    assert "`ethics`" in ethics
    assert expert != ethics


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
        role_name="expert",
        project_port=37596,
        project_agent_id="expert",
        system_path=system,
        allowed_tools="Read,Write",
        workspace=tmp_path,
        session_name="p37596/expert",
        resume=True,
    )
    # When resume=True, --resume must appear AND its value must be the
    # same human-readable session_name we set with --name (Claude Code
    # accepts session titles as a --resume value).
    assert "--resume" in invocation.command
    resume_index = invocation.command.index("--resume")
    assert invocation.command[resume_index + 1] == "p37596/expert"
    # And --name is still there with the same value, so the two flags are
    # consistent.
    assert "--name" in invocation.command
    name_index = invocation.command.index("--name")
    assert invocation.command[name_index + 1] == "p37596/expert"


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
    for role in ("expert", "ethics"):
        prompt = _cold_prompt(role)
        assert _WARMUP_HEADER in prompt, f"warmup missing for {role}"
        assert "select:" in prompt
        assert "mos_await_events" in prompt
        assert "mos_draft_view" in prompt


def test_warmup_block_for_ethics_includes_curation_tools() -> None:
    """Ethics is the merged memory curator — its warmup primes the draft-commit
    and Book curation tools."""
    prompt = _cold_prompt("ethics")
    assert _WARMUP_HEADER in prompt
    assert "select:" in prompt
    assert "mos_draft_commit_shared" in prompt
    assert "mos_book_ingest" in prompt


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
    prompt = _cold_prompt("expert")
    assert "MANUAL/scripts/lookup.py" in prompt
    assert "keyword" in prompt.lower()


def test_warmup_block_appears_before_step_1() -> None:
    # Step 0 must come before "1. Call `mos_draft_view()`" so the role
    # warms schemas before its very first MCP call.
    prompt = _cold_prompt("expert")
    step0 = prompt.index(_WARMUP_HEADER)
    step1 = prompt.index("1. Call `mos_draft_view()`")
    assert step0 < step1


# --- Issue #86: quiet-branch discipline (initiate vs drain-silently) ---


def test_eacn_prompt_pairs_drain_silently_with_initiate() -> None:
    # Issue #86 failure mode 3: roles that only learn "idle silently" mutually
    # yield and deadlock. The forever-loop prompt must teach BOTH halves:
    # drain a no-decision event silently, AND initiate (DM / task) when idle
    # or blocked rather than passively re-polling.
    for role in ("ethics", "expert"):
        prompt = _cold_prompt(role)
        flat = " ".join(prompt.split())
        assert "drain-silently vs. initiate" in flat, f"missing paired rule for {role}"
        assert "INITIATE, do not wait" in flat, f"missing initiate half for {role}"
        assert "DRAINING ONLY" in flat, f"missing drain-silently half for {role}"
        # The deadlock-breaker is task ownership, not chat — pin that framing.
        assert "TASK OWNERSHIP" in flat, f"missing task-ownership framing for {role}"
        assert "invited_agent_ids" in flat, f"missing invited_agent_ids for {role}"
        # Both initiation tools are named in the quiet-branch guidance.
        assert "eacn3_send_message" in prompt
        assert "eacn3_create_task" in prompt


def test_eacn_prompt_keeps_initiate_distinct_from_keepalive_ack() -> None:
    # The initiate-when-idle rule must NOT bleed into the cache_keepalive turn,
    # which is strictly ack-only. Pin that the quiet-branch block flags the
    # distinction and precedes the keepalive section.
    prompt = _cold_prompt("expert")
    assert "NOT the cache_keepalive turn" in prompt
    assert prompt.index("drain-silently vs. initiate") < prompt.index("Cache keepalive:")


def test_expert_warmup_pins_create_task() -> None:
    # Issue #86: eacn3_create_task must be first-class at cold start for every
    # EACN role. The unified Expert worker must be able to publish a task
    # without a ToolSearch round-trip.
    prompt = _cold_prompt("expert")
    warmup = prompt[prompt.index(_WARMUP_HEADER) : prompt.index("1. Call `mos_draft_view()`")]
    assert "eacn3_create_task" in warmup
    assert "eacn3_send_message" in warmup
