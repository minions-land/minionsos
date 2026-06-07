"""Regression tests for the Gru monitor watchdog wiring.

Pins the fix for the run()/run_async() drift: the production sidecar
(bin/gru -> python -m minions.gru.loop -> main() -> loop.run()) must start the
FULL set of enabled watchdog threads, not just experiment-reconcile + _tick.
Both entrypoints delegate to _start_watchdog_threads(), so they cannot diverge.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from minions.gru.loop import GruLoop

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
