"""Gru heartbeat / health monitor loop.

Can run in two modes:
1. As a daemon thread inside Gru's agent-host session (via ``gru_start_monitor()``
   MCP tool).
2. As a standalone process: ``uv run python -m minions.gru.loop``.

The loop:
- Periodically scans active projects.
- Probes each backend via ``/health``.
- Records crashes and checks thresholds.
- Drives experiment queue reconciliation in parallel with Gru's heartbeat.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from datetime import UTC, datetime

from minions.config import load_gru_config, pin_effective_agent_host
from minions.lifecycle.health import CrashCounter, append_health_event, backend_health
from minions.logging_setup import configure_logging
from minions.paths import project_exploration_dir
from minions.state.store import StateStore

configure_logging()
logger = logging.getLogger(__name__)

DEBUG_MODE: bool = bool(os.environ.get("MINIONS_DEBUG", "").strip())


class GruLoop:
    """Heartbeat loop that monitors project backends and role health."""

    def __init__(self, heartbeat_interval: int | None = None) -> None:
        self.agent_host = pin_effective_agent_host()
        cfg = load_gru_config()
        self.interval: int = heartbeat_interval or cfg.heartbeat_interval_seconds
        self.experiment_reconcile_interval: int = cfg.experiment_reconcile_interval_seconds
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

        Suitable for use in a daemon thread or as ``__main__``. An experiment
        scheduler thread runs in parallel with Gru's heartbeat.
        """
        import threading

        def _experiment_scheduler_thread() -> None:
            while not self._stopped:
                self._reconcile_experiment_queues()
                for _ in range(max(1, self.experiment_reconcile_interval) * 2):
                    if self._stopped:
                        break
                    time.sleep(0.5)

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
            pass
        logger.info("Gru monitor loop stopped.")

    async def run_async(self) -> None:
        """Async variant for use inside an existing asyncio event loop."""
        logger.info("Gru monitor async loop started (interval=%ds).", self.interval)
        experiment_task = asyncio.create_task(self._experiment_reconcile_async())
        try:
            while not self._stopped:
                try:
                    self._tick()
                except Exception as exc:
                    logger.error("Gru monitor tick error: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval)
        finally:
            experiment_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await experiment_task

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
                self._crash_counter.reset_backend(port)
                try:
                    from minions.lifecycle.project import project_repair_eacn_agents

                    project_repair_eacn_agents(port, store=self._store)
                except Exception as exc:
                    logger.debug("Project EACN repair skipped port=%d: %s", port, exc)

            # Watchdog: each `active` role should have a live tmux session.
            # If the session has died, relaunch in place. We do NOT touch
            # roles in `dismissed` state — the operator killed those on
            # purpose. Stale `active` entries only relaunch up to the
            # crash threshold, after which we mark the role dismissed and
            # alert.
            from minions.lifecycle.role_launcher import (
                launch_role_process,
                session_alive,
            )

            for role in project.active_roles:
                if role.state != "active":
                    continue
                if session_alive(port, role.name):
                    continue
                # Session is gone. Distinguish a deliberate
                # ``mos_reset_context`` from a real crash by checking the
                # marker file the reset tool drops before killing tmux.
                marker = project_exploration_dir(port) / ".reset_markers" / role.name
                deliberate_reset = marker.exists()
                if deliberate_reset:
                    with contextlib.suppress(OSError):
                        marker.unlink()
                else:
                    self._crash_counter.record_role_crash(port, role.name)
                if not deliberate_reset and self._crash_counter.role_threshold_exceeded(
                    port, role.name
                ):
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
                    continue
                # Below crash threshold — try to respawn.
                try:
                    status = launch_role_process(role, port)
                    if deliberate_reset:
                        msg = (
                            f"[INFO] Role {role.name!r} on port {port} reset "
                            f"and respawned cold (tmux={status.get('session_name')})."
                        )
                        self._emit_health_event(
                            port=port,
                            kind="role_reset",
                            severity="info",
                            message=msg,
                            role_name=role.name,
                        )
                        logger.info(msg)
                    else:
                        msg = (
                            f"[WARN] Role {role.name!r} on port {port} session was dead; "
                            f"relaunched (tmux={status.get('session_name')})."
                        )
                        self._emit_health_event(
                            port=port,
                            kind="role_respawn",
                            severity="warning",
                            message=msg,
                            role_name=role.name,
                        )
                        logger.warning(msg)
                    events.append(msg)
                except Exception as exc:
                    msg = (
                        f"[WARN] Role {role.name!r} on port {port} session "
                        f"died and respawn failed: {exc}"
                    )
                    self._emit_health_event(
                        port=port,
                        kind="role_respawn_failed",
                        severity="warning",
                        message=msg,
                        role_name=role.name,
                    )
                    logger.warning(msg)
                    events.append(msg)
                continue

        if events or (now - self._last_report_ts >= self.interval):
            ts = datetime.now(tz=UTC).isoformat()
            if events:
                logger.info("Gru heartbeat digest [%s]: %d event(s).", ts, len(events))
                for e in events:
                    logger.info("  %s", e)
            else:
                logger.debug("Gru heartbeat [%s]: all systems nominal.", ts)
            self._last_report_ts = now

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


def _pid_alive(pid: int) -> bool:
    """Return True if *pid* is a running process."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main() -> None:
    loop = GruLoop()
    asyncio.run(loop.run_async())


if __name__ == "__main__":
    main()
