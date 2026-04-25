"""Backend and role health monitoring with crash-counter logic.

Crash threshold (per spec §3 / §7):
- Backend: 3 crashes within 1 h → notify author, stop auto-restart.
- Role: 3 crashes within 1 h → mark dismissed, notify author.

The crash counters are in-process (not persisted); they reset on process
restart.  The Gru loop (``minions/gru/loop.py``) calls these helpers.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

import httpx

from minions.config import load_gru_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


def backend_health(port: int, timeout: float = 3.0) -> bool:
    """Return True if the EACN3 backend on *port* responds 200 to ``/health``."""
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Crash counter
# ---------------------------------------------------------------------------


@dataclass
class _CrashRecord:
    timestamps: list[float] = field(default_factory=list)


class CrashCounter:
    """Rolling-window crash counter for backends and roles.

    Usage::

        counter = CrashCounter()
        counter.record_crash("backend", port=37596)
        if counter.threshold_exceeded("backend", port=37596):
            # notify author
    """

    def __init__(self) -> None:
        cfg = load_gru_config()
        self._window: float = float(cfg.crash_window_seconds)
        self._backend_threshold: int = cfg.backend_crash_threshold
        self._role_threshold: int = cfg.role_crash_threshold
        self._backend_crashes: dict[int, _CrashRecord] = defaultdict(_CrashRecord)
        self._role_crashes: dict[tuple[int, str], _CrashRecord] = defaultdict(_CrashRecord)

    def _prune(self, record: _CrashRecord) -> None:
        cutoff = time.monotonic() - self._window
        record.timestamps = [t for t in record.timestamps if t >= cutoff]

    def record_backend_crash(self, port: int) -> None:
        """Record a backend crash for *port*."""
        record = self._backend_crashes[port]
        record.timestamps.append(time.monotonic())
        self._prune(record)
        logger.warning(
            "Backend crash recorded: port=%d count_in_window=%d",
            port,
            len(record.timestamps),
        )

    def backend_threshold_exceeded(self, port: int) -> bool:
        """Return True if the backend crash threshold has been exceeded for *port*."""
        record = self._backend_crashes[port]
        self._prune(record)
        return len(record.timestamps) >= self._backend_threshold

    def record_role_crash(self, port: int, role_name: str) -> None:
        """Record a role crash for (*port*, *role_name*)."""
        key = (port, role_name)
        record = self._role_crashes[key]
        record.timestamps.append(time.monotonic())
        self._prune(record)
        logger.warning(
            "Role crash recorded: port=%d role=%r count_in_window=%d",
            port,
            role_name,
            len(record.timestamps),
        )

    def role_threshold_exceeded(self, port: int, role_name: str) -> bool:
        """Return True if the role crash threshold has been exceeded."""
        key = (port, role_name)
        record = self._role_crashes[key]
        self._prune(record)
        return len(record.timestamps) >= self._role_threshold

    def reset_backend(self, port: int) -> None:
        """Reset crash counter for *port* (e.g. after successful restart)."""
        self._backend_crashes[port] = _CrashRecord()

    def reset_role(self, port: int, role_name: str) -> None:
        """Reset crash counter for (*port*, *role_name*)."""
        self._role_crashes[(port, role_name)] = _CrashRecord()


# Module-level singleton for use by the Gru loop.
_default_counter: CrashCounter | None = None


def get_crash_counter() -> CrashCounter:
    """Return the module-level ``CrashCounter`` singleton."""
    global _default_counter
    if _default_counter is None:
        _default_counter = CrashCounter()
    return _default_counter
