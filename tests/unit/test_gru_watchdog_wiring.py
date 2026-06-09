"""Regression tests for the Gru monitor watchdog wiring.

Pins the fix for the run()/run_async() drift: the production sidecar
(bin/gru -> python -m minions.gru.loop -> main() -> loop.run()) must start the
FULL set of enabled watchdog threads, not just experiment-reconcile + _tick.
Both entrypoints delegate to _start_watchdog_threads(), so they cannot diverge.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from minions.gru.loop import GruLoop
from minions.state.store import ProjectEntry, RoleEntry

# Every watchdog thread name _start_watchdog_threads may spawn when all
# feature flags are enabled. experiment-scheduler and role-evolution are
# unconditional; the rest are gated on their *_enabled config flags.
ALL_WATCHDOG_NAMES = {
    "experiment-scheduler",
    "role-evolution",
    "gru-drive",
    "wedge-watchdog",
    "gru-digest",
    "stagnation-vote",
    "parked-prompt",
}


def _enable_all(loop: GruLoop) -> None:
    loop.gru_drive_enabled = True
    loop.wedge_watchdog_enabled = True
    loop.gru_digest_enabled = True
    loop.stagnation_vote_enabled = True
    loop.parked_prompt_enabled = True


def test_start_watchdog_threads_spawns_full_set_when_enabled():
    """With every flag on, all 7 supervisors must be launched as daemon threads."""
    loop = GruLoop(heartbeat_interval=1)
    _enable_all(loop)

    started: list[threading.Thread] = []
    real_start = threading.Thread.start

    def _record_start(self: threading.Thread) -> None:
        started.append(self)
        # Do NOT actually run the watchdog loops in the test.

    with patch.object(threading.Thread, "start", _record_start):
        loop._start_watchdog_threads()

    names = {t.name for t in started}
    assert names == ALL_WATCHDOG_NAMES
    assert all(t.daemon for t in started)
    # Silence "thread never started" warnings — these were never really started.
    del real_start


def test_start_watchdog_threads_respects_disabled_flags():
    """Disabled watchdogs must not spawn; the two unconditional ones always do."""
    loop = GruLoop(heartbeat_interval=1)
    loop.gru_drive_enabled = False
    loop.wedge_watchdog_enabled = False
    loop.gru_digest_enabled = False
    loop.stagnation_vote_enabled = False
    loop.parked_prompt_enabled = False

    started: list[threading.Thread] = []
    with patch.object(threading.Thread, "start", lambda self: started.append(self)):
        loop._start_watchdog_threads()

    names = {t.name for t in started}
    assert names == {"experiment-scheduler", "role-evolution"}


def test_run_delegates_to_start_watchdog_threads():
    """The synchronous run() path must start the watchdog set before ticking."""
    loop = GruLoop(heartbeat_interval=1)

    calls: list[str] = []

    def _fake_start() -> None:
        calls.append("watchdogs")
        loop._stopped = True  # exit the heartbeat loop immediately

    with (
        patch.object(loop, "_start_watchdog_threads", _fake_start),
        patch.object(loop, "_tick"),
    ):
        loop.run()

    assert calls == ["watchdogs"]


def test_parked_prompt_watchdog_kicks_sleeping_role_at_prompt(monkeypatch):
    """A sleeping role with a live tmux session and stale heartbeat still needs recovery."""
    loop = GruLoop(heartbeat_interval=1)
    loop.parked_prompt_min_age = 90
    project = ProjectEntry(
        port=37597,
        real_name="Regression",
        status="active",
        created="2026-06-09T00:00:00+00:00",
        active_roles=[RoleEntry(name="expert-mathematician", state="sleeping")],
    )
    monkeypatch.setattr(
        loop._store,
        "list_projects",
        lambda filter=None: [project],
    )
    monkeypatch.setattr(loop, "_heartbeat_age_seconds", lambda port, role: 3600)

    @dataclass(frozen=True)
    class _Signal:
        parked: bool
        snapshot_lines: int = 8

    kicked: list[str] = []
    health_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.session_alive",
        lambda port, role: True,
    )
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.session_name",
        lambda port, role: f"mos-{port}-{role}",
    )
    monkeypatch.setattr(
        "minions.lifecycle.parked_prompt.detect_parked_pane",
        lambda session: _Signal(parked=True),
    )
    monkeypatch.setattr(
        "minions.lifecycle.parked_prompt.kick_pane",
        lambda session: kicked.append(session) or True,
    )
    monkeypatch.setattr(
        loop,
        "_emit_health_event",
        lambda **event: health_events.append(event),
    )

    loop._sweep_parked_roles()

    assert kicked == ["mos-37597-expert-mathematician"]
    assert health_events[0]["kind"] == "parked_prompt_recovered"
    assert "input prompt" in str(health_events[0]["message"])
    assert "hb_age=3600s" in str(health_events[0]["message"])


def test_parked_prompt_watchdog_ignores_dismissed_role(monkeypatch):
    """Dismissed roles are not resident event-loop workers and must not be kicked."""
    loop = GruLoop(heartbeat_interval=1)
    project = ProjectEntry(
        port=37597,
        real_name="Regression",
        status="active",
        created="2026-06-09T00:00:00+00:00",
        active_roles=[RoleEntry(name="old-expert", state="dismissed")],
    )
    monkeypatch.setattr(loop._store, "list_projects", lambda filter=None: [project])
    monkeypatch.setattr(loop, "_heartbeat_age_seconds", lambda port, role: 3600)

    kicked: list[str] = []
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.session_alive",
        lambda port, role: True,
    )
    monkeypatch.setattr(
        "minions.lifecycle.role_launcher.session_name",
        lambda port, role: f"mos-{port}-{role}",
    )
    monkeypatch.setattr(
        "minions.lifecycle.parked_prompt.detect_parked_pane",
        lambda session: pytest.fail("dismissed roles should not be probed"),
    )
    monkeypatch.setattr(
        "minions.lifecycle.parked_prompt.kick_pane",
        lambda session: kicked.append(session) or True,
    )

    loop._sweep_parked_roles()

    assert kicked == []


@pytest.mark.forked
def test_main_uses_run_not_run_async(monkeypatch):
    """Production main() must drive the complete run() path (all watchdogs),
    not the partial run_async() path."""
    # Force clean import of loop module
    import sys

    if "minions.gru.loop" in sys.modules:
        del sys.modules["minions.gru.loop"]
    if "minions.gru" in sys.modules:
        del sys.modules["minions.gru"]

    from unittest.mock import Mock

    from minions.gru import loop as loop_mod

    called: dict[str, bool] = {"run": False, "run_async": False}

    # Create a mock GruLoop that tracks which method was called
    mock_loop = Mock(spec=GruLoop)

    def _fake_run() -> None:
        called["run"] = True

    async def _fake_run_async() -> None:  # pragma: no cover - must not run
        called["run_async"] = True

    def _fake_stop() -> None:
        pass

    mock_loop.run = _fake_run
    mock_loop.run_async = _fake_run_async
    mock_loop.stop = _fake_stop

    # Mock GruLoop constructor to return our mock
    monkeypatch.setattr(loop_mod, "GruLoop", lambda **kwargs: mock_loop)

    # main() does `import signal` and registers handlers; neutralize the
    # registration so the test does not mutate real process signal state.
    import signal as _signal

    monkeypatch.setattr(_signal, "signal", lambda *a, **k: None)

    loop_mod.main()

    assert called["run"] is True
    assert called["run_async"] is False
