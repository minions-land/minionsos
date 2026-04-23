"""Gru heartbeat / health monitor loop.

Can run in two modes:
1. As a daemon thread inside Gru's Claude session (via ``gru_start_monitor()``
   MCP tool).
2. As a standalone process: ``uv run python -m minions.gru.loop``.

The loop:
- Periodically scans active projects.
- Probes each backend via ``/health``.
- Records crashes and checks thresholds.
- Logs a digest if anything changed since the last report.
- Stays silent if nothing noteworthy happened (low-freq D behaviour per spec §7).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime

from minions.config import load_gru_config
from minions.lifecycle.health import CrashCounter, backend_health
from minions.logging_setup import configure_logging
from minions.state.store import StateStore

configure_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GruLoop
# ---------------------------------------------------------------------------


class GruLoop:
    """Heartbeat loop that monitors project backends and role health."""

    def __init__(self, heartbeat_interval: int | None = None) -> None:
        cfg = load_gru_config()
        self.interval: int = heartbeat_interval or cfg.heartbeat_interval_seconds
        self._store = StateStore()
        self._crash_counter = CrashCounter()
        self._last_report_ts: float = 0.0
        self._stopped = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the loop to stop after the current iteration."""
        self._stopped = True

    def run(self) -> None:
        """Run the monitor loop synchronously (blocking).

        Suitable for use in a daemon thread or as ``__main__``. A
        :class:`WakeupScheduler` is started in a sibling daemon thread
        running its own asyncio loop so role event-dispatch proceeds in
        parallel with Gru's heartbeat.
        """
        import threading

        from minions.lifecycle.wakeup import WakeupScheduler

        wakeup = WakeupScheduler(store=self._store)

        def _wakeup_thread() -> None:
            asyncio.run(wakeup.run_async())

        t = threading.Thread(target=_wakeup_thread, daemon=True, name="wakeup-scheduler")
        t.start()
        logger.info("Gru monitor loop started (interval=%ds).", self.interval)
        try:
            while not self._stopped:
                try:
                    self._tick()
                except Exception as exc:
                    logger.error("Gru monitor tick error: %s", exc, exc_info=True)
                for _ in range(self.interval * 2):
                    if self._stopped:
                        break
                    time.sleep(0.5)
        finally:
            wakeup.stop()
        logger.info("Gru monitor loop stopped.")

    async def run_async(self) -> None:
        """Async variant for use inside an existing asyncio event loop.

        Also drives :class:`minions.lifecycle.wakeup.WakeupScheduler` in the
        same event loop, so role event-dispatch runs at the Python layer
        alongside Gru's own heartbeat.
        """
        from minions.lifecycle.wakeup import WakeupScheduler

        wakeup = WakeupScheduler(store=self._store)
        logger.info("Gru monitor async loop started (interval=%ds).", self.interval)
        wakeup_task = asyncio.create_task(wakeup.run_async())
        try:
            while not self._stopped:
                try:
                    self._tick()
                except Exception as exc:
                    logger.error("Gru monitor tick error: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval)
        finally:
            wakeup.stop()
            wakeup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await wakeup_task

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """One monitoring cycle."""
        now = time.monotonic()
        projects = self._store.list_projects(filter="active")

        events: list[str] = []

        for project in projects:
            port = project.port
            healthy = backend_health(port)

            if not healthy:
                self._crash_counter.record_backend_crash(port)
                if self._crash_counter.backend_threshold_exceeded(port):
                    msg = (
                        f"[ALERT] Backend on port {port} ({project.real_name}) has crashed "
                        f"≥3 times in 1h. Auto-restart disabled. Manual intervention required."
                    )
                    logger.error(msg)
                    events.append(msg)
                else:
                    msg = f"[WARN] Backend on port {port} ({project.real_name}) is unhealthy."
                    logger.warning(msg)
                    events.append(msg)
            else:
                # Reset crash counter on successful health check.
                self._crash_counter.reset_backend(port)

            # Check role processes.
            for role in project.active_roles:
                if role.state != "active" or role.pid is None:
                    continue
                if not _pid_alive(role.pid):
                    self._crash_counter.record_role_crash(port, role.name)
                    if self._crash_counter.role_threshold_exceeded(port, role.name):
                        msg = (
                            f"[ALERT] Role {role.name!r} on port {port} has crashed "
                            f"≥3 times in 1h. Marking dismissed."
                        )
                        logger.error(msg)
                        events.append(msg)
                        try:
                            self._store.upsert_role(
                                port,
                                role.model_copy(update={"state": "dismissed", "pid": None}),
                            )
                        except Exception as exc:
                            logger.error("Failed to mark role dismissed: %s", exc)
                    else:
                        msg = (
                            f"[WARN] Role {role.name!r} on port {port}"
                            f" (PID {role.pid}) is not running."
                        )
                        logger.warning(msg)
                        events.append(msg)

        # Emit digest if there are events or if the heartbeat interval elapsed.
        if events or (now - self._last_report_ts >= self.interval):
            ts = datetime.now(tz=UTC).isoformat()
            if events:
                logger.info("Gru heartbeat digest [%s]: %d event(s).", ts, len(events))
                for e in events:
                    logger.info("  %s", e)
            else:
                logger.debug("Gru heartbeat [%s]: all systems nominal.", ts)
            self._last_report_ts = now


# ---------------------------------------------------------------------------
# PID liveness helper
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    """Return True if *pid* is a running process."""
    import os

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it.
        return True


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def main() -> None:
    loop = GruLoop()
    asyncio.run(loop.run_async())


if __name__ == "__main__":
    main()
