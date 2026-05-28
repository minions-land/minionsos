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
import threading
import time
from datetime import UTC, datetime

from minions.config import load_gru_config, pin_effective_agent_host
from minions.lifecycle.health import CrashCounter, append_health_event, backend_health
from minions.logging_setup import configure_logging
from minions.paths import project_reset_markers_dir
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
        self.role_evolution_interval: int = cfg.role_evolution_interval_seconds
        self.role_evolution_auto_apply: bool = cfg.role_evolution_auto_apply
        self.gru_drive_enabled: bool = cfg.gru_drive_enabled
        self.gru_drive_interval: int = cfg.gru_drive_interval_seconds
        self.gru_drive_stale_seconds: int = cfg.gru_drive_stale_minutes * 60
        self.wedge_watchdog_enabled: bool = cfg.wedge_watchdog_enabled
        self.wedge_watchdog_interval: int = cfg.wedge_watchdog_interval_seconds
        self.wedge_watchdog_threshold: int = cfg.wedge_watchdog_threshold
        self.wedge_watchdog_tail_bytes: int = cfg.wedge_watchdog_tail_bytes
        self.wedge_watchdog_cooldown_seconds: int = cfg.wedge_watchdog_cooldown_seconds
        self.gru_digest_enabled: bool = cfg.gru_digest_enabled
        self.gru_digest_interval: int = cfg.gru_digest_interval_seconds
        self.gru_digest_anomaly_min_events: int = cfg.gru_digest_anomaly_min_events
        self.stagnation_vote_enabled: bool = cfg.stagnation_vote_enabled
        self.stagnation_vote_window: int = cfg.stagnation_vote_window_seconds
        self.stagnation_vote_cooldown: int = cfg.stagnation_vote_cooldown_seconds
        self.parked_prompt_enabled: bool = cfg.parked_prompt_watchdog_enabled
        self.parked_prompt_interval: int = cfg.parked_prompt_watchdog_interval_seconds
        self.parked_prompt_min_age: int = cfg.parked_prompt_watchdog_min_age_seconds
        self._last_parked_kick_ts: dict[tuple[int, str], float] = {}
        self._store = StateStore()
        self._crash_counter = CrashCounter()
        self._last_report_ts: float = 0.0
        self._last_drive_ts: dict[tuple[int, str], float] = {}
        self._last_wedge_kill_ts: dict[tuple[int, str], float] = {}
        self._stopped = False
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the loop to stop after the current iteration."""
        self._stopped = True
        self._stop_event.set()

    def run(self) -> None:
        """Run the monitor loop synchronously (blocking).

        Suitable for use in a daemon thread or as ``__main__``. An experiment
        scheduler thread runs in parallel with Gru's heartbeat.
        """

        def _experiment_scheduler_thread() -> None:
            while not self._stopped:
                self._reconcile_experiment_queues()
                if self._stop_event.wait(max(1, self.experiment_reconcile_interval)):
                    break

        def _role_evolution_thread() -> None:
            while not self._stopped:
                try:
                    self._evaluate_role_evolution()
                except Exception as exc:
                    logger.error("role_evolution tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.role_evolution_interval)):
                    break

        def _gru_drive_thread() -> None:
            while not self._stopped:
                try:
                    self._drive_active_projects()
                except Exception as exc:
                    logger.error("gru_drive tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.gru_drive_interval)):
                    break

        def _wedge_watchdog_thread() -> None:
            while not self._stopped:
                try:
                    self._sweep_wedged_roles()
                except Exception as exc:
                    logger.error("wedge_watchdog tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.wedge_watchdog_interval)):
                    break

        def _gru_digest_thread() -> None:
            while not self._stopped:
                try:
                    self._tick_gru_digest()
                except Exception as exc:
                    logger.error("gru_digest tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.gru_digest_interval)):
                    break

        def _stagnation_vote_thread() -> None:
            # Run on the same cadence as the digest — both are activity
            # samplers and aligning them keeps the I/O bursts near-
            # contemporaneous, which is friendlier to the SQLite WAL.
            while not self._stopped:
                try:
                    self._tick_stagnation_vote()
                except Exception as exc:
                    logger.error("stagnation_vote tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.gru_digest_interval)):
                    break

        def _parked_prompt_thread() -> None:
            while not self._stopped:
                try:
                    self._sweep_parked_roles()
                except Exception as exc:
                    logger.error("parked_prompt tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.parked_prompt_interval)):
                    break

        exp_t = threading.Thread(
            target=_experiment_scheduler_thread,
            daemon=True,
            name="experiment-scheduler",
        )
        exp_t.start()
        evo_t = threading.Thread(
            target=_role_evolution_thread,
            daemon=True,
            name="role-evolution",
        )
        evo_t.start()
        if self.gru_drive_enabled:
            drv_t = threading.Thread(
                target=_gru_drive_thread,
                daemon=True,
                name="gru-drive",
            )
            drv_t.start()
            logger.info(
                "Gru drive thread started (interval=%ds, stale=%ds).",
                self.gru_drive_interval,
                self.gru_drive_stale_seconds,
            )
        if self.wedge_watchdog_enabled:
            wedge_t = threading.Thread(
                target=_wedge_watchdog_thread,
                daemon=True,
                name="wedge-watchdog",
            )
            wedge_t.start()
            logger.info(
                "Wedge watchdog started (interval=%ds, threshold=%d, tail=%dB).",
                self.wedge_watchdog_interval,
                self.wedge_watchdog_threshold,
                self.wedge_watchdog_tail_bytes,
            )
        if self.gru_digest_enabled:
            digest_t = threading.Thread(
                target=_gru_digest_thread,
                daemon=True,
                name="gru-digest",
            )
            digest_t.start()
            logger.info(
                "Gru digest cron started (interval=%ds, anomaly_min_events=%d).",
                self.gru_digest_interval,
                self.gru_digest_anomaly_min_events,
            )
        if self.stagnation_vote_enabled:
            stag_t = threading.Thread(
                target=_stagnation_vote_thread,
                daemon=True,
                name="stagnation-vote",
            )
            stag_t.start()
            logger.info(
                "Stagnation-vote breaker started (window=%ds, cooldown=%ds).",
                self.stagnation_vote_window,
                self.stagnation_vote_cooldown,
            )
        if self.parked_prompt_enabled:
            parked_t = threading.Thread(
                target=_parked_prompt_thread,
                daemon=True,
                name="parked-prompt",
            )
            parked_t.start()
            logger.info(
                "Parked-prompt watchdog started (interval=%ds, min_age=%ds).",
                self.parked_prompt_interval,
                self.parked_prompt_min_age,
            )
        logger.info("Gru monitor loop started (interval=%ds).", self.interval)
        try:
            while not self._stopped:
                try:
                    self._tick()
                except Exception as exc:
                    logger.error("Gru monitor tick error: %s", exc, exc_info=True)
                if self._stop_event.wait(max(1, self.interval)):
                    break
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
                # Sleep in small chunks so signal handler can interrupt quickly
                for _ in range(self.interval * 2):
                    if self._stopped:
                        break
                    await asyncio.sleep(0.5)
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

        # Auto-exit when no active projects remain
        if not projects:
            logger.info("No active projects remaining, Gru monitor exiting.")
            self._stopped = True
            return

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
                    # Below threshold — attempt backend respawn
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
                    # Attempt auto-respawn
                    try:
                        from minions.lifecycle.project import respawn_backend

                        respawn_backend(port)
                        respawn_msg = f"[INFO] Backend respawned on port {port}."
                        self._emit_health_event(
                            port=port,
                            kind="backend_respawn",
                            severity="info",
                            message=respawn_msg,
                            metadata={"project_name": project.real_name},
                        )
                        logger.info(respawn_msg)
                        events.append(respawn_msg)
                    except Exception as exc:
                        err_msg = f"[ERROR] Backend respawn failed on port {port}: {exc}"
                        logger.error(err_msg)
                        events.append(err_msg)
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
                marker = project_reset_markers_dir(port) / role.name
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

        # Reap orphan tmux sessions (ports not in active projects)
        self._reap_orphan_sessions()

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
        """Run Python-side Coder experiment queue scheduling for active projects."""
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

    def _evaluate_role_evolution(self) -> None:
        """Periodic evidence-gated role-evolution evaluation.

        Reads recent artifacts under each project's branches/shared/, runs
        ``role_evolution.evaluate``, and writes one audit-log line per
        evaluation. When ``role_evolution_auto_apply`` is enabled, also
        invokes the corresponding apply_split / apply_merge / apply_dismiss
        for each non-KEEP recommendation. Default is recommend-only.
        """
        from minions.lifecycle import role_evolution as RE

        projects = self._store.list_projects(filter="active")
        for project in projects:
            try:
                report = RE.evaluate(project.port, store=self._store)
            except Exception as exc:
                logger.debug("role_evolution.evaluate skipped port=%d: %s", project.port, exc)
                continue

            non_keep_splits = [s for s in report.splits if s.decision != "KEEP"]
            non_keep_merges = [m for m in report.merges if m.decision != "KEEP"]
            non_keep_dismisses = [d for d in report.dismisses if d.decision != "KEEP"]
            if not non_keep_splits and not non_keep_merges and not non_keep_dismisses:
                continue

            # Always log to the governance audit so operators can see what
            # the supervisor would have done — even when auto-apply is off.
            try:
                RE.append_audit(
                    project_port=project.port,
                    kind="evaluate",
                    roles_in=[s.role for s in non_keep_splits]
                    + [r for m in non_keep_merges for r in m.roles]
                    + [d.role for d in non_keep_dismisses],
                    roles_out=[
                        spec["name"] for s in non_keep_splits for spec in s.proposed_specialists
                    ]
                    + [m.proposed_role["name"] for m in non_keep_merges if m.proposed_role],
                    reason="periodic-evaluate",
                    extra={
                        "splits": [{"role": s.role, "reason": s.reason} for s in non_keep_splits],
                        "merges": [
                            {"roles": m.roles, "kind": m.kind, "reason": m.reason}
                            for m in non_keep_merges
                        ],
                        "dismisses": [
                            {"role": d.role, "reason": d.reason} for d in non_keep_dismisses
                        ],
                        "auto_apply": self.role_evolution_auto_apply,
                    },
                )
            except Exception as exc:
                logger.warning("role_evolution audit write failed: %s", exc)

            if not self.role_evolution_auto_apply:
                continue

            # Auto-apply branch — splits, then merges, then dismisses.
            # Order matters: split is the only growth move, so do it before
            # any retraction to maximise coverage; merges close redundancy;
            # dismisses retire what is left starved. Each application is
            # best-effort and continues on failure.
            for s in non_keep_splits:
                try:
                    RE.apply_split(
                        project_port=project.port,
                        source_role=s.role,
                        into_specs=s.proposed_specialists,
                        evidence_refs=[ev.artifact_path for c in s.clusters for ev in c.events[:3]],
                        reason=f"auto-apply: {s.reason}",
                        store=self._store,
                    )
                except Exception as exc:
                    logger.error("auto-apply split failed for %s: %s", s.role, exc)

            for m in non_keep_merges:
                if not m.proposed_role:
                    continue
                try:
                    RE.apply_merge(
                        project_port=project.port,
                        source_roles=m.roles,
                        into_spec=m.proposed_role,
                        evidence_refs=["auto:" + m.kind],
                        reason=f"auto-apply: {m.reason}",
                        store=self._store,
                    )
                except Exception as exc:
                    logger.error("auto-apply merge failed for %s: %s", m.roles, exc)

            for d in non_keep_dismisses:
                try:
                    RE.apply_dismiss(
                        project_port=project.port,
                        role_name=d.role,
                        evidence_refs=[f"auto:starvation:{d.role}"],
                        reason=f"auto-apply: {d.reason}",
                        store=self._store,
                    )
                except Exception as exc:
                    logger.error("auto-apply dismiss failed for %s: %s", d.role, exc)

    def _drive_active_projects(self) -> None:
        """Send an advisory EACN message to any Role that has been silent
        too long.

        For each active project, the loop:
          1. Reads each registered Role's heartbeat file
             (``branches/<role>/.minionsos/heartbeat`` — refreshed by the
             ``heartbeat_refresh`` PreToolUse hook on every tool call).
          2. Computes how stale each heartbeat is.
          3. For Roles older than ``gru_drive_stale_seconds``, sends a
             single advisory EACN message asking for a status check.
          4. Records the drive timestamp in
             ``self._last_drive_ts`` so we don't re-nudge the same Role
             every tick — a single nudge per role per
             ``gru_drive_stale_seconds`` window is enough.

        Best-effort end-to-end: any failure (missing heartbeat, EACN
        timeout, broken project) is logged and skipped, never raised.
        Disabled by default; gated on ``gru.yaml: gru_drive_enabled``.
        """
        from minions.lifecycle import eacn_client
        from minions.lifecycle.eacn_identity import resolve_agent_id
        from minions.paths import project_role_workspace

        now = time.time()
        projects = self._store.list_projects(filter="active")
        for project in projects:
            port = project.port
            for role in project.active_roles:
                if role.state != "active":
                    continue
                if role.name == "noter":
                    # Noter is on a timer backbone, not EACN — drive doesn't apply.
                    continue
                hb_age = self._heartbeat_age_seconds(port, role.name)
                if hb_age is None:
                    # No heartbeat yet — the Role just spawned. Don't nudge.
                    continue
                if hb_age < self.gru_drive_stale_seconds:
                    continue
                # Avoid re-nudging the same Role within the stale window.
                key = (port, role.name)
                last = self._last_drive_ts.get(key, 0.0)
                if now - last < self.gru_drive_stale_seconds:
                    continue
                try:
                    eacn_client.send_message(
                        port=port,
                        to_agent_id=resolve_agent_id(port, role.name),
                        from_agent_id=resolve_agent_id(port, "gru"),
                        content={
                            "kind": "gru_drive_nudge",
                            "role": role.name,
                            "stale_seconds": int(hb_age),
                            "advisory": (
                                f"You have been silent for ~{int(hb_age // 60)} min. "
                                "Gru is checking in. If you're still working, ignore. "
                                "If you're stuck or waiting on a peer, send a status "
                                "message to Gru explaining what's blocked."
                            ),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "gru_drive: nudge failed port=%d role=%s: %s",
                        port,
                        role.name,
                        exc,
                    )
                    continue
                self._last_drive_ts[key] = now
                logger.info(
                    "gru_drive: nudged port=%d role=%s (stale=%ds)",
                    port,
                    role.name,
                    int(hb_age),
                )
        # Reference unused import path so a refactor doesn't drop it silently.
        _ = project_role_workspace

    def _sweep_wedged_roles(self) -> None:
        """Detect Roles stuck in an empty-upstream / bare-`ack` loop and kill them.

        See GitHub Issue #15 and ``minions.lifecycle.wedge_detect``. The
        kill triggers the existing watchdog respawn path in ``_tick`` —
        same outcome as ``mos_reset_context`` but enforced from outside
        the wedged process. A cooldown suppresses repeated kills against
        the same role so a freshly-respawned role gets time to cold-start.
        """
        from minions.lifecycle.role_launcher import kill_session
        from minions.lifecycle.wedge_detect import inspect_role, is_wedged
        from minions.paths import project_role_log, project_role_workspace

        now = time.time()
        projects = self._store.list_projects(filter="active")
        for project in projects:
            port = project.port
            for role in project.active_roles:
                if role.state != "active":
                    continue
                if role.name == "noter":
                    # Noter drives off a timer rather than mos_await_events;
                    # its log shape differs and the wedge signature does
                    # not apply.
                    continue
                key = (port, role.name)
                last_kill = self._last_wedge_kill_ts.get(key, 0.0)
                if now - last_kill < self.wedge_watchdog_cooldown_seconds:
                    continue
                log_path = project_role_log(port, role.name)
                cwd = project_role_workspace(port, role.name)
                signal = inspect_role(
                    cwd=cwd,
                    log_path=log_path,
                    tail_bytes=self.wedge_watchdog_tail_bytes,
                )
                # Always emit one diagnostic line per tick per role so the
                # operator can see whether the watchdog is firing — Issue
                # #26's "watchdog is decorative" complaint stems from the
                # silent-failure mode.
                logger.debug(
                    "wedge_watchdog: port=%d role=%s source=%s empty=%d ack=%d sampled=%d",
                    port,
                    role.name,
                    signal.log_path.suffix,
                    signal.empty_marker_count,
                    signal.ack_line_count,
                    signal.sampled_lines,
                )
                if not is_wedged(signal, threshold=self.wedge_watchdog_threshold):
                    continue
                msg = (
                    f"[ALERT] Role {role.name!r} on port {port} appears wedged "
                    f"(empty={signal.empty_marker_count}, "
                    f"ack={signal.ack_line_count} in last "
                    f"{signal.sampled_lines} samples from {signal.log_path.name}). "
                    "Killing tmux session so the respawn path cold-starts the role from Draft."
                )
                logger.error(msg)
                self._emit_health_event(
                    port=port,
                    kind="role_wedged",
                    severity="alert",
                    message=msg,
                    role_name=role.name,
                    metadata={
                        "empty_marker_count": signal.empty_marker_count,
                        "ack_line_count": signal.ack_line_count,
                        "sampled_lines": signal.sampled_lines,
                        "signal_source": signal.log_path.name,
                        "threshold": self.wedge_watchdog_threshold,
                    },
                )
                try:
                    kill_session(port, role.name)
                except Exception as exc:
                    logger.warning(
                        "wedge_watchdog: kill_session failed port=%d role=%s: %s",
                        port,
                        role.name,
                        exc,
                    )
                self._last_wedge_kill_ts[key] = now

    def _sweep_parked_roles(self) -> None:
        """Recover roles parked at the input prompt after /compact (Issue #29).

        The post_compact_draft hook fires an immediate tmux kick on its
        way out — this Gru-side sweep is the safety net for the case
        where the hook itself failed (no tmux on PATH at hook-spawn
        time, race with the TUI redraw, the hook crashed before it
        reached the kick).

        Detection requires both signals: (a) the role's pane shows the
        prompt cursor on its own line in the recent tail, AND (b) the
        role's heartbeat is at least ``parked_prompt_min_age`` stale.
        Either signal alone has a high false-positive rate (a healthy
        role renders the cursor briefly between turns; a stale heartbeat
        may indicate a deeper wedge handled by the wedge-watchdog
        instead). Both together are specific to the parked-after-compact
        failure mode.
        """
        from minions.lifecycle.parked_prompt import detect_parked_pane, kick_pane
        from minions.lifecycle.role_launcher import session_alive
        from minions.lifecycle.role_launcher import session_name as _session_name

        now = time.time()
        projects = self._store.list_projects(filter="active")
        for project in projects:
            port = project.port
            for role in project.active_roles:
                if role.state != "active":
                    continue
                if role.name == "noter":
                    # Noter doesn't go through /compact in the same shape;
                    # if it ever parks the noter-wait timer wakes it on
                    # its own cadence.
                    continue
                key = (port, role.name)
                # Cooldown after a successful kick — the role needs a
                # cycle to redraw and start its next turn before we look
                # again, otherwise we'd kick the same prompt twice.
                last_kick = self._last_parked_kick_ts.get(key, 0.0)
                if now - last_kick < self.parked_prompt_interval:
                    continue
                if not session_alive(port, role.name):
                    continue
                hb_age = self._heartbeat_age_seconds(port, role.name)
                if hb_age is None or hb_age < self.parked_prompt_min_age:
                    continue
                sess = _session_name(port, role.name)
                signal = detect_parked_pane(sess)
                if not signal.parked:
                    continue
                logger.info(
                    "parked_prompt: kicking port=%d role=%s session=%s "
                    "(hb_age=%ds, snapshot_lines=%d)",
                    port,
                    role.name,
                    sess,
                    int(hb_age),
                    signal.snapshot_lines,
                )
                if kick_pane(sess):
                    self._last_parked_kick_ts[key] = now
                    self._emit_health_event(
                        port=port,
                        kind="parked_prompt_recovered",
                        severity="info",
                        message=(
                            f"Role {role.name!r} on port {port} was parked at "
                            f"the input prompt after /compact "
                            f"(hb_age={int(hb_age)}s); Gru sent a recovery kick."
                        ),
                        role_name=role.name,
                        metadata={"hb_age_seconds": int(hb_age)},
                    )

    def _tick_gru_digest(self) -> None:
        """Snapshot per-role event/Draft activity and persist a digest.

        See ``minions.gru.digest`` for the data model. The tick is cheap
        (no LLM tokens, no EACN traffic, just disk reads + one markdown
        write per project), so we do not gate it on a cooldown — every
        tick produces a fresh digest.
        """
        from minions.gru import digest as digest_mod

        projects = self._store.list_projects(filter="active")
        for project in projects:
            port = project.port
            role_names = [
                role.name
                for role in project.active_roles
                if role.state == "active" and role.name != "noter"
            ]
            if not role_names:
                continue
            try:
                snapshot = digest_mod.collect_project_digest(
                    port,
                    role_names,
                    window_seconds=self.gru_digest_interval,
                    anomaly_min_events=self.gru_digest_anomaly_min_events,
                )
                digest_mod.publish_digest(snapshot)
            except Exception as exc:
                logger.warning("gru_digest: failed for port=%d: %s", port, exc, exc_info=True)

    def _tick_stagnation_vote(self) -> None:
        """Open a milestone vote on every active project that's been silent.

        See ``minions.gru.milestone_vote``. The detection is cheap (Draft
        json read, ``git log -1`` on the shared worktree, one SQLite
        query against the experiment scheduler), so we run it for every
        active project on every tick and let the cooldown prevent
        spam. Decisions are logged at info so the operator can audit
        which votes were opened and why.
        """
        from minions.gru import milestone_vote

        projects = self._store.list_projects(filter="active")
        for project in projects:
            port = project.port
            try:
                profile_name = getattr(project, "profile_name", None)
                current_phase = getattr(project, "current_phase", None)
                outcome = milestone_vote.tick_for_project(
                    port,
                    profile_name=profile_name,
                    current_phase=current_phase,
                    window_seconds=self.stagnation_vote_window,
                    cooldown_seconds=self.stagnation_vote_cooldown,
                )
            except Exception as exc:
                logger.warning(
                    "stagnation_vote: tick failed for port=%d: %s",
                    port,
                    exc,
                    exc_info=True,
                )
                continue
            if outcome.get("acted"):
                logger.info(
                    "stagnation_vote: opened vote on port=%d milestone=%s addressed=%s reason=%r",
                    port,
                    outcome.get("milestone"),
                    outcome.get("addressed"),
                    outcome.get("reason"),
                )
                self._emit_health_event(
                    port=port,
                    kind="stagnation_vote_opened",
                    severity="info",
                    message=(
                        f"Gru opened a milestone vote for "
                        f"{outcome.get('milestone')!r} after stagnation: "
                        f"{outcome.get('reason')}"
                    ),
                    role_name="gru",
                    metadata={
                        "milestone": outcome.get("milestone"),
                        "addressed": outcome.get("addressed", []),
                        "failed": outcome.get("failed", []),
                    },
                )

    def _heartbeat_age_seconds(self, port: int, role_name: str) -> float | None:
        """Return seconds since the Role's heartbeat file was last touched.

        Returns ``None`` when the file doesn't exist (likely a newly-
        spawned Role that hasn't run a tool call yet).
        """
        from minions.paths import project_role_workspace

        try:
            workspace = project_role_workspace(port, role_name)
            hb = workspace / ".minionsos" / "heartbeat"
            if not hb.is_file():
                return None
            return time.time() - hb.stat().st_mtime
        except OSError:
            return None

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

    def _reap_orphan_sessions(self) -> None:
        """Kill ``mos-{port}-{role}`` tmux sessions whose port is not active.

        Defensive sweep against pytest residue, crash leftovers, and any
        path where a Role tmux session outlives its project record. The
        session-name format is the contract from ``role_launcher``; any
        session matching ``mos-<int>-...`` whose <int> is not an active
        project port is an orphan and gets killed.
        """
        import subprocess

        try:
            result = subprocess.run(["tmux", "ls"], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return  # no tmux, nothing to reap
        if result.returncode != 0:
            return  # no tmux server / no sessions

        active_ports = {p.port for p in self._store.list_projects(filter="active")}

        for line in (result.stdout or "").splitlines():
            session_name = line.split(":", 1)[0]
            if not session_name.startswith("mos-"):
                continue
            parts = session_name.split("-", 2)
            if len(parts) < 2:
                continue
            try:
                port = int(parts[1])
            except ValueError:
                continue
            if port in active_ports:
                continue
            try:
                subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    capture_output=True,
                    check=False,
                )
                logger.info(
                    "Reaped orphan tmux session %s (port %d not active)", session_name, port
                )
            except Exception as exc:
                logger.debug("Failed to reap orphan session %s: %s", session_name, exc)


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
    import signal

    loop = GruLoop()

    def _signal_handler(signum: int, _frame: object) -> None:
        logger.info("Received signal %d, stopping Gru monitor.", signum)
        loop.stop()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    asyncio.run(loop.run_async())


if __name__ == "__main__":
    main()
