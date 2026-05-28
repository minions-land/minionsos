"""Backend and role health monitoring with crash-counter logic.

Crash threshold (per spec §3 / §7):
- Backend: 3 crashes within 1 h → notify author, stop auto-restart.
- Role: 3 crashes within 1 h → mark dismissed, notify author.

The crash counters are in-process (not persisted); they reset on process
restart.  The Gru loop (``minions/gru/loop.py``) calls these helpers.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from minions.config import load_gru_config
from minions.paths import project_logs_dir

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
# Structured health event log
# ---------------------------------------------------------------------------


def health_events_path(port: int) -> Path:
    return project_logs_dir(port) / "health_events.jsonl"


def append_health_event(
    *,
    port: int,
    kind: str,
    severity: str,
    message: str,
    role_name: str | None = None,
    pid: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one structured backend/role health event. Never raises."""
    event: dict[str, Any] = {
        "ts": datetime.now(tz=UTC).isoformat(),
        "port": port,
        "kind": kind,
        "severity": severity,
        "message": message,
    }
    if role_name:
        event["role_name"] = role_name
    if pid is not None:
        event["pid"] = pid
    if metadata:
        event["metadata"] = metadata
    try:
        path = health_events_path(port)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
    except Exception as exc:
        logger.warning(
            "append_health_event failed port=%d kind=%s severity=%s: %s",
            port,
            kind,
            severity,
            exc,
            exc_info=True,
        )
    return event


def read_recent_health_events(port: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent structured health events for *port*, newest last."""
    path = health_events_path(port)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


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


# ---------------------------------------------------------------------------
# Phase 1 minimal status snapshot
# ---------------------------------------------------------------------------


def project_status_snapshot(port: int, project_status: str) -> dict:
    """Return a Phase 1 status dict for one project.

    Keys: port, project_status, backend_alive, agents, queue_depth,
    pending_events, recent_health_events, recent_failures.
    Non-active projects skip the backend probe (backend_alive=None).
    Never raises; errors are captured in recent_failures.
    """
    from minions.lifecycle import eacn_client

    health_events = read_recent_health_events(port, limit=10)
    recent_health_failures = [
        str(e.get("message"))
        for e in health_events
        if str(e.get("severity", "")).lower() in {"warning", "error", "alert"} and e.get("message")
    ]

    if project_status != "active":
        return {
            "port": port,
            "project_status": project_status,
            "backend_alive": None,
            "agents": [],
            "queue_depth": 0,
            "pending_events": [],
            "recent_health_events": health_events,
            "recent_failures": [],
        }

    alive = backend_health(port)
    agents: list[dict] = []
    queue_depth = 0
    pending_events: list[dict] = []
    recent_failures: list[str] = []

    if alive:
        try:
            probe = eacn_client.probe_backend(port)
            agents = probe.get("agents", [])
            queue_depth = probe.get("queue_depth", 0)
            pending_events = probe.get("pending_events", [])
            recent_failures.extend(str(err) for err in probe.get("errors", []))
        except Exception as exc:
            recent_failures.append(str(exc))
    else:
        recent_failures.append(f"backend /health failed on port {port}")
        recent_failures.extend(recent_health_failures)

    return {
        "port": port,
        "project_status": project_status,
        "backend_alive": alive,
        "agents": agents,
        "queue_depth": queue_depth,
        "pending_events": pending_events,
        "recent_health_events": health_events,
        "recent_failures": recent_failures,
    }
