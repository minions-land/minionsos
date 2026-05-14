"""Tests for the per-Role scratchpad layered-memory mechanism."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from minions.config import GruConfig
from minions.lifecycle import role as role_mod
from minions.lifecycle.wakeup import _compute_thresholds, _estimate_tokens, _scratchpad_status

_TEST_CFG = GruConfig(model_context_window_tokens=1000)
SOFT = int(_TEST_CFG.model_context_window_tokens * _TEST_CFG.scratchpad_soft_pct)
HARD = int(_TEST_CFG.model_context_window_tokens * _TEST_CFG.scratchpad_hard_pct)
VETO = int(_TEST_CFG.model_context_window_tokens * _TEST_CFG.scratchpad_veto_pct)


def _write_tokens(path: Path, n_tokens: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (n_tokens * 4), encoding="utf-8")


def test_token_estimator() -> None:
    assert _estimate_tokens("x" * 4) == 1
    assert _estimate_tokens("x" * 400) == 100
    assert _estimate_tokens("") == 0


class TestScratchpadStatus:
    def test_missing_file_is_ok(self, tmp_path: Path) -> None:
        sp = tmp_path / "memory" / "noter.md"
        thresholds = _compute_thresholds(_TEST_CFG)
        with patch("minions.lifecycle.wakeup.project_scratchpad", return_value=sp):
            status, tokens = _scratchpad_status(37596, "noter", thresholds)
        assert status == "ok"
        assert tokens == 0

    def test_below_soft_is_ok(self, tmp_path: Path) -> None:
        sp = tmp_path / "memory" / "noter.md"
        _write_tokens(sp, SOFT - 1)
        thresholds = _compute_thresholds(_TEST_CFG)
        with patch("minions.lifecycle.wakeup.project_scratchpad", return_value=sp):
            status, _ = _scratchpad_status(37596, "noter", thresholds)
        assert status == "ok"

    def test_between_soft_and_hard_is_soft(self, tmp_path: Path) -> None:
        sp = tmp_path / "memory" / "noter.md"
        _write_tokens(sp, SOFT + 10)
        thresholds = _compute_thresholds(_TEST_CFG)
        with patch("minions.lifecycle.wakeup.project_scratchpad", return_value=sp):
            status, _ = _scratchpad_status(37596, "noter", thresholds)
        assert status == "soft"

    def test_between_hard_and_veto_is_hard(self, tmp_path: Path) -> None:
        sp = tmp_path / "memory" / "noter.md"
        _write_tokens(sp, HARD + 10)
        thresholds = _compute_thresholds(_TEST_CFG)
        with patch("minions.lifecycle.wakeup.project_scratchpad", return_value=sp):
            status, _ = _scratchpad_status(37596, "noter", thresholds)
        assert status == "hard"

    def test_above_veto_is_veto(self, tmp_path: Path) -> None:
        sp = tmp_path / "memory" / "noter.md"
        _write_tokens(sp, VETO + 10)
        thresholds = _compute_thresholds(_TEST_CFG)
        with patch("minions.lifecycle.wakeup.project_scratchpad", return_value=sp):
            status, _ = _scratchpad_status(37596, "noter", thresholds)
        assert status == "veto"


class TestScratchpadInitPrompt:
    def test_hard_status_tells_role_to_compress_first(self, tmp_path: Path) -> None:
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        msg = role_mod._format_event_message(
            [{"id": "e1"}],
            scratchpad_path=sp,
            scratchpad_status="hard",
            project_port=37596,
            role_name="noter",
        )
        assert "Compress the scratchpad in place (subagent) BEFORE" in msg
        assert "agent_id `noter`" in msg
        assert "pass `noter` explicitly" in msg

    def test_soft_status_is_gentle_hint(self, tmp_path: Path) -> None:
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        msg = role_mod._format_event_message(
            [{"id": "e1"}],
            scratchpad_path=sp,
            scratchpad_status="soft",
            project_port=37596,
            role_name="noter",
        )
        assert "When convenient, dispatch a subagent to compress." in msg

    def test_veto_compaction_message_is_maintenance_only(self, tmp_path: Path) -> None:
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        msg = role_mod._format_event_message(
            [{"type": "scratchpad_compaction_required"}],
            scratchpad_path=sp,
            scratchpad_status="veto_compact",
            project_port=37596,
            role_name="noter",
        )
        assert "maintenance wake-up only" in msg
        assert "Do not process buffered EACN work" in msg
        assert "will be redelivered after the scratchpad is below veto" in msg


class TestInvokeEphemeralScratchpad:
    def test_invoke_creates_role_state_dir_and_passes_env(self, tmp_path: Path) -> None:
        fake_proc = MagicMock()
        fake_proc.pid = 1234
        state_dir = tmp_path / "branches" / "noter" / ".minionsos"
        sp = state_dir / "scratchpad.md"

        with (
            patch("minions.lifecycle.role.subprocess.Popen", return_value=fake_proc) as popen,
            patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
            patch(
                "minions.lifecycle.role.project_role_log", return_value=tmp_path / "role-noter.log"
            ),
            patch("minions.lifecycle.role.project_scratchpad", return_value=sp),
        ):
            role_mod.invoke_role_ephemeral(
                "noter",
                37596,
                [{"id": "e1"}],
                extra_env={"MINIONS_SCRATCHPAD_STATUS": "soft"},
            )
        assert state_dir.is_dir()
        env = popen.call_args.kwargs["env"]
        assert env["MINIONS_SCRATCHPAD_STATUS"] == "soft"
        assert env["MINIONS_SCRATCHPAD_PATH"] == str(sp)
        cmd = popen.call_args[0][0]
        assert "--message" not in cmd
        written = b"".join(call.args[0] for call in fake_proc.stdin.write.call_args_list).decode(
            "utf-8"
        )
        assert "[Scratchpad]" in written
        assert "When convenient, dispatch a subagent to compress." in written


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
