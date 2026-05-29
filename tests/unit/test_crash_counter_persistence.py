"""Unit tests for CrashCounter disk persistence.

Pins the fix that the rolling-window crash guard survives a monitor restart
(notably the restart `mos upgrade` performs), instead of resetting to zero in
RAM and letting a crash-looping backend/role evade the >=3-in-1h threshold.
"""

from __future__ import annotations

import time
from pathlib import Path

from minions.lifecycle.health import CrashCounter


def test_backend_crashes_survive_restart(tmp_path: Path):
    """A fresh CrashCounter pointed at the same file sees prior crashes."""
    path = tmp_path / "crash_counter.json"

    c1 = CrashCounter(path=path)
    c1.record_backend_crash(37596)
    c1.record_backend_crash(37596)
    assert c1.backend_threshold_exceeded(37596) is False  # 2 < 3 default

    # Simulate a monitor restart: brand-new object, same file.
    c2 = CrashCounter(path=path)
    c2.record_backend_crash(37596)
    assert c2.backend_threshold_exceeded(37596) is True  # 3 >= 3, guard held


def test_role_crashes_survive_restart(tmp_path: Path):
    path = tmp_path / "crash_counter.json"

    c1 = CrashCounter(path=path)
    c1.record_role_crash(37596, "coder")
    c1.record_role_crash(37596, "coder")

    c2 = CrashCounter(path=path)
    c2.record_role_crash(37596, "coder")
    assert c2.role_threshold_exceeded(37596, "coder") is True
    # A different role on the same port is unaffected.
    assert c2.role_threshold_exceeded(37596, "writer") is False


def test_reset_clears_persisted_state(tmp_path: Path):
    path = tmp_path / "crash_counter.json"

    c1 = CrashCounter(path=path)
    c1.record_backend_crash(37596)
    c1.record_backend_crash(37596)
    c1.reset_backend(37596)

    c2 = CrashCounter(path=path)
    c2.record_backend_crash(37596)
    # Only the post-reset crash should count.
    assert c2.backend_threshold_exceeded(37596) is False


def test_stale_timestamps_pruned_on_load(tmp_path: Path, monkeypatch):
    """Timestamps older than the window are dropped when a new process loads."""
    path = tmp_path / "crash_counter.json"

    c1 = CrashCounter(path=path)
    # Force two crashes far in the past by rewinding the clock during record.
    base = time.time()
    monkeypatch.setattr(time, "time", lambda: base - (c1._window + 100))
    c1.record_backend_crash(37596)
    c1.record_backend_crash(37596)
    monkeypatch.undo()

    # New process at "now": the two stale crashes must not survive the load.
    c2 = CrashCounter(path=path)
    c2.record_backend_crash(37596)
    assert c2.backend_threshold_exceeded(37596) is False


def test_missing_file_is_clean_start(tmp_path: Path):
    """No persistence file means an empty counter, not a crash."""
    c = CrashCounter(path=tmp_path / "does_not_exist.json")
    assert c.backend_threshold_exceeded(1) is False
    assert c.role_threshold_exceeded(1, "coder") is False


def test_corrupt_file_does_not_raise(tmp_path: Path):
    """A garbage persistence file is ignored, not fatal."""
    path = tmp_path / "crash_counter.json"
    path.write_text("{not valid json", encoding="utf-8")
    c = CrashCounter(path=path)  # must not raise
    assert c.backend_threshold_exceeded(1) is False
