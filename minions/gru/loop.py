"""Gru heartbeat / health monitor loop.

Can run in two modes:
1. As a daemon thread inside Gru's agent-host session (via ``gru_start_monitor()``
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
import os
import time
from datetime import UTC, datetime
from typing import Any

from minions.config import load_gru_config, pin_effective_agent_host
from minions.lifecycle.health import CrashCounter, append_health_event, backend_health
from minions.logging_setup import configure_logging
from minions.state.store import StateStore

configure_logging()
logger = logging.getLogger(__name__)

DEBUG_MODE: bool = bool(os.environ.get("MINIONS_DEBUG", "").strip())

# ---------------------------------------------------------------------------
# GruLoop
# ---------------------------------------------------------------------------


class GruLoop:
    """Heartbeat loop that monitors project backends and role health."""

    def __init__(self, heartbeat_interval: int | None = None) -> None:
        self.agent_host = pin_effective_agent_host()
        cfg = load_gru_config()
        self.interval: int = heartbeat_interval or cfg.heartbeat_interval_seconds
        self.experiment_reconcile_interval: int = cfg.experiment_reconcile_interval_seconds
        self._gru_agent_id: str = cfg.gru_eacn_agent_id
        self._gru_inbox_wakeup_cooldown_seconds: int = max(5, cfg.role_cooldown_seconds)
        self._store = StateStore()
        self._crash_counter = CrashCounter()
        self._last_report_ts: float = 0.0
        self._last_gru_inbox_wakeup_ts: dict[int, float] = {}
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

        def _experiment_scheduler_thread() -> None:
            while not self._stopped:
                self._reconcile_experiment_queues()
                for _ in range(max(1, self.experiment_reconcile_interval) * 2):
                    if self._stopped:
                        break
                    time.sleep(0.5)

        t = threading.Thread(target=_wakeup_thread, daemon=True, name="wakeup-scheduler")
        t.start()
        exp_t = threading.Thread(
            target=_experiment_scheduler_thread,
            daemon=True,
            name="experiment-scheduler",
        )
        exp_t.start()
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
        experiment_task = asyncio.create_task(self._experiment_reconcile_async())
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
            experiment_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await wakeup_task
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await experiment_task

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """One monitoring cycle."""
        # Reap any exited ephemeral role subprocesses so their log file
        # handles are closed and their PIDs in projects.json are cleared
        # before we run the liveness check below.
        try:
            from minions.lifecycle.role import reap_finished

            reap_finished(store=self._store)
        except Exception as exc:
            logger.debug("reap_finished failed: %s", exc)

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
                    self._emit_health_event(
                        port=port,
                        kind="backend_unhealthy",
                        severity="alert",
                        message=msg,
                        metadata={"project_name": project.real_name},
                    )
                    logger.error(msg)
                    events.append(msg)
                else:
                    msg = f"[WARN] Backend on port {port} ({project.real_name}) is unhealthy."
                    self._emit_health_event(
                        port=port,
                        kind="backend_unhealthy",
                        severity="warning",
                        message=msg,
                        metadata={"project_name": project.real_name},
                    )
                    logger.warning(msg)
                    events.append(msg)
            else:
                # Reset crash counter on successful health check.
                self._crash_counter.reset_backend(port)
                try:
                    from minions.lifecycle.project import project_repair_eacn_agents

                    project_repair_eacn_agents(port, store=self._store)
                    project = self._store.get_project(port) or project
                except Exception as exc:
                    logger.debug("Project EACN repair skipped port=%d: %s", port, exc)
                polled = self._poll_gru_inbox(port)
                woke_gru = self._maybe_invoke_gru_for_unread(port, now)
                if polled or woke_gru:
                    msg = (
                        f"[INFO] Gru inbox on port {port} ({project.real_name}) "
                        f"polled={polled} woke_gru={woke_gru}."
                    )
                    logger.info(msg)
                    events.append(msg)

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
                        self._emit_health_event(
                            port=port,
                            kind="role_crash",
                            severity="alert",
                            message=msg,
                            role_name=role.name,
                            pid=role.pid,
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
                        self._emit_health_event(
                            port=port,
                            kind="role_crash",
                            severity="warning",
                            message=msg,
                            role_name=role.name,
                            pid=role.pid,
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

    def _poll_gru_inbox(self, port: int) -> int:
        """Drain project-local EACN events for the Gru queue into the journal."""
        try:
            from minions.lifecycle import eacn_client, gru_inbox

            payload = eacn_client.poll_events(
                port,
                self._gru_agent_id,
                timeout_secs=0,
                http_timeout=5.0,
            )
            events = payload.get("events") or payload.get("messages") or []
            if not isinstance(events, list):
                return 0
            return gru_inbox.append_events(port, [e for e in events if isinstance(e, dict)])
        except Exception as exc:
            logger.debug(
                "Gru inbox poll failed port=%d agent=%s: %s",
                port,
                self._gru_agent_id,
                exc,
            )
            return 0

    def _maybe_invoke_gru_for_unread(self, port: int, now: float) -> bool:
        """Wake Gru when its EACN journal has pending entries.

        The monitor never marks entries read. The invoked Gru session must call
        ``gru_inbox_poll(mark_read=false)``, handle the returned entries, then
        ``gru_inbox_poll(mark_read=true)``.
        """
        try:
            from minions.lifecycle import gru_inbox

            entries = gru_inbox.read_unread(port, max_events=25)
            unread = gru_inbox.unread_count(port)
        except Exception as exc:
            logger.debug("Gru inbox unread check failed port=%d: %s", port, exc)
            return False
        if not entries:
            return False

        last = self._last_gru_inbox_wakeup_ts.get(port)
        if last is not None and now - last < self._gru_inbox_wakeup_cooldown_seconds:
            return False

        try:
            from minions.lifecycle.role import invoke_role_ephemeral, is_inflight

            if is_inflight(port, "gru"):
                return False
            max_seq = max(int(entry.get("seq", 0)) for entry in entries)
            event: dict[str, Any] = {
                "type": "gru_inbox_unread",
                "id": f"gru-inbox:{port}:{max_seq}",
                "payload": {
                    "port": port,
                    "unread_count": unread,
                    "shown_entries": entries,
                    "instruction": (
                        "Handle Gru's project-local EACN queue via "
                        "gru_inbox_poll(mark_read=false), then mark handled "
                        "entries with gru_inbox_poll(mark_read=true)."
                    ),
                },
            }
            result = invoke_role_ephemeral(
                "gru",
                port,
                [event],
                extra_env={"MINIONS_WAKEUP_CLASS": "event"},
                store=self._store,
            )
        except Exception as exc:
            logger.debug("Gru inbox wakeup failed port=%d: %s", port, exc)
            return False

        if isinstance(result, dict) and result.get("deferred"):
            return False
        self._last_gru_inbox_wakeup_ts[port] = now
        return True

    async def _experiment_reconcile_async(self) -> None:
        while not self._stopped:
            self._reconcile_experiment_queues()
            await asyncio.sleep(max(1, self.experiment_reconcile_interval))

    def _reconcile_experiment_queues(self) -> None:
        """Run Python-side Experimenter queue scheduling for active projects."""
        try:
            from minions.tools.experiment_scheduler import ExperimentScheduler, default_db_path
        except Exception as exc:
            logger.debug("Experiment scheduler import failed: %s", exc)
            return
        for project in self._store.list_projects(filter="active"):
            db_path = default_db_path(project.port)
            if not db_path.exists():
                continue
            try:
                result = ExperimentScheduler(project_port=project.port).reconcile()
                launched = len(result.get("launched") or [])
                completed = len(result.get("completed") or [])
                failed = len(result.get("failed") or [])
                if launched or completed or failed:
                    logger.info(
                        "Experiment queue reconcile port=%d launched=%d completed=%d failed=%d",
                        project.port,
                        launched,
                        completed,
                        failed,
                    )
            except Exception as exc:
                logger.debug("Experiment queue reconcile skipped port=%d: %s", project.port, exc)

    def _emit_health_event(
        self,
        *,
        port: int,
        kind: str,
        severity: str,
        message: str,
        role_name: str | None = None,
        pid: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        event = append_health_event(
            port=port,
            kind=kind,
            severity=severity,
            message=message,
            role_name=role_name,
            pid=pid,
            metadata=metadata,
        )
        try:
            cfg = load_gru_config()
        except Exception:
            return
        if not cfg.health_event_eacn_notifications:
            return
        try:
            from minions.lifecycle import eacn_client

            for target in ("gru", "noter"):
                try:
                    eacn_client.send_message(
                        port=port,
                        to_agent_id=target,
                        from_agent_id="health-monitor",
                        content={"type": "health_event", **event},
                        timeout=1.0,
                        audit_to_noter=False,
                    )
                except Exception as exc:
                    logger.debug(
                        "health event EACN notify failed port=%d target=%s: %s",
                        port,
                        target,
                        exc,
                    )
        except Exception as exc:
            logger.debug("health event EACN notify setup failed port=%d: %s", port, exc)


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
