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
import re
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
    "killed",
    "sigkill",
    "signal 9",
    "signal: 9",
    "core dumped",
)
# Exit codes that almost always indicate the OS killed the process before it
# could write a CUDA/torch traceback. 137 = SIGKILL (OOM-killer), 139 = SIGSEGV
# (very common when a CUDA allocation fails partway through). Negative values
# come from subprocess wrappers that pass through the signal directly.
OOM_EXIT_CODES = frozenset({137, 139, -9, -11})
# Multiplier used when escalating a unit's reserve_mb after an OOM. We want
# enough headroom that the retry actually picks a bigger GPU, not the same
# one with the same nvidia-smi reading.
OOM_ESCALATION_FACTOR = 1.5
DEFAULT_MAX_RETRIES = 3

# Hard-metric anomaly detection
ANOMALY_NAN_PATTERN = re.compile(r"\b(nan|NaN|NAN|inf|Inf|INF)\b")
ANOMALY_LOSS_LINE_PATTERN = re.compile(r"(?i)(loss|train_loss|val_loss|nll|perplexity)")
# GPU utilization collapse: if 0% for this many seconds, kill the run.
GPU_UTIL_COLLAPSE_SECONDS = 300  # 5 minutes


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
    max_retries: int = DEFAULT_MAX_RETRIES
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
    # Number of pre-existing active runs (running/launching) on this GPU.
    # Used as the primary spread-first tie-break so an empty card always wins
    # over a card that already has work.
    active_run_count: int = 0
    # Speculative count of placements made within the current reconcile/plan,
    # so the second small unit doesn't pile back onto the GPU we just chose.
    new_run_count: int = 0

    @property
    def remaining_mb(self) -> int:
        return self.free_mb - self.running_reserved_mb - self.new_reserved_mb

    @property
    def total_run_count(self) -> int:
        """Live + speculative run count, used by spread-first tie-break."""
        return self.active_run_count + self.new_run_count


QueryGpusFn = Callable[[str], list[dict[str, Any]]]
ExpRunFn = Callable[[str, str, list[int] | None], dict[str, Any]]
ExpStatusFn = Callable[[str, str], dict[str, Any]]
ExpKillFn = Callable[[str, str], dict[str, Any]]


class _UnitRowView:
    """sqlite3.Row-shaped view over a ``QueueUnit`` for dry-run planning.

    ``_pick_candidate`` and ``_block_reason`` read units via ``unit["field"]``.
    The plan() entry point feeds them in-memory ``QueueUnit`` objects, so this
    shim translates field access without forcing a DB round-trip.
    """

    __slots__ = ("_unit",)

    def __init__(self, unit: QueueUnit) -> None:
        self._unit = unit

    def __getitem__(self, key: str) -> Any:
        unit = self._unit
        if key == "target_id":
            return unit.target_id
        if key == "gpu_ids_json":
            return _json_dumps(unit.gpu_ids) if unit.gpu_ids is not None else None
        if key == "gpus_needed":
            return max(1, int(unit.gpus_needed))
        if key == "min_free_mb":
            return max(0, int(unit.min_free_mb))
        if key == "reserve_mb":
            return unit.reserve_mb
        raise KeyError(key)


# A unit "row" the placement logic can read. Either a real sqlite3.Row (when
# called from reconcile) or an in-memory view (when called from plan()).
UnitLike = sqlite3.Row | _UnitRowView


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
        exp_kill_fn: ExpKillFn | None = None,
    ) -> None:
        self.project_port = project_port
        self.db_path = db_path or default_db_path(_resolve_project_port(project_port))
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
            placement = self._placement_summary(conn, launched, slots)

        return {
            "launched": launched,
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "placement": placement,
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
                           pid, exit_code, log_path, started_at, finished_at
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
        evict: bool = False,
        reason: str | None = None,
        reconcile: bool = True,
    ) -> dict[str, Any]:
        """Set the dynamic allow-list of GPUs available for new runs.

        ``evict=False`` (default, "drain" mode): GPUs removed from the allowlist
        get marked ``draining=1`` so no *new* placements land on them, but any
        run already on those cards is left alone to finish naturally. Use this
        when an operator says "I'll need these cards back, but only after
        what's running there is done."

        ``evict=True`` ("evict" mode): same allowlist update, plus every run
        currently on a removed GPU receives ``exp_kill`` (SIGTERM) so the
        process can checkpoint and exit, the run is recorded as ``evicted``
        with exit code -15, and its unit is reset to ``pending`` (without
        consuming the OOM retry budget or escalating ``reserve_mb`` — this is
        an operator-driven move, not a failure). The next reconcile reissues
        those units onto the remaining allowed GPUs. Caller is responsible
        for making sure their command traps SIGTERM and writes a checkpoint;
        this is documented in ``allocate-resources``.
        """
        targets = self._target_ids_for_pool(target_id)
        now = _now_iso()
        changed: dict[str, Any] = {}
        evicted_runs: list[dict[str, Any]] = []
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
                if evict:
                    evicted_runs.extend(
                        self._evict_runs_off_gpus(conn, tid, removed_gpus=seen_ids - allowed)
                    )
        result: dict[str, Any] = {"changed": changed}
        if evict:
            result["evicted"] = evicted_runs
        if reconcile:
            result["reconcile"] = self.reconcile()
        return result

    def _evict_runs_off_gpus(
        self,
        conn: sqlite3.Connection,
        target_id: str,
        *,
        removed_gpus: set[int],
    ) -> list[dict[str, Any]]:
        """SIGTERM every run on *removed_gpus* and reset their units to pending.

        Called from ``set_gpu_pool(evict=True)``. Critical contract: this is
        an operator-driven move, **not a failure**, so we do NOT escalate
        ``reserve_mb``, do NOT count an attempt, and do NOT mark the unit
        ``failed``. The run row is recorded with ``state='evicted'`` and
        ``exit_code=-15`` so ``_refresh_running`` (which only inspects
        ``running`` / ``launching``) skips it on the next pass.
        """
        if not removed_gpus:
            return []
        active = conn.execute(
            """
            SELECT r.run_id, r.unit_id, r.batch_id, r.gpu_ids_json, r.target_id
            FROM runs r
            WHERE r.state IN ('running', 'launching') AND r.target_id=?
            """,
            (target_id,),
        ).fetchall()
        evicted: list[dict[str, Any]] = []
        now = _now_iso()
        for row in active:
            run_gpus = {int(g) for g in _json_loads(row["gpu_ids_json"], [])}
            if not (run_gpus & removed_gpus):
                continue
            try:
                self._exp_kill(target_id, str(row["run_id"]))
                kill_error = None
            except Exception as exc:
                kill_error = str(exc)
                logger.warning("exp_kill failed during evict run_id=%s: %s", row["run_id"], exc)
            conn.execute(
                """
                UPDATE runs
                SET state='evicted', exit_code=-15, finished_at=?, updated_at=?
                WHERE run_id=?
                """,
                (now, now, row["run_id"]),
            )
            # Decrement attempts so the eviction itself doesn't burn retry budget.
            conn.execute(
                """
                UPDATE units
                SET status='pending',
                    active_run_id=NULL,
                    last_error='evicted by gpu_pool change; will be requeued',
                    attempts=MAX(0, attempts - 1),
                    updated_at=?
                WHERE unit_id=?
                """,
                (now, row["unit_id"]),
            )
            evicted.append(
                {
                    "run_id": row["run_id"],
                    "unit_id": row["unit_id"],
                    "batch_id": row["batch_id"],
                    "target_id": target_id,
                    "evicted_from_gpus": sorted(run_gpus & removed_gpus),
                    "kill_error": kill_error,
                }
            )
        return evicted

    def gpu_pool(self) -> dict[str, Any]:
        """Return current allowed/draining GPU pool records.

        Also enumerates active runs (``state in {'running','launching'}``)
        currently sitting on draining GPUs so operators can see how much
        work still has to clear before a drain is complete.
        """
        with self._connect() as conn:
            overrides = [dict(row) for row in conn.execute("SELECT * FROM gpu_pool").fetchall()]
            active = conn.execute(
                """
                SELECT r.run_id, r.unit_id, r.batch_id, r.target_id, r.gpu_ids_json,
                       r.state, r.started_at
                FROM runs r
                WHERE r.state IN ('running', 'launching')
                """
            ).fetchall()
        draining_keys = {
            (str(row["target_id"]), int(row["gpu_id"]))
            for row in overrides
            if int(row["draining"]) == 1 or int(row["enabled"]) == 0
        }
        draining_runs: list[dict[str, Any]] = []
        for row in active:
            target_id = str(row["target_id"])
            for gpu_id in _json_loads(row["gpu_ids_json"], []):
                if (target_id, int(gpu_id)) in draining_keys:
                    draining_runs.append(
                        {
                            "run_id": row["run_id"],
                            "unit_id": row["unit_id"],
                            "batch_id": row["batch_id"],
                            "target_id": target_id,
                            "gpu_id": int(gpu_id),
                            "state": row["state"],
                            "started_at": row["started_at"],
                        }
                    )
                    break
        return {
            "default": "all GPUs enabled when no row exists for a target",
            "overrides": overrides,
            "draining_runs": draining_runs,
        }

    def plan(self, units: list[QueueUnit]) -> dict[str, Any]:
        """Dry-run: where would these units land if submitted right now?

        Read-only. Does not write to the queue, does not call ``exp_run``, does
        not touch the unit table. Reuses the live ``_gpu_slots`` snapshot
        (running-job reserves already deducted) and ``_pick_candidate`` so
        callers see the same decision the next ``reconcile`` would make.

        Units are simulated **in order**. Each fitting unit's ``reserve_mb`` is
        speculatively deducted from the snapshot before the next unit is
        considered, so multi-unit submits are predicted correctly: caller can
        see, e.g. "submitting 5 units would land 4 and stall 1 for capacity".
        """
        with self._connect() as conn:
            slots = self._gpu_slots(conn)

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
            candidate = self._pick_candidate(view, slots)
            if candidate is None:
                placements.append(
                    {
                        "unit_index": idx,
                        "status": "blocked",
                        "reason": self._block_reason(view),
                    }
                )
                continue
            target_id, gpu_ids, reserve_mb = candidate
            self._reserve_slots(slots, target_id, gpu_ids, reserve_mb)
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

        return exp_run(ExpRunArgs(target_id=target_id, cmd=cmd, gpu_ids=gpu_ids))

    def _exp_status(self, target_id: str, run_id: str) -> dict[str, Any]:
        if self._exp_status_fn is not None:
            return self._exp_status_fn(target_id, run_id)
        from minions.tools.experiment_ssh import ExpStatusArgs, exp_status

        return exp_status(ExpStatusArgs(target_id=target_id, run_id=run_id))

    def _exp_kill(self, target_id: str, run_id: str) -> dict[str, Any]:
        if self._exp_kill_fn is not None:
            return self._exp_kill_fn(target_id, run_id)
        from minions.tools.experiment_ssh import ExpKillArgs, exp_kill

        return exp_kill(ExpKillArgs(target_id=target_id, run_id=run_id))

    def _resolve_port(self) -> int | None:
        """Best-effort resolution of the project port for EACN notifications."""
        if self.project_port is not None:
            return self.project_port
        raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
        return int(raw) if raw.isdigit() else None

    def _notify_coder(
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
        """Best-effort EACN notification to the coder agent on experiment completion.

        Sends a structured message so Coder can react to results without polling.
        Failures are logged but never raised — notification is advisory.
        """
        port = self._resolve_port()
        if port is None:
            logger.debug("_notify_coder: no project port, skipping notification for %s", run_id)
            return
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
                to_agent_id="coder",
                from_agent_id="scheduler",
                content=payload,
                timeout=5.0,
            )
            logger.info("Notified coder: run_id=%s status=%s on port %d", run_id, status, port)
        except Exception as exc:
            logger.warning(
                "Failed to notify coder for run_id=%s status=%s: %s", run_id, status, exc
            )

    def _check_hard_anomalies(
        self,
        run_id: str,
        target_id: str,
        log_tail: str,
    ) -> str | None:
        """Check for hard-metric anomalies in a running experiment's log tail.

        Returns a reason string if an anomaly is detected, None otherwise.
        Checks:
        - NaN/Inf in loss-related log lines
        - GPU utilization collapse (0% for > 5 minutes) — detected via log patterns
        """
        # Check for NaN/Inf in loss-related lines
        for line in log_tail.splitlines():
            if ANOMALY_LOSS_LINE_PATTERN.search(line) and ANOMALY_NAN_PATTERN.search(line):
                return f"NaN/Inf detected in loss metric: {line.strip()[:120]}"

        # Check for GPU utilization collapse pattern in logs
        # Common patterns: "GPU utilization: 0%", "gpu_util=0", "utilization.gpu [%]: 0"
        gpu_zero_pattern = re.compile(
            r"(?i)(gpu[_ ]?util\w*\s*[:=]\s*0[%\s]|utilization\.gpu\s*\[%\]\s*:\s*0\b)"
        )
        zero_util_lines = [line for line in log_tail.splitlines() if gpu_zero_pattern.search(line)]
        # If the last 10+ lines of GPU util are all 0%, likely collapsed
        if len(zero_util_lines) >= 10:
            return "GPU utilization collapsed to 0% (sustained in recent log tail)"

        return None

    def _refresh_running(self, conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
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

            # --- Hard-metric anomaly detection for still-running experiments ---
            if status.get("state") != "exited":
                anomaly_reason = self._check_hard_anomalies(
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
                    self._notify_coder(
                        run_id=str(row["run_id"]),
                        status="anomaly_killed",
                        exit_code=-99,
                        log_path=row["log_path"],
                        target_id=str(row["target_id"]),
                        reason=anomaly_reason,
                        metrics_summary=log_tail[-500:] if log_tail else None,
                    )
                continue

            # --- Terminal state handling ---
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

            # Compute duration if started_at is available
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
                self._notify_coder(
                    run_id=str(row["run_id"]),
                    status="completed",
                    exit_code=0,
                    log_path=row["log_path"],
                    target_id=str(row["target_id"]),
                    duration_seconds=duration_seconds,
                    metrics_summary=log_tail[-500:] if log_tail else None,
                )
                continue

            is_oom = self._is_oom(log_tail, exit_code)
            attempts = int(row["attempts"])
            max_retries = int(row["max_retries"])
            next_status = "pending" if is_oom and attempts <= max_retries else "failed"
            new_reserve = self._escalate_reserve(row) if next_status == "pending" else None
            if next_status == "pending":
                error = (
                    f"OOM (exit={exit_code}); requeued with reserve_mb={new_reserve}"
                    if new_reserve is not None
                    else f"OOM (exit={exit_code}); requeued"
                )
            else:
                error = (
                    f"OOM retry budget exhausted (exit={exit_code})"
                    if is_oom
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
                    "oom": is_oom,
                    "next_status": next_status,
                    "reserve_mb": new_reserve,
                }
            )
            # Notify coder for terminal failures (not OOM retries)
            if next_status == "failed":
                notify_status = "oom" if is_oom else ("killed" if exit_code < 0 else "failed")
                self._notify_coder(
                    run_id=str(row["run_id"]),
                    status=notify_status,
                    exit_code=exit_code,
                    log_path=row["log_path"],
                    target_id=str(row["target_id"]),
                    duration_seconds=duration_seconds,
                    metrics_summary=log_tail[-500:] if log_tail else None,
                )
        return completed, failed

    def _gpu_slots(self, conn: sqlite3.Connection) -> list[GpuSlot]:
        pool = {
            (str(row["target_id"]), int(row["gpu_id"])): row
            for row in conn.execute("SELECT * FROM gpu_pool").fetchall()
        }
        running_reservations: dict[tuple[str, int], int] = {}
        running_run_counts: dict[tuple[str, int], int] = {}
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
                running_run_counts[key] = running_run_counts.get(key, 0) + 1

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
                        active_run_count=running_run_counts.get(key, 0),
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
        unit: UnitLike,
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
            # Spread-first tie-break: an idle GPU always beats a GPU that
            # already has live or speculative runs on it; only after run-count
            # ties do we prefer the GPU with more headroom. Without this the
            # "fattest GPU first" rule piles every small unit onto whichever
            # card happens to start with the most free VRAM.
            slot = sorted(
                candidates,
                key=lambda s: (s.total_run_count, -s.remaining_mb, s.target_id, s.gpu_id),
            )[0]
            return slot.target_id, [slot.gpu_id], reserve_mb

        by_target: dict[str, list[GpuSlot]] = {}
        for slot in candidates:
            by_target.setdefault(slot.target_id, []).append(slot)
        target_options: list[tuple[tuple[int, int], str, list[GpuSlot]]] = []
        for target_id, target_slots in by_target.items():
            ordered = sorted(
                target_slots,
                key=lambda s: (s.total_run_count, -s.remaining_mb, s.gpu_id),
            )
            if len(ordered) >= gpus_needed:
                chosen = ordered[:gpus_needed]
                # Score: (sum of run counts ascending, sum of remaining descending)
                target_options.append(
                    (
                        (
                            sum(s.total_run_count for s in chosen),
                            -sum(s.remaining_mb for s in chosen),
                        ),
                        target_id,
                        chosen,
                    )
                )
        if not target_options:
            return None
        _score, target_id, chosen = sorted(target_options, key=lambda x: (x[0], x[1]))[0]
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
                slot.new_run_count += 1

    def _note_no_capacity(self, conn: sqlite3.Connection, unit: sqlite3.Row) -> None:
        reason = self._block_reason(unit)
        conn.execute(
            "UPDATE units SET last_error=?, updated_at=? WHERE unit_id=?",
            (reason, _now_iso(), unit["unit_id"]),
        )

    def _block_reason(self, unit: UnitLike) -> str:
        """Classify why a pending unit could not be placed this reconcile.

        Returns a short tag that is also stored in ``units.last_error`` so the
        placement summary and any human reading the queue can see *why* a unit
        is stuck — not just that it is.
        """
        target_constraint = str(unit["target_id"] or "auto")
        if target_constraint != "auto" and target_constraint not in self._configured_target_ids():
            return f"target_pin: {target_constraint!r} not in active fleet"
        if unit["gpu_ids_json"]:
            return "explicit_gpu: pinned GPUs not available in current pool"
        return "no_capacity: no allowed GPU has enough free VRAM"

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

    def _placement_summary(
        self,
        conn: sqlite3.Connection,
        launched: list[dict[str, Any]],
        slots_at_start: list[GpuSlot],
    ) -> dict[str, Any]:
        """Summarize how this reconcile spread work and why pending units stuck.

        - ``by_gpu`` — current physical distribution of all live runs, keyed by
          ``"<target_id>:<gpu_id>"``. Helps spot pile-ups.
        - ``blocked_reasons`` — count of pending units grouped by classification
          tag (``no_capacity`` / ``target_pin`` / ``explicit_gpu``).
        - ``skew_warning`` — non-empty string if **this** reconcile launched
          more than one unit but pinned them all to a single GPU while other
          GPUs in the same target had room. That is the SYSTEM.md "spread-first"
          rule failing in practice; the skill layer should reflect on it.
        """
        by_gpu: dict[str, dict[str, int]] = {}
        active_rows = conn.execute(
            """
            SELECT target_id, gpu_ids_json, state
            FROM runs
            WHERE state IN ('running', 'launching')
            """
        ).fetchall()
        for row in active_rows:
            target_id = str(row["target_id"])
            state = str(row["state"])
            for gpu_id in _json_loads(row["gpu_ids_json"], []):
                key = f"{target_id}:{int(gpu_id)}"
                bucket = by_gpu.setdefault(key, {"running": 0, "launching": 0})
                bucket[state] = bucket.get(state, 0) + 1

        blocked_reasons: dict[str, int] = {}
        pending_rows = conn.execute(
            "SELECT last_error FROM units WHERE status='pending'"
        ).fetchall()
        for row in pending_rows:
            err = str(row["last_error"] or "")
            tag = err.split(":", 1)[0].strip() if err else "uninspected"
            blocked_reasons[tag] = blocked_reasons.get(tag, 0) + 1

        skew_warning = ""
        if len(launched) >= 2:
            placements = {(d["target_id"], tuple(d["gpu_ids"])) for d in launched}
            if len(placements) == 1:
                target_id, gpu_ids = next(iter(placements))
                same_target_slots = [s for s in slots_at_start if s.target_id == target_id]
                if len(same_target_slots) > len(gpu_ids):
                    skew_warning = (
                        f"{len(launched)} launches concentrated on "
                        f"{target_id}:{list(gpu_ids)} while {len(same_target_slots)} "
                        f"GPUs were available on that target — re-check spread-first"
                    )

        return {
            "by_gpu": by_gpu,
            "blocked_reasons": blocked_reasons,
            "skew_warning": skew_warning,
        }

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

    def _unit_reserve_mb(self, unit: UnitLike) -> int:
        reserve = unit["reserve_mb"]
        if reserve is not None:
            return max(0, int(reserve))
        min_free = int(unit["min_free_mb"] or 0)
        return max(min_free, DEFAULT_RESERVE_MB)

    def _is_oom(self, log_tail: str, exit_code: int | None = None) -> bool:
        """Return True if the run almost certainly died from a memory issue.

        Considers two signals: the log tail (CUDA / torch traceback strings) and
        the exit code (OS-level OOM-killer is SIGKILL → 137; CUDA allocation
        faults often produce SIGSEGV → 139). The exit-code branch matters when
        a process is killed before it has a chance to flush a traceback.
        """
        if exit_code is not None and int(exit_code) in OOM_EXIT_CODES:
            return True
        lowered = log_tail.lower()
        return any(needle in lowered for needle in OOM_NEEDLES)

    def _gpu_capacity_ceiling(self) -> int | None:
        """Largest single-GPU total VRAM in the active fleet, in MB.

        Used to cap escalated reserves so we never request more memory than
        any single GPU has. ``None`` means we lack the information and should
        fall back to a sane absolute cap.
        """
        ceiling = 0
        for target_id in self._configured_target_ids():
            try:
                gpus = self._query_gpus(target_id)
            except Exception as exc:
                logger.debug("query_gpus failed during reserve cap: %s", exc)
                continue
            for gpu in gpus:
                total = gpu.get("total_mb")
                if isinstance(total, int) and total > ceiling:
                    ceiling = total
        return ceiling or None

    def _escalate_reserve(self, unit_row: sqlite3.Row) -> int:
        """Bump a unit's ``reserve_mb`` after an OOM so its retry picks a roomier GPU.

        Multiplies the *current effective reserve* by ``OOM_ESCALATION_FACTOR``
        and clamps to 95% of the largest GPU's total VRAM. The escalation is
        persisted on the unit row, so the next reconcile's ``_pick_candidate``
        actually requires the bigger headroom.
        """
        current = self._unit_reserve_mb(unit_row)
        bumped = max(current + 1024, int(current * OOM_ESCALATION_FACTOR))
        ceiling = self._gpu_capacity_ceiling()
        if ceiling is not None:
            bumped = min(bumped, int(ceiling * 0.95))
        return max(bumped, current)
