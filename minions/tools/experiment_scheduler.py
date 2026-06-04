"""Project-level experiment queue and GPU packing scheduler.

The Expert should not spend context manually deciding which GPU gets
the next run. This module keeps a durable project queue in SQLite and performs a
simple "fluid gravity" reconcile: every pending unit is considered against the
current fleet, and any allowed GPU with capacity can absorb the next runnable
unit.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.config import load_experiment_targets
from minions.tools.scheduler_gpu import (
    build_gpu_slots,
    get_gpu_pool_status,
    gpu_capacity_ceiling,
)
from minions.tools.scheduler_gpu import (
    set_gpu_pool as gpu_set_pool,
)
from minions.tools.scheduler_helpers import (
    QueueUnit,
    _json_dumps,
    _new_id,
    _now_iso,
    _UnitRowView,
    check_hard_anomalies,
    default_db_path,
    resolve_project_port,
)
from minions.tools.scheduler_packing import (
    block_reason,
    escalate_reserve,
    is_oom,
    pick_candidate,
    placement_summary,
    reserve_slots,
)
from minions.tools.scheduler_queue import (
    get_blocked_units,
    get_pending_units,
    get_status,
    note_no_capacity,
    refresh_batches,
    submit_batch,
)

logger = logging.getLogger(__name__)

QueryGpusFn = Callable[[str], list[dict[str, Any]]]
ExpRunFn = Callable[[str, str, list[int] | None], dict[str, Any]]
ExpStatusFn = Callable[[str, str], dict[str, Any]]
ExpKillFn = Callable[[str, str], dict[str, Any]]


class ExperimentScheduler:
    """Durable project-level experiment queue with GPU fluid-fill reconcile."""

    def __init__(
        self,
        *,
        project_port: int | None = None,
        db_path: Path | None = None,
        target_ids: Iterable[str] | None = None,
        query_gpus_fn: QueryGpusFn | None = None,
        exp_run_fn: ExpRunFn | None = None,
        exp_status_fn: ExpStatusFn | None = None,
        exp_kill_fn: ExpKillFn | None = None,
    ) -> None:
        self.project_port = project_port
        self.db_path = db_path or default_db_path(resolve_project_port(project_port))
        self._target_ids = list(target_ids) if target_ids is not None else None
        self._query_gpus_fn = query_gpus_fn
        self._exp_run_fn = exp_run_fn
        self._exp_status_fn = exp_status_fn
        self._exp_kill_fn = exp_kill_fn
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        units: list[QueueUnit],
        *,
        requester: str | None = None,
        batch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        reconcile: bool = True,
    ) -> dict[str, Any]:
        """Append a new logical batch into the project-global queue."""
        if not units:
            raise ValueError("exp_queue_submit requires at least one unit.")

        units_dicts = [
            {
                "cmd": u.cmd,
                "target_id": u.target_id,
                "gpu_ids": u.gpu_ids,
                "gpus_needed": u.gpus_needed,
                "min_free_mb": u.min_free_mb,
                "reserve_mb": u.reserve_mb,
                "priority": u.priority,
                "max_retries": u.max_retries,
                "metadata": u.metadata,
            }
            for u in units
        ]

        with self._tx() as conn:
            bid, unit_ids = submit_batch(
                conn,
                units_dicts,
                requester=requester,
                batch_id=batch_id,
                metadata=metadata,
            )

        result: dict[str, Any] = {"batch_id": bid, "unit_ids": unit_ids, "submitted": len(unit_ids)}
        if reconcile:
            result["reconcile"] = self.reconcile()
        return result

    def reconcile(self, batch_id: str | None = None) -> dict[str, Any]:
        """Update statuses and launch every pending unit that fits current GPU state."""
        launched: list[dict[str, Any]] = []
        completed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        with self._tx() as conn:
            reaped = self._reap_zombie_runs(conn)
            completed, failed = self._refresh_running(conn)
            slots = build_gpu_slots(conn, self._query_gpus, self._configured_target_ids())
            pending = get_pending_units(conn, batch_id=batch_id)

            for unit in pending:
                candidate = pick_candidate(unit, slots, self._configured_target_ids())
                if candidate is None:
                    note_no_capacity(conn, unit, block_reason(unit, self._configured_target_ids()))
                    continue
                target_id, gpu_ids, reserve_mb = candidate
                now = _now_iso()
                conn.execute(
                    """
                    UPDATE units
                    SET status='launching', attempts=attempts + 1, last_error=NULL, updated_at=?
                    WHERE unit_id=?
                    """,
                    (now, unit["unit_id"]),
                )
                try:
                    run = self._exp_run(target_id, unit["cmd"], gpu_ids)
                except Exception as exc:
                    message = str(exc)
                    conn.execute(
                        """
                        UPDATE units
                        SET status='pending', last_error=?, updated_at=?
                        WHERE unit_id=?
                        """,
                        (message, _now_iso(), unit["unit_id"]),
                    )
                    failed.append({"unit_id": unit["unit_id"], "launch_error": message})
                    continue

                run_id = str(run.get("run_id") or _new_id("run"))
                conn.execute(
                    """
                    INSERT INTO runs(
                        run_id, unit_id, batch_id, target_id, gpu_ids_json, pid, log_path,
                        state, started_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
                    """,
                    (
                        run_id,
                        unit["unit_id"],
                        unit["batch_id"],
                        str(run.get("target_id") or target_id),
                        _json_dumps(gpu_ids),
                        run.get("pid"),
                        run.get("log_path"),
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE units
                    SET status='running', active_run_id=?, updated_at=?
                    WHERE unit_id=?
                    """,
                    (run_id, now, unit["unit_id"]),
                )
                reserve_slots(slots, target_id, gpu_ids, reserve_mb)
                launched.append(
                    {
                        "unit_id": unit["unit_id"],
                        "batch_id": unit["batch_id"],
                        "run_id": run_id,
                        "target_id": target_id,
                        "gpu_ids": gpu_ids,
                    }
                )

            refresh_batches(conn)
            blocked = get_blocked_units(conn, batch_id=batch_id)
            placement = placement_summary(conn, launched, slots)
            self._set_meta(conn, "last_reconcile_at", _now_iso())

        return {
            "launched": launched,
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "reaped": reaped,
            "placement": placement,
            "summary": self.status(batch_id=batch_id)["summary"],
        }

    def status(self, batch_id: str | None = None) -> dict[str, Any]:
        """Return a compact queue status for one batch or the whole project."""
        with self._connect() as conn:
            result = get_status(conn, batch_id=batch_id)

        result["last_reconcile_at"] = self._get_meta("last_reconcile_at")
        result["gpu_idle_warning"] = self._gpu_idle_warning(result["units"])
        return result

    def set_gpu_pool(
        self,
        *,
        target_id: str = "all",
        allowed_gpu_ids: list[int] | str = "all",
        draining: bool = True,
        evict: bool = False,
        reason: str | None = None,
        reconcile: bool = True,
    ) -> dict[str, Any]:
        """Set the dynamic allow-list of GPUs available for new runs."""
        with self._tx() as conn:
            changed, evicted_runs = gpu_set_pool(
                conn,
                self._query_gpus,
                self._exp_kill,
                self._target_ids_for_pool(target_id),
                target_id=target_id,
                allowed_gpu_ids=allowed_gpu_ids,
                draining=draining,
                evict=evict,
                reason=reason,
            )

        result: dict[str, Any] = {"changed": changed}
        if evict:
            result["evicted"] = evicted_runs
        if reconcile:
            result["reconcile"] = self.reconcile()
        return result

    def gpu_pool(self) -> dict[str, Any]:
        """Return current allowed/draining GPU pool records."""
        with self._connect() as conn:
            return get_gpu_pool_status(conn)

    def plan(self, units: list[QueueUnit]) -> dict[str, Any]:
        """Dry-run: where would these units land if submitted right now?"""
        with self._connect() as conn:
            slots = build_gpu_slots(conn, self._query_gpus, self._configured_target_ids())

        fleet_snapshot = [
            {
                "target_id": s.target_id,
                "gpu_id": s.gpu_id,
                "free_mb": s.free_mb,
                "total_mb": s.total_mb,
                "remaining_mb": s.remaining_mb,
            }
            for s in slots
        ]

        placements: list[dict[str, Any]] = []
        for idx, unit in enumerate(units):
            view = _UnitRowView(unit)
            candidate = pick_candidate(view, slots, self._configured_target_ids())
            if candidate is None:
                placements.append(
                    {
                        "unit_index": idx,
                        "status": "blocked",
                        "reason": block_reason(view, self._configured_target_ids()),
                    }
                )
                continue
            target_id, gpu_ids, reserve_mb = candidate
            reserve_slots(slots, target_id, gpu_ids, reserve_mb)
            placements.append(
                {
                    "unit_index": idx,
                    "status": "fits",
                    "target_id": target_id,
                    "gpu_ids": gpu_ids,
                    "reserve_mb": reserve_mb,
                }
            )

        fits = sum(1 for p in placements if p["status"] == "fits")
        blocked = len(placements) - fits
        return {
            "placements": placements,
            "fleet_snapshot": fleet_snapshot,
            "summary": {"fits": fits, "blocked": blocked, "total": len(placements)},
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    requester TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS units (
                    unit_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    cmd TEXT NOT NULL,
                    target_id TEXT NOT NULL DEFAULT 'auto',
                    gpu_ids_json TEXT,
                    gpus_needed INTEGER NOT NULL DEFAULT 1,
                    min_free_mb INTEGER NOT NULL DEFAULT 0,
                    reserve_mb INTEGER,
                    priority INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 1,
                    active_run_id TEXT,
                    last_error TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    unit_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    gpu_ids_json TEXT NOT NULL,
                    pid INTEGER,
                    log_path TEXT,
                    state TEXT NOT NULL,
                    exit_code INTEGER,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(unit_id) REFERENCES units(unit_id),
                    FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
                );

                CREATE TABLE IF NOT EXISTS gpu_pool (
                    target_id TEXT NOT NULL,
                    gpu_id INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    draining INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(target_id, gpu_id)
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _set_meta(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT INTO meta(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, _now_iso()),
        )

    def _get_meta(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _configured_target_ids(self) -> list[str]:
        if self._target_ids is not None:
            return list(self._target_ids)
        cfg = load_experiment_targets()
        return [target.id for target in cfg.active_targets()]

    def _target_ids_for_pool(self, target_id: str) -> list[str]:
        if target_id == "all":
            return self._configured_target_ids()
        return [target_id]

    def _query_gpus(self, target_id: str) -> list[dict[str, Any]]:
        if self._query_gpus_fn is not None:
            return self._query_gpus_fn(target_id)
        from minions.tools.experiment_ssh import QueryGpusArgs, query_gpus

        return query_gpus(QueryGpusArgs(target_id=target_id))

    def _exp_run(self, target_id: str, cmd: str, gpu_ids: list[int] | None) -> dict[str, Any]:
        if self._exp_run_fn is not None:
            return self._exp_run_fn(target_id, cmd, gpu_ids)
        from minions.tools.experiment_ssh import ExpRunArgs, exp_run

        prior = os.environ.get("MINIONS_PROJECT_PORT")
        if self.project_port is not None:
            os.environ["MINIONS_PROJECT_PORT"] = str(self.project_port)
        try:
            return exp_run(ExpRunArgs(target_id=target_id, cmd=cmd, gpu_ids=gpu_ids))
        finally:
            if self.project_port is not None:
                if prior is None:
                    os.environ.pop("MINIONS_PROJECT_PORT", None)
                else:
                    os.environ["MINIONS_PROJECT_PORT"] = prior

    def _exp_status(self, target_id: str, run_id: str) -> dict[str, Any]:
        if self._exp_status_fn is not None:
            return self._exp_status_fn(target_id, run_id)
        from minions.tools.experiment_ssh import ExpStatusArgs, exp_status

        status = exp_status(ExpStatusArgs(target_id=target_id, run_id=run_id))
        return {k: v for k, v in status.items()}

    def _exp_kill(self, target_id: str, run_id: str) -> dict[str, Any]:
        if self._exp_kill_fn is not None:
            return self._exp_kill_fn(target_id, run_id)
        from minions.tools.experiment_ssh import ExpKillArgs, exp_kill

        return exp_kill(ExpKillArgs(target_id=target_id, run_id=run_id))

    def _gpu_idle_warning(self, units: list[dict[str, Any]]) -> str:
        """Return a non-empty string when no_capacity units sit while GPUs idle."""
        no_cap = [
            u
            for u in units
            if u.get("status") == "pending"
            and (u.get("last_error") or "").startswith("no_capacity")
        ]
        if not no_cap:
            return ""
        try:
            target_ids = self._configured_target_ids()
            gpus_used = 0
            gpus_total = 0
            for tid in target_ids:
                snap = self._query_gpus(tid)
                for gpu in snap:
                    gpus_total += 1
                    if int(gpu.get("used_mb", 0)) > 0:
                        gpus_used += 1
        except Exception:
            return ""
        if gpus_total == 0 or gpus_used > 0:
            return ""
        return (
            f"{len(no_cap)} pending units stuck on no_capacity but "
            f"{gpus_total} GPUs report 0 MiB used — call exp_queue_reconcile."
        )

    def _resolve_port(self) -> int | None:
        """Best-effort resolution of the project port for EACN notifications."""
        if self.project_port is not None:
            return self.project_port
        raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
        return int(raw) if raw.isdigit() else None

    def _notify_requester(
        self,
        run_id: str,
        status: str,
        *,
        exit_code: int | None = None,
        log_path: str | None = None,
        target_id: str | None = None,
        duration_seconds: float | None = None,
        metrics_summary: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Best-effort EACN notification to the experiment's requester on completion."""
        port = self._resolve_port()
        if port is None:
            logger.debug("_notify_requester: no project port, skipping notification for %s", run_id)
            return
        to_agent = "expert"
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT b.requester FROM runs r "
                    "JOIN batches b ON r.batch_id = b.batch_id "
                    "WHERE r.run_id = ?",
                    (run_id,),
                ).fetchone()
            if row and row[0]:
                to_agent = str(row[0])
        except Exception as exc:
            logger.debug("_notify_requester: requester lookup failed for %s: %s", run_id, exc)
        payload: dict[str, Any] = {
            "type": "experiment_complete",
            "run_id": run_id,
            "status": status,
        }
        if exit_code is not None:
            payload["exit_code"] = exit_code
        if log_path:
            payload["log_path"] = log_path
        if target_id:
            payload["target_id"] = target_id
        if duration_seconds is not None:
            payload["duration_seconds"] = round(duration_seconds, 1)
        if metrics_summary:
            payload["metrics_summary"] = metrics_summary
        if reason:
            payload["reason"] = reason
        try:
            from minions.lifecycle.eacn_client import _post_message_raw

            _post_message_raw(
                port=port,
                to_agent_id=to_agent,
                from_agent_id="scheduler",
                content=payload,
                timeout=5.0,
            )
            logger.info(
                "Notified %s: run_id=%s status=%s on port %d", to_agent, run_id, status, port
            )
        except Exception as exc:
            logger.warning(
                "Failed to notify %s for run_id=%s status=%s: %s", to_agent, run_id, status, exc
            )

    def _reap_zombie_runs(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        """Transition runs whose backing PID is dead into state='exited'."""
        if (
            self._exp_run_fn is not None
            or self._exp_status_fn is not None
            or self._exp_kill_fn is not None
        ):
            return []
        rows = conn.execute(
            """
            SELECT run_id, unit_id, pid, log_path
            FROM runs
            WHERE state IN ('running', 'launching')
            """
        ).fetchall()
        reaped: list[dict[str, Any]] = []
        for row in rows:
            pid = row["pid"]
            if pid is None:
                continue
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                continue
            try:
                os.kill(pid_int, 0)
                continue
            except ProcessLookupError:
                pass
            except PermissionError:
                continue
            except OSError:
                continue
            exit_code = -9
            log_path_s = row["log_path"]
            if log_path_s:
                exit_path = Path(log_path_s).with_suffix(".exit")
                if exit_path.exists():
                    try:
                        exit_code = int(exit_path.read_text().strip() or "0")
                    except (OSError, ValueError):
                        exit_code = -1
            now = _now_iso()
            conn.execute(
                """
                UPDATE runs
                SET state='exited', exit_code=?, finished_at=?, updated_at=?
                WHERE run_id=?
                """,
                (exit_code, now, now, row["run_id"]),
            )
            new_status = "done" if exit_code == 0 else "failed"
            last_error = None if exit_code == 0 else f"zombie_reaped: exit_code={exit_code}"
            conn.execute(
                """
                UPDATE units
                SET status=?, active_run_id=NULL, last_error=?, updated_at=?
                WHERE unit_id=?
                """,
                (new_status, last_error, now, row["unit_id"]),
            )
            logger.warning(
                "reaped zombie run_id=%s unit_id=%s pid=%d exit_code=%d",
                row["run_id"],
                row["unit_id"],
                pid_int,
                exit_code,
            )
            reaped.append(
                {
                    "run_id": row["run_id"],
                    "unit_id": row["unit_id"],
                    "pid": pid_int,
                    "exit_code": exit_code,
                    "next_status": new_status,
                }
            )
        return reaped

    def _refresh_running(self, conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
        """Poll active runs and transition completed/failed units."""
        completed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        rows = conn.execute(
            """
            SELECT r.run_id, r.unit_id, r.batch_id, r.target_id, r.started_at, r.log_path,
                   u.attempts, u.max_retries, u.reserve_mb, u.min_free_mb
            FROM runs r
            JOIN units u ON u.unit_id = r.unit_id
            WHERE r.state IN ('running', 'launching')
            """
        ).fetchall()
        for row in rows:
            try:
                status = self._exp_status(str(row["target_id"]), str(row["run_id"]))
            except Exception as exc:
                logger.debug("exp_status failed run_id=%s: %s", row["run_id"], exc)
                continue

            log_tail = str(status.get("log_tail") or "")

            # Hard-metric anomaly detection
            if status.get("state") != "exited":
                anomaly_reason = check_hard_anomalies(
                    str(row["run_id"]), str(row["target_id"]), log_tail
                )
                if anomaly_reason:
                    logger.warning(
                        "Anomaly detected run_id=%s: %s — killing", row["run_id"], anomaly_reason
                    )
                    try:
                        self._exp_kill(str(row["target_id"]), str(row["run_id"]))
                    except Exception as exc:
                        logger.warning("exp_kill during anomaly failed: %s", exc)
                    now = _now_iso()
                    conn.execute(
                        """
                        UPDATE runs
                        SET state='exited', exit_code=-99, finished_at=?, updated_at=?
                        WHERE run_id=?
                        """,
                        (now, now, row["run_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE units
                        SET status='failed', active_run_id=NULL, last_error=?, updated_at=?
                        WHERE unit_id=?
                        """,
                        (f"anomaly_killed: {anomaly_reason}", now, row["unit_id"]),
                    )
                    failed.append(
                        {
                            "unit_id": row["unit_id"],
                            "run_id": row["run_id"],
                            "exit_code": -99,
                            "oom": False,
                            "next_status": "failed",
                            "reserve_mb": None,
                            "anomaly": anomaly_reason,
                        }
                    )
                    self._notify_requester(
                        run_id=str(row["run_id"]),
                        status="anomaly_killed",
                        exit_code=-99,
                        log_path=row["log_path"],
                        target_id=str(row["target_id"]),
                        reason=anomaly_reason,
                        metrics_summary=log_tail[-500:] if log_tail else None,
                    )
                continue

            # Terminal state handling
            exit_code = int(status.get("exit_code", -1))
            now = _now_iso()
            conn.execute(
                """
                UPDATE runs
                SET state='exited', exit_code=?, finished_at=?, updated_at=?
                WHERE run_id=?
                """,
                (exit_code, now, now, row["run_id"]),
            )

            duration_seconds: float | None = None
            started_at = row["started_at"]
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at)
                    duration_seconds = (datetime.now(tz=UTC) - start_dt).total_seconds()
                except (ValueError, TypeError):
                    pass

            if exit_code == 0:
                conn.execute(
                    """
                    UPDATE units
                    SET status='done', active_run_id=NULL, last_error=NULL, updated_at=?
                    WHERE unit_id=?
                    """,
                    (now, row["unit_id"]),
                )
                completed.append({"unit_id": row["unit_id"], "run_id": row["run_id"]})
                self._notify_requester(
                    run_id=str(row["run_id"]),
                    status="completed",
                    exit_code=0,
                    log_path=row["log_path"],
                    target_id=str(row["target_id"]),
                    duration_seconds=duration_seconds,
                    metrics_summary=log_tail[-500:] if log_tail else None,
                )
                continue

            oom = is_oom(log_tail, exit_code)
            attempts = int(row["attempts"])
            max_retries = int(row["max_retries"])
            next_status = "pending" if oom and attempts <= max_retries else "failed"
            ceiling = gpu_capacity_ceiling(self._query_gpus, self._configured_target_ids())
            new_reserve = escalate_reserve(row, ceiling) if next_status == "pending" else None
            if next_status == "pending":
                error = (
                    f"OOM (exit={exit_code}); requeued with reserve_mb={new_reserve}"
                    if new_reserve is not None
                    else f"OOM (exit={exit_code}); requeued"
                )
            else:
                error = (
                    f"OOM retry budget exhausted (exit={exit_code})"
                    if oom
                    else f"exit_code={exit_code}"
                )
            if new_reserve is not None:
                conn.execute(
                    """
                    UPDATE units
                    SET status=?, active_run_id=NULL, last_error=?, reserve_mb=?, updated_at=?
                    WHERE unit_id=?
                    """,
                    (next_status, error, new_reserve, now, row["unit_id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE units
                    SET status=?, active_run_id=NULL, last_error=?, updated_at=?
                    WHERE unit_id=?
                    """,
                    (next_status, error, now, row["unit_id"]),
                )
            failed.append(
                {
                    "unit_id": row["unit_id"],
                    "run_id": row["run_id"],
                    "exit_code": exit_code,
                    "oom": oom,
                    "next_status": next_status,
                    "reserve_mb": new_reserve,
                }
            )
            if next_status == "failed":
                notify_status = "oom" if oom else ("killed" if exit_code < 0 else "failed")
                self._notify_requester(
                    run_id=str(row["run_id"]),
                    status=notify_status,
                    exit_code=exit_code,
                    log_path=row["log_path"],
                    target_id=str(row["target_id"]),
                    duration_seconds=duration_seconds,
                    metrics_summary=log_tail[-500:] if log_tail else None,
                )
        return completed, failed

