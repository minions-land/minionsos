"""Unit tests for the empty-upstream / bare-`ack` wedge detector (Issue #15)."""

from __future__ import annotations

from pathlib import Path

from minions.lifecycle.wedge_detect import inspect_log_tail, is_wedged


def test_missing_log_returns_zero_signal(tmp_path: Path) -> None:
    missing = tmp_path / "role-coder.log"
    sig = inspect_log_tail(missing)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert sig.sampled_lines == 0
    assert sig.log_path == missing
    assert not is_wedged(sig, threshold=4)


def test_clean_log_is_not_wedged(tmp_path: Path) -> None:
    log = tmp_path / "role-coder.log"
    log.write_text(
        "  Called minionsos (ctrl+o to expand)\n"
        "● Reading 1 file…\n"
        "● Done. Writing summary.\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert not is_wedged(sig, threshold=4)


def test_pure_keepalive_ack_loop_is_not_wedged(tmp_path: Path) -> None:
    """A long quiet ack loop without any empty-upstream marker is
    consistent with a healthy cache-keepalive cadence on a quiet project,
    and the watchdog must NOT kill it.
    """
    log = tmp_path / "role-ethics.log"
    log.write_text(
        "\n".join(["● ack"] * 20) + "\n"
    )
    sig = inspect_log_tail(log)
    assert sig.ack_line_count == 20
    assert sig.empty_marker_count == 0
    assert not is_wedged(sig, threshold=4)


def test_wedge_signature_is_detected(tmp_path: Path) -> None:
    log = tmp_path / "role-coder.log"
    log.write_text(
        "  Called minionsos (ctrl+o to expand)\n\n"
        "● ack\n\n"
        "  Called minionsos (ctrl+o to expand)\n\n"
        "●  ack\n\n"
        "  Called minionsos (ctrl+o to expand)\n\n"
        "● [upstream returned no content]\n\n"
        "● [upstream returned no content]\n\n"
        "● [upstream returned no content]\n\n"
        "● [upstream returned no content]\n\n"
        "✻ Brewed for 35m 26s\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 4
    assert sig.ack_line_count == 2
    assert is_wedged(sig, threshold=4)


def test_ack_threshold_with_one_empty_marker_is_wedge(tmp_path: Path) -> None:
    log = tmp_path / "role-x.log"
    log.write_text(
        "● [upstream returned no content]\n"
        + "\n".join(["● ack"] * 6)
        + "\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 1
    assert sig.ack_line_count == 6
    assert is_wedged(sig, threshold=4)


def test_ansi_escapes_do_not_hide_signature(tmp_path: Path) -> None:
    log = tmp_path / "role-y.log"
    log.write_bytes(
        b"\x1b[1m\xe2\x97\x8f\x1b[0m \x1b[2m[upstream returned no content]\x1b[0m\n"
        * 4
        + b"\x1b[1m\xe2\x97\x8f\x1b[0m ack\n"
    )
    sig = inspect_log_tail(log)
    assert sig.empty_marker_count == 4
    assert sig.ack_line_count == 1
    assert is_wedged(sig, threshold=4)


def test_tail_bytes_bounds_the_read(tmp_path: Path) -> None:
    """Old wedge patterns far back in the log must not trigger; only the
    recent tail counts."""
    log = tmp_path / "role-z.log"
    ancient_wedge = (
        "● [upstream returned no content]\n● ack\n" * 50
    )
    recent_healthy = "● Reading 1 file…\n● Writing changes…\n" * 50
    log.write_text(ancient_wedge + recent_healthy)
    sig = inspect_log_tail(log, tail_bytes=1024)
    assert sig.empty_marker_count == 0
    assert sig.ack_line_count == 0
    assert not is_wedged(sig, threshold=4)
