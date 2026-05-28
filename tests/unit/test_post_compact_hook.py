"""Tests for the PostCompact hook (Issue #29 tmux-kick + journal extract)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from minions.hooks import post_compact_draft as hook


def _fake_tmux_has_session_alive(*args, **kwargs):
    """subprocess.run substitute for tmux has-session (returns 0=alive)."""
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")


def _fake_tmux_has_session_dead(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=1, stdout=b"", stderr=b"")


class TestKickOwnPane:
    """Issue #29: the post-compact hook must kick its own pane so the
    parked-at-prompt failure mode auto-recovers within ~2s."""

    def test_kick_skipped_when_session_missing(self) -> None:
        with patch.object(subprocess, "run", side_effect=_fake_tmux_has_session_dead):
            assert hook._kick_own_pane(39999, "coder") is False

    def test_kick_skipped_when_role_unknown(self) -> None:
        assert hook._kick_own_pane(39999, "unknown") is False
        assert hook._kick_own_pane(39999, "") is False

    def test_kick_spawns_background_process_when_session_alive(self) -> None:
        popen_calls: list[dict] = []

        class _StubPopen:
            def __init__(self, args, **kwargs):
                popen_calls.append({"args": args, "kwargs": kwargs})
                self.pid = 12345

        with (
            patch.object(subprocess, "run", side_effect=_fake_tmux_has_session_alive),
            patch.object(subprocess, "Popen", _StubPopen),
        ):
            assert hook._kick_own_pane(39999, "coder") is True

        assert len(popen_calls) == 1
        argv = popen_calls[0]["args"]
        # nohup bash -c '<kick cmd>'
        assert argv[0] == "nohup"
        assert argv[1] == "bash"
        assert argv[2] == "-c"
        kick_cmd = argv[3]
        # The kick must address the right session, use -l for literal paste,
        # and include both the prompt and the Enter press.
        assert "mos-39999-coder" in kick_cmd
        assert "-l" in kick_cmd
        # The injected kick is now a Claude Code /goal slash command so the
        # stopping rule persists across turns; see GH #64 + parked_prompt.py.
        assert "/goal" in kick_cmd
        assert "mos_await_events" in kick_cmd
        assert "Enter" in kick_cmd
        # Detached so the hook can return immediately.
        kwargs = popen_calls[0]["kwargs"]
        assert kwargs.get("start_new_session") is True

    def test_kick_swallows_popen_failure(self) -> None:
        """If the spawn itself fails (e.g. nohup missing), kick must not raise."""
        with (
            patch.object(subprocess, "run", side_effect=_fake_tmux_has_session_alive),
            patch.object(subprocess, "Popen", side_effect=OSError("nohup not found")),
        ):
            assert hook._kick_own_pane(39999, "coder") is False


class TestTryKickFromEnv:
    """The early-return paths in main() use _try_kick_from_env so a bad
    stdin payload or missing draft dir still wakes the parked role."""

    def test_skips_without_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINIONS_PROJECT_PORT", raising=False)
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        assert hook._try_kick_from_env() is False

    def test_skips_without_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "39999")
        monkeypatch.delenv("MINIONS_ROLE_NAME", raising=False)
        assert hook._try_kick_from_env() is False

    def test_invokes_kick_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "39999")
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        with patch.object(hook, "_kick_own_pane", return_value=True) as mock_kick:
            assert hook._try_kick_from_env() is True
        mock_kick.assert_called_once_with(39999, "coder")


class TestMainKicksOnEveryPath:
    """main() must kick the pane regardless of whether journal-extract
    succeeded — the parking happens whether or not the summary parses."""

    def test_empty_stdin_still_kicks(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "39999")
        monkeypatch.setenv("MINIONS_ROLE_NAME", "noter")
        monkeypatch.setattr("sys.stdin.read", lambda: "")
        with patch.object(hook, "_kick_own_pane", return_value=True) as mock_kick:
            hook.main()
        mock_kick.assert_called_once()

    def test_malformed_stdin_still_kicks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINIONS_PROJECT_PORT", "39999")
        monkeypatch.setenv("MINIONS_ROLE_NAME", "noter")
        monkeypatch.setattr("sys.stdin.read", lambda: "not-valid-json")
        with patch.object(hook, "_kick_own_pane", return_value=True) as mock_kick:
            hook.main()
        mock_kick.assert_called_once()

    def test_successful_extract_kicks(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The happy path: journal entry gets written AND the kick fires."""
        # Stage a fake project tree shaped the way _draft_dir resolves it
        # under the new (v15.53+) layout: projects/ sits under MINIONS_ROOT,
        # MINIONS_ROOT is the repo root (matching what gru/mos shell
        # launchers export at runtime).
        port = 41010
        repo = tmp_path / "MinionsOS"
        repo.mkdir(parents=True)
        draft_dir = repo / "projects" / f"project_{port}" / "branches" / "shared" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "draft.json").write_text(
            json.dumps({"nodes": [{"id": "H-001"}], "edges": []}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MINIONS_ROOT", str(repo))
        monkeypatch.delenv("MINIONS_PROJECTS_ROOT", raising=False)
        monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
        monkeypatch.setenv("MINIONS_ROLE_NAME", "noter")

        stdin_payload = json.dumps(
            {
                "compact_summary": (
                    "## Working_on\n- driving H-001\n\n"
                    "## Next_action\n- mos_draft_summary()\n"
                ),
                "trigger": "manual",
            }
        )
        monkeypatch.setattr("sys.stdin.read", lambda: stdin_payload)

        with patch.object(hook, "_kick_own_pane", return_value=True) as mock_kick:
            hook.main()
        mock_kick.assert_called_once_with(port, "noter")
        # Journal entry written.
        journal = draft_dir / "journal.jsonl"
        assert journal.is_file()
        entry = json.loads(journal.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["op"] == "post_compact_extract"
        assert entry["role"] == "noter"


# Smoke: kick command shape — use real shlex quoting so we catch a regression
# where a stray quote could break the bash -c invocation.
def test_kick_command_quotes_session_name_safely() -> None:
    """Even a malicious session name shouldn't break the kick (defence-
    in-depth — the session name is derived from int port + role string,
    but better to belt-and-braces the quoting)."""
    popen_calls: list[list] = []

    class _Stub:
        def __init__(self, args, **kwargs):
            popen_calls.append(args)

    with (
        patch.object(subprocess, "run", side_effect=_fake_tmux_has_session_alive),
        patch.object(subprocess, "Popen", _Stub),
    ):
        assert hook._kick_own_pane(39999, "coder") is True

    cmd = popen_calls[0][3]
    # No bare unquoted shell metachars in the session ref.
    assert "mos-39999-coder" in cmd
    # Both send-keys calls present.
    assert cmd.count("send-keys") == 2


class TestDraftDirResolution:
    """v15.53 layout migration: _draft_dir must resolve to projects/project_<port>/...

    Three resolution paths in priority order:
      1. MINIONS_PROJECTS_ROOT env var (highest)
      2. MINIONS_ROOT env var, with /projects/ appended
      3. file-location fallback (lowest)
    """

    def test_resolves_under_minions_projects_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        port = 41011
        custom_root = tmp_path / "elsewhere"
        draft_dir = custom_root / f"project_{port}" / "branches" / "shared" / "draft"
        draft_dir.mkdir(parents=True)

        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(custom_root))
        monkeypatch.delenv("MINIONS_ROOT", raising=False)

        assert hook._draft_dir(port) == draft_dir

    def test_resolves_under_minions_root_projects(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        port = 41012
        repo = tmp_path / "MinionsOS"
        draft_dir = repo / "projects" / f"project_{port}" / "branches" / "shared" / "draft"
        draft_dir.mkdir(parents=True)

        monkeypatch.delenv("MINIONS_PROJECTS_ROOT", raising=False)
        monkeypatch.setenv("MINIONS_ROOT", str(repo))

        assert hook._draft_dir(port) == draft_dir

    def test_returns_none_when_directory_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path / "empty"))
        monkeypatch.delenv("MINIONS_ROOT", raising=False)
        assert hook._draft_dir(99999) is None
