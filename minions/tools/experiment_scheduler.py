"""Project-level experiment queue and GPU packing scheduler.

The Experimenter role should not spend context manually deciding which GPU gets
the next run. This module keeps a durable project queue in SQLite and performs a
simple "fluid gravity" reconcile: every pending unit is considered against the
current fleet, and any allowed GPU with capacity can absorb the next runnable
unit.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.config import load_experiment_targets
from minions.errors import ConfigError
from minions.paths import project_artifacts_dir

logger = logging.getLogger(__name__)

DEFAULT_RESERVE_MB = 8192
OOM_NEEDLES = (
    "out of memory",
    "cuda out of memory",
    "cublas_status_alloc_failed",
    "hip out of memory",
    "oom",
)


@dataclass(frozen=True)
class QueueUnit:
    """One runnable experiment unit."""

    cmd: str
    target_id: str = "auto"
    gpu_ids: list[int] | None = None
    gpus_needed: int = 1
    min_free_mb: int = 0
    reserve_mb: int | None = None
    priority: int = 0
    max_retries: int = 1
    metadata: dict[str, Any] | None = None


@dataclass
class GpuSlot:
    """Mutable scheduling view for one GPU."""

    target_id: str
    gpu_id: int
    free_mb: int
    total_mb: int | None = None
    running_reserved_mb: int = 0
    new_reserved_mb: int = 0

    @property
    def remaining_mb(self) -> int:
        return self.free_mb - self.running_reserved_mb - self.new_reserved_mb


QueryGpusFn = Callable[[str], list[dict[str, Any]]]
ExpRunFn = Callable[[str, str, list[int] | None], dict[str, Any]]
ExpStatusFn = Callable[[str, str], dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _resolve_project_port(project_port: int | None = None) -> int:
    if project_port is not None:
        return project_port
    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    raise ConfigError(
        "Experiment queue tools require MINIONS_PROJECT_PORT or an explicit project_port."
    )


def default_db_path(project_port: int) -> Path:
    """Return the durable scheduler DB path for a project."""
    return project_artifacts_dir(project_port) / "experimenter" / "scheduler.sqlite"


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
    ) -> None:
        self.project_port = project_port
        self.db_path = db_path or default_db_path(_resolve_project_port(project_port))
        self._target_ids = list(target_ids) if target_ids is not None else None
        self._query_gpus_fn = query_gpus_fn
        self._exp_run_fn = exp_run_fn
        self._exp_status_fn = exp_status_fn
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
        bid = batch_id or _new_id("batch")
        now = _now_iso()
        unit_ids: list[str] = []
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO batches(
                    batch_id, requester, metadata_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, 'active', ?, ?)
                ON CONFLICT(batch_id) DO NOTHING
                """,
                (bid, requester, _json_dumps(metadata or {}), now, now),
            )
            for unit in units:
                unit_id = _new_id("unit")
                unit_ids.append(unit_id)
                conn.execute(
                    """
                    INSERT INTO units(
                        unit_id, batch_id, cmd, target_id, gpu_ids_json, gpus_needed,
                        min_free_mb, reserve_mb, priority, status, attempts, max_retries,
                        metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                    """,
                    (
                        unit_id,
                        bid,
                        unit.cmd,
                        unit.target_id,
                        _json_dumps(unit.gpu_ids) if unit.gpu_ids is not None else None,
                        max(1, int(unit.gpus_needed)),
                        max(0, int(unit.min_free_mb)),
                        unit.reserve_mb,
                        int(unit.priority),
                        max(0, int(unit.max_retries)),
                        _json_dumps(unit.metadata or {}),
                        now,
                        now,
                    ),
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
        blocked: list[dict[str, Any]] = []

        with self._tx() as conn:
            completed, failed = self._refresh_running(conn)
            slots = self._gpu_slots(conn)
            pending = self._pending_units(conn, batch_id=batch_id)

            for unit in pending:
                candidate = self._pick_candidate(unit, slots)
                if candidate is None:
                    self._note_no_capacity(conn, unit)
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
                self._reserve_slots(slots, target_id, gpu_ids, reserve_mb)
                launched.append(
                    {
                        "unit_id": unit["unit_id"],
                        "batch_id": unit["batch_id"],
                        "run_id": run_id,
                        "target_id": target_id,
                        "gpu_ids": gpu_ids,
                    }
                )

            self._refresh_batches(conn)
            if batch_id is None:
                blocked = self._blocked_units(conn)
            else:
                blocked = self._blocked_units(conn, batch_id=batch_id)

        return {
            "launched": launched,
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "summary": self.status(batch_id=batch_id)["summary"],
        }

    def status(self, batch_id: str | None = None) -> dict[str, Any]:
        """Return a compact queue status for one batch or the whole project."""
        where = ""
        params: tuple[Any, ...] = ()
        if batch_id:
            where = "WHERE batch_id=?"
            params = (batch_id,)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT status, COUNT(*) AS n
                FROM units
                {where}
                GROUP BY status
                ORDER BY status
                """,
                params,
            ).fetchall()
            summary = {str(row["status"]): int(row["n"]) for row in rows}
            units = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT unit_id, batch_id, status, priority, attempts, max_retries,
                           target_id, gpu_ids_json, active_run_id, last_error, updated_at
                    FROM units
                    {where}
                    ORDER BY priority DESC, created_at ASC
                    """,
                    params,
                ).fetchall()
            ]
            runs = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT run_id, unit_id, batch_id, target_id, gpu_ids_json, state,
                           exit_code, log_path, started_at, finished_at
                    FROM runs
                    {where}
                    ORDER BY started_at ASC
                    """,
                    params,
                ).fetchall()
            ]
        for unit in units:
            unit["gpu_ids"] = _json_loads(unit.pop("gpu_ids_json"), None)
        for run in runs:
            run["gpu_ids"] = _json_loads(run.pop("gpu_ids_json"), [])
        return {
            "batch_id": batch_id,
            "summary": summary,
            "units": units,
            "runs": runs,
        }

    def set_gpu_pool(
        self,
        *,
        target_id: str = "all",
        allowed_gpu_ids: list[int] | str = "all",
        draining: bool = True,
        reason: str | None = None,
        reconcile: bool = True,
    ) -> dict[str, Any]:
        """Set the dynamic allow-list of GPUs available for new runs."""
        targets = self._target_ids_for_pool(target_id)
        now = _now_iso()
        changed: dict[str, Any] = {}
        with self._tx() as conn:
            for tid in targets:
                if allowed_gpu_ids == "all":
                    conn.execute("DELETE FROM gpu_pool WHERE target_id=?", (tid,))
                    changed[tid] = "all"
                    continue
                allowed = {int(g) for g in allowed_gpu_ids}
                seen_ids = {int(g["id"]) for g in self._query_gpus(tid)}
                for gpu_id in sorted(seen_ids | allowed):
                    conn.execute(
                        """
                        INSERT INTO gpu_pool(
                            target_id, gpu_id, enabled, draining, reason, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(target_id, gpu_id)
                        DO UPDATE SET enabled=excluded.enabled,
                                      draining=excluded.draining,
                                      reason=excluded.reason,
                                      updated_at=excluded.updated_at
                        """,
                        (
                            tid,
                            gpu_id,
                            1 if gpu_id in allowed else 0,
                            0 if gpu_id in allowed else int(draining),
                            reason,
                            now,
                        ),
                    )
                changed[tid] = sorted(allowed)
        result: dict[str, Any] = {"changed": changed}
        if reconcile:
            result["reconcile"] = self.reconcile()
        return result

    def gpu_pool(self) -> dict[str, Any]:
        """Return current allowed/draining GPU pool records."""
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM gpu_pool").fetchall()]
        return {"default": "all GPUs enabled when no row exists for a target", "overrides": rows}

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
                """
            )

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
        return [target.id for target in cfg.targets]

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

        return exp_run(ExpRunArgs(target_id=target_id, cmd=cmd, gpu_ids=gpu_ids))

    def _exp_status(self, target_id: str, run_id: str) -> dict[str, Any]:
        if self._exp_status_fn is not None:
            return self._exp_status_fn(target_id, run_id)
        from minions.tools.experiment_ssh import ExpStatusArgs, exp_status

        return exp_status(ExpStatusArgs(target_id=target_id, run_id=run_id))

    def _refresh_running(self, conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
        completed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        rows = conn.execute(
            """
            SELECT r.run_id, r.unit_id, r.batch_id, r.target_id, u.attempts, u.max_retries
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
            if status.get("state") != "exited":
                continue
            exit_code = int(status.get("exit_code", -1))
            log_tail = str(status.get("log_tail") or "")
            now = _now_iso()
            conn.execute(
                """
                UPDATE runs
                SET state='exited', exit_code=?, finished_at=?, updated_at=?
                WHERE run_id=?
                """,
                (exit_code, now, now, row["run_id"]),
            )
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
                continue

            is_oom = self._is_oom(log_tail)
            attempts = int(row["attempts"])
            max_retries = int(row["max_retries"])
            next_status = "pending" if is_oom and attempts <= max_retries else "failed"
            error = "OOM; requeued" if next_status == "pending" else f"exit_code={exit_code}"
            if is_oom and next_status == "failed":
                error = "OOM retry budget exhausted"
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
                    "oom": is_oom,
                    "next_status": next_status,
                }
            )
        return completed, failed

    def _gpu_slots(self, conn: sqlite3.Connection) -> list[GpuSlot]:
        pool = {
            (str(row["target_id"]), int(row["gpu_id"])): row
            for row in conn.execute("SELECT * FROM gpu_pool").fetchall()
        }
        running_reservations: dict[tuple[str, int], int] = {}
        running_rows = conn.execute(
            """
            SELECT r.target_id, r.gpu_ids_json, u.reserve_mb, u.min_free_mb
            FROM runs r
            JOIN units u ON u.unit_id = r.unit_id
            WHERE r.state IN ('running', 'launching')
            """
        ).fetchall()
        for row in running_rows:
            reserve_mb = self._unit_reserve_mb(row)
            for gpu_id in _json_loads(row["gpu_ids_json"], []):
                key = (str(row["target_id"]), int(gpu_id))
                running_reservations[key] = running_reservations.get(key, 0) + reserve_mb

        slots: list[GpuSlot] = []
        for target_id in self._configured_target_ids():
            for gpu in self._query_gpus(target_id):
                gpu_id = int(gpu["id"])
                override = pool.get((target_id, gpu_id))
                if override is not None and (
                    int(override["enabled"]) == 0 or int(override["draining"]) == 1
                ):
                    continue
                key = (target_id, gpu_id)
                slots.append(
                    GpuSlot(
                        target_id=target_id,
                        gpu_id=gpu_id,
                        free_mb=int(gpu.get("free_mb") or 0),
                        total_mb=int(gpu["total_mb"]) if gpu.get("total_mb") is not None else None,
                        running_reserved_mb=running_reservations.get(key, 0),
                    )
                )
        return slots

    def _pending_units(
        self,
        conn: sqlite3.Connection,
        batch_id: str | None = None,
    ) -> list[sqlite3.Row]:
        where = "WHERE status='pending'"
        params: tuple[Any, ...] = ()
        if batch_id is not None:
            where += " AND batch_id=?"
            params = (batch_id,)
        return conn.execute(
            f"""
            SELECT *
            FROM units
            {where}
            ORDER BY priority DESC, created_at ASC
            """,
            params,
        ).fetchall()

    def _pick_candidate(
        self,
        unit: sqlite3.Row,
        slots: list[GpuSlot],
    ) -> tuple[str, list[int], int] | None:
        reserve_mb = self._unit_reserve_mb(unit)
        min_free_mb = int(unit["min_free_mb"])
        target_constraint = str(unit["target_id"] or "auto")
        explicit_gpus = _json_loads(unit["gpu_ids_json"], None)
        gpus_needed = max(1, int(unit["gpus_needed"]))

        candidates = [
            slot
            for slot in slots
            if (target_constraint == "auto" or slot.target_id == target_constraint)
            and slot.remaining_mb >= max(min_free_mb, reserve_mb)
        ]
        if explicit_gpus is not None:
            explicit = {int(g) for g in explicit_gpus}
            candidates = [slot for slot in candidates if slot.gpu_id in explicit]
        if not candidates:
            return None

        if explicit_gpus is not None:
            by_target: dict[str, list[GpuSlot]] = {}
            for slot in candidates:
                by_target.setdefault(slot.target_id, []).append(slot)
            for target_id, target_slots in by_target.items():
                ids = {slot.gpu_id for slot in target_slots}
                explicit_ids = [int(g) for g in explicit_gpus]
                if all(gpu_id in ids for gpu_id in explicit_ids):
                    return target_id, explicit_ids, reserve_mb
            return None

        if gpus_needed == 1:
            slot = sorted(candidates, key=lambda s: (-s.remaining_mb, s.target_id, s.gpu_id))[0]
            return slot.target_id, [slot.gpu_id], reserve_mb

        by_target: dict[str, list[GpuSlot]] = {}
        for slot in candidates:
            by_target.setdefault(slot.target_id, []).append(slot)
        target_options: list[tuple[int, str, list[GpuSlot]]] = []
        for target_id, target_slots in by_target.items():
            ordered = sorted(target_slots, key=lambda s: (-s.remaining_mb, s.gpu_id))
            if len(ordered) >= gpus_needed:
                chosen = ordered[:gpus_needed]
                target_options.append((sum(s.remaining_mb for s in chosen), target_id, chosen))
        if not target_options:
            return None
        _score, target_id, chosen = sorted(target_options, key=lambda x: (-x[0], x[1]))[0]
        return target_id, sorted(slot.gpu_id for slot in chosen), reserve_mb

    def _reserve_slots(
        self,
        slots: list[GpuSlot],
        target_id: str,
        gpu_ids: list[int],
        reserve_mb: int,
    ) -> None:
        gpu_set = set(gpu_ids)
        for slot in slots:
            if slot.target_id == target_id and slot.gpu_id in gpu_set:
                slot.new_reserved_mb += reserve_mb

    def _note_no_capacity(self, conn: sqlite3.Connection, unit: sqlite3.Row) -> None:
        reason = "no allowed GPU currently satisfies target/gpu/memory constraints"
        conn.execute(
            "UPDATE units SET last_error=?, updated_at=? WHERE unit_id=?",
            (reason, _now_iso(), unit["unit_id"]),
        )

    def _blocked_units(
        self,
        conn: sqlite3.Connection,
        batch_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where = "WHERE status IN ('blocked', 'failed')"
        params: tuple[Any, ...] = ()
        if batch_id is not None:
            where += " AND batch_id=?"
            params = (batch_id,)
        return [
            dict(row)
            for row in conn.execute(
                f"SELECT unit_id, batch_id, status, last_error FROM units {where}",
                params,
            ).fetchall()
        ]

    def _refresh_batches(self, conn: sqlite3.Connection) -> None:
        batch_ids = [
            row["batch_id"] for row in conn.execute("SELECT batch_id FROM batches").fetchall()
        ]
        now = _now_iso()
        for batch_id in batch_ids:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM units WHERE batch_id=? GROUP BY status",
                (batch_id,),
            ).fetchall()
            counts = {str(row["status"]): int(row["n"]) for row in rows}
            if counts and set(counts) <= {"done"}:
                status = "done"
            elif counts and set(counts) <= {"done", "failed", "blocked"}:
                status = "completed_with_failures"
            else:
                status = "active"
            conn.execute(
                "UPDATE batches SET status=?, updated_at=? WHERE batch_id=?",
                (status, now, batch_id),
            )

    def _unit_reserve_mb(self, unit: sqlite3.Row) -> int:
        reserve = unit["reserve_mb"]
        if reserve is not None:
            return max(0, int(reserve))
        min_free = int(unit["min_free_mb"] or 0)
        return max(min_free, DEFAULT_RESERVE_MB)

    def _is_oom(self, log_tail: str) -> bool:
        lowered = log_tail.lower()
        return any(needle in lowered for needle in OOM_NEEDLES)
