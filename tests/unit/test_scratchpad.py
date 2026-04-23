"""Tests for the per-Role scratchpad layered-memory mechanism."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from minions.config import GruConfig
from minions.lifecycle import role as role_mod
from minions.lifecycle import wakeup as wakeup_mod
from minions.lifecycle.wakeup import (
    WakeupScheduler,
    _estimate_tokens,
)

# Small-window config used across tests; with the default percentages this
# yields soft=100 / hard=150 / veto=200 token thresholds — easy to exercise
# without writing megabytes to tmp_path.
_TEST_CFG = GruConfig(model_context_window_tokens=1000)
SOFT = int(_TEST_CFG.model_context_window_tokens * _TEST_CFG.scratchpad_soft_pct)
HARD = int(_TEST_CFG.model_context_window_tokens * _TEST_CFG.scratchpad_hard_pct)
VETO = int(_TEST_CFG.model_context_window_tokens * _TEST_CFG.scratchpad_veto_pct)


@dataclass
class FakeRole:
    name: str
    state: str = "active"
    poll_interval: str = "1m"


@dataclass
class FakeProject:
    port: int
    active_roles: list[FakeRole] = field(default_factory=list)


class FakeStore:
    def __init__(self, projects: list[FakeProject]) -> None:
        self._projects = projects

    def list_projects(self, filter: str = "active") -> list[FakeProject]:
        return list(self._projects)


def _run(coro):
    return asyncio.run(coro)


def _write_tokens(path: Path, n_tokens: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (n_tokens * 4), encoding="utf-8")


def test_token_estimator() -> None:
    assert _estimate_tokens("x" * 4) == 1
    assert _estimate_tokens("x" * 400) == 100
    assert _estimate_tokens("") == 0


def _patch_paths(tmp_path: Path):
    """Patch project_scratchpad/project_memory_dir inside wakeup to tmp."""

    def _sp(port: int, role: str) -> Path:
        return tmp_path / f"project_{port}" / "memory" / f"{role}.md"

    def _md(port: int) -> Path:
        return tmp_path / f"project_{port}" / "memory"

    return (
        patch.object(wakeup_mod, "project_scratchpad", side_effect=_sp),
        patch.object(wakeup_mod, "project_memory_dir", side_effect=_md),
    )


class TestWakeupScratchpad:
    def _make(self, tmp_path: Path):
        project = FakeProject(port=37596, active_roles=[FakeRole("noter")])
        store = FakeStore([project])
        calls: list[tuple[str, int, list[dict], dict]] = []

        def invoke(role, port, events, **kwargs):
            calls.append((role, port, events, kwargs))

        sched = WakeupScheduler(store=store, invoke_fn=invoke, config=_TEST_CFG)
        return sched, calls

    def test_below_soft_dispatches_ok(self, tmp_path: Path) -> None:
        sched, calls = self._make(tmp_path)
        p1, p2 = _patch_paths(tmp_path)
        payload = {"events": [{"id": "e1"}]}
        with p1, p2, patch.object(wakeup_mod, "poll_events", return_value=payload):
            _run(sched.tick_once())
        assert len(calls) == 1
        assert calls[0][3]["extra_env"]["MINIONS_SCRATCHPAD_STATUS"] == "ok"

    def test_between_soft_and_hard_dispatches_soft(self, tmp_path: Path) -> None:
        sched, calls = self._make(tmp_path)
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        _write_tokens(sp, SOFT + 10)
        p1, p2 = _patch_paths(tmp_path)
        payload = {"events": [{"id": "e1"}]}
        with p1, p2, patch.object(wakeup_mod, "poll_events", return_value=payload):
            _run(sched.tick_once())
        assert calls[0][3]["extra_env"]["MINIONS_SCRATCHPAD_STATUS"] == "soft"

    def test_between_hard_and_veto_dispatches_hard_and_message(self, tmp_path: Path) -> None:
        sched, calls = self._make(tmp_path)
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        _write_tokens(sp, HARD + 10)
        p1, p2 = _patch_paths(tmp_path)
        payload = {"events": [{"id": "e1"}]}
        with p1, p2, patch.object(wakeup_mod, "poll_events", return_value=payload):
            _run(sched.tick_once())
        assert calls[0][3]["extra_env"]["MINIONS_SCRATCHPAD_STATUS"] == "hard"
        # And check that the init message reflects the hard directive.
        msg = role_mod._format_event_message(
            [{"id": "e1"}],
            scratchpad_path=sp,
            scratchpad_status="hard",
            project_port=37596,
            role_name="noter",
        )
        assert "Compress the scratchpad in place (subagent) BEFORE" in msg

    def test_above_veto_no_dispatch_and_dedup_warning(self, tmp_path: Path) -> None:
        sched, calls = self._make(tmp_path)
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        _write_tokens(sp, VETO + 10)
        p1, p2 = _patch_paths(tmp_path)
        payload = {"events": [{"id": "e1"}]}
        posted: list[Any] = []

        def fake_post(port, to_agent_id, from_agent_id, content, **_):
            posted.append((port, to_agent_id, content))
            return {}

        with (
            p1,
            p2,
            patch.object(wakeup_mod, "poll_events", return_value=payload),
            patch.object(wakeup_mod, "post_message", side_effect=fake_post),
        ):
            _run(sched.tick_once())
            # Second tick — same over-veto state — must NOT re-post.
            sched._last_poll_ts.clear()
            _run(sched.tick_once())

        assert calls == []
        assert len(posted) == 1
        assert "exceeds" in posted[0][2]

    def test_dedup_resets_when_file_drops_below_veto(self, tmp_path: Path) -> None:
        sched, calls = self._make(tmp_path)
        sp = tmp_path / "project_37596" / "memory" / "noter.md"
        _write_tokens(sp, VETO + 10)
        p1, p2 = _patch_paths(tmp_path)
        payload = {"events": [{"id": "e1"}]}
        posted: list[Any] = []

        with (
            p1,
            p2,
            patch.object(wakeup_mod, "poll_events", return_value=payload),
            patch.object(
                wakeup_mod,
                "post_message",
                side_effect=lambda *a, **k: posted.append(k.get("content") or a[-1]),
            ),
        ):
            _run(sched.tick_once())
            # Shrink scratchpad below veto — one more dispatch, warning flag reset.
            _write_tokens(sp, 100)
            sched._last_poll_ts.clear()
            _run(sched.tick_once())
            # Grow again — should re-warn (fresh warning, not deduped).
            _write_tokens(sp, VETO + 10)
            sched._last_poll_ts.clear()
            # Re-deliver events: they were removed from dedup on veto, but now
            # already processed on the "ok" tick above, so push a new event.
            payload2 = {"events": [{"id": "e2"}]}
            with patch.object(wakeup_mod, "poll_events", return_value=payload2):
                _run(sched.tick_once())

        assert len(posted) == 2

    def test_memory_dir_auto_created(self, tmp_path: Path) -> None:
        sched, calls = self._make(tmp_path)
        p1, p2 = _patch_paths(tmp_path)
        payload = {"events": [{"id": "e1"}]}
        with p1, p2, patch.object(wakeup_mod, "poll_events", return_value=payload):
            _run(sched.tick_once())
        assert (tmp_path / "project_37596" / "memory").is_dir()


class TestInvokeEphemeralScratchpad:
    def test_invoke_creates_memory_dir_and_passes_env(self, tmp_path: Path) -> None:
        fake_proc = MagicMock()
        fake_proc.pid = 1234
        mem_dir = tmp_path / "memory"
        sp = mem_dir / "noter.md"

        with (
            patch("minions.lifecycle.role.subprocess.Popen", return_value=fake_proc) as popen,
            patch("minions.lifecycle.role.project_workspace", return_value=tmp_path),
            patch(
                "minions.lifecycle.role.project_role_log", return_value=tmp_path / "role-noter.log"
            ),
            patch("minions.lifecycle.role.project_memory_dir", return_value=mem_dir),
            patch("minions.lifecycle.role.project_scratchpad", return_value=sp),
        ):
            role_mod.invoke_role_ephemeral(
                "noter",
                37596,
                [{"id": "e1"}],
                extra_env={"MINIONS_SCRATCHPAD_STATUS": "soft"},
            )
        assert mem_dir.is_dir()
        env = popen.call_args.kwargs["env"]
        assert env["MINIONS_SCRATCHPAD_STATUS"] == "soft"
        assert env["MINIONS_SCRATCHPAD_PATH"] == str(sp)
        cmd = popen.call_args[0][0]
        msg_idx = cmd.index("--message") + 1
        assert "[Scratchpad]" in cmd[msg_idx]
        assert "When convenient, dispatch a subagent to compress." in cmd[msg_idx]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
