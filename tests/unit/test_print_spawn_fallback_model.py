"""--fallback-model wiring on `claude --print` spawn sites.

Claude Code 2.1.152 documents `--fallback-model` as `--print`-only. Long-lived
interactive Roles silently ignore the flag, so it is intentionally absent from
``minions.lifecycle.agent_host.build_role_invocation``. The auto-fallback
feature is wired into the two `--print` spawn sites instead:

* ``minions.tools.review._spawn_claude_review`` (paper review)
* ``minions.tools.adjudicator._spawn_claude_adjudicate`` (answer adjudication)

These tests intercept ``subprocess.run`` and inspect the resulting argv so we
can verify the flag is appended (and only when configured) without having to
launch a real claude process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from minions.tools import adjudicator as adj_mod
from minions.tools import review as rev_mod


class _RunCapture:
    """Drop-in replacement for ``subprocess.run`` that records the argv."""

    def __init__(self) -> None:
        self.argv: list[str] | None = None

    def __call__(self, cmd: list[str], **_: Any) -> Any:
        self.argv = list(cmd)

        class _Result:
            returncode = 0

        return _Result()


@pytest.fixture()
def patched_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``load_gru_config`` return a config with a deterministic fallback."""

    class _Cfg:
        fallback_model = "claude-sonnet-4-6[1m]"

    monkeypatch.setattr("minions.config.load_gru_config", lambda *_a, **_kw: _Cfg())
    # Clear env overrides so the config-driven path is exercised.
    for var in ("MOS_REVIEW_FALLBACK_MODEL", "MOS_ADJUDICATE_FALLBACK_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_review_spawn_includes_fallback_from_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_config: None,
) -> None:
    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--fallback-model" in capture.argv
    idx = capture.argv.index("--fallback-model")
    assert capture.argv[idx + 1] == "claude-sonnet-4-6[1m]"
    # And the spawn site is --print, which is what makes the flag actually fire.
    assert "--print" in capture.argv


def test_review_spawn_env_override_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_config: None,
) -> None:
    monkeypatch.setenv("MOS_REVIEW_FALLBACK_MODEL", "claude-haiku-4-5-20251001")
    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    idx = capture.argv.index("--fallback-model")
    assert capture.argv[idx + 1] == "claude-haiku-4-5-20251001"


def test_review_spawn_omits_when_config_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Cfg:
        fallback_model = None

    monkeypatch.setattr("minions.config.load_gru_config", lambda *_a, **_kw: _Cfg())
    monkeypatch.delenv("MOS_REVIEW_FALLBACK_MODEL", raising=False)

    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--fallback-model" not in capture.argv


def test_review_spawn_allows_task_but_not_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_config: None
) -> None:
    """The Area-Chair fans out via concurrent foreground Task; Workflow is denied.

    A `--print` turn ends before a backgrounded Workflow completes, so the
    reliable parallelism primitive is concurrent foreground `Task`. `Workflow`
    must not be in `--allowed-tools`.
    """
    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    idx = capture.argv.index("--allowed-tools")
    allowed = capture.argv[idx + 1]
    tools = {t.strip() for t in allowed.split(",")}
    assert "Task" in tools, "Area-Chair must be able to fan out via Task"
    assert "codex" in tools, "aspect subagents delegate volume reading to Codex"
    assert "Workflow" not in tools, "Workflow is background-only; abandoned on --print exit"


def test_review_spawn_sets_ultracode_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_config: None
) -> None:
    monkeypatch.setenv("MOS_REVIEW_ULTRACODE", "1")
    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--settings" in capture.argv
    idx = capture.argv.index("--settings")
    assert "ultracode" in capture.argv[idx + 1]


def test_review_spawn_omits_ultracode_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_config: None
) -> None:
    monkeypatch.setenv("MOS_REVIEW_ULTRACODE", "0")
    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--settings" not in capture.argv


@pytest.mark.parametrize("falsey", ["false", "False", "FALSE", "no", "No", "OFF", "off", "0"])
def test_review_spawn_ultracode_disable_is_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_config: None, falsey: str
) -> None:
    """Any case/spelling of a falsey value disables ultracode (regression guard)."""
    monkeypatch.setenv("MOS_REVIEW_ULTRACODE", falsey)
    capture = _RunCapture()
    monkeypatch.setattr(rev_mod.subprocess, "run", capture)

    rev_mod._spawn_claude_review(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--settings" not in capture.argv, f"{falsey!r} should disable ultracode"


def test_adjudicate_spawn_includes_fallback_from_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_config: None,
) -> None:
    capture = _RunCapture()
    monkeypatch.setattr(adj_mod.subprocess, "run", capture)

    adj_mod._spawn_claude_adjudicate(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--fallback-model" in capture.argv
    idx = capture.argv.index("--fallback-model")
    assert capture.argv[idx + 1] == "claude-sonnet-4-6[1m]"
    assert "--print" in capture.argv


def test_adjudicate_spawn_env_override_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_config: None,
) -> None:
    monkeypatch.setenv("MOS_ADJUDICATE_FALLBACK_MODEL", "claude-haiku-4-5-20251001")
    capture = _RunCapture()
    monkeypatch.setattr(adj_mod.subprocess, "run", capture)

    adj_mod._spawn_claude_adjudicate(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    idx = capture.argv.index("--fallback-model")
    assert capture.argv[idx + 1] == "claude-haiku-4-5-20251001"


def test_adjudicate_spawn_omits_when_config_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Cfg:
        fallback_model = None

    monkeypatch.setattr("minions.config.load_gru_config", lambda *_a, **_kw: _Cfg())
    monkeypatch.delenv("MOS_ADJUDICATE_FALLBACK_MODEL", raising=False)

    capture = _RunCapture()
    monkeypatch.setattr(adj_mod.subprocess, "run", capture)

    adj_mod._spawn_claude_adjudicate(workspace=tmp_path, prompt="x", timeout=1)
    assert capture.argv is not None
    assert "--fallback-model" not in capture.argv
