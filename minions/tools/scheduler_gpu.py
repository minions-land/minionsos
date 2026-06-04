"""GPU pool management and slot allocation for experiment scheduler.

Handles dynamic GPU allow/deny lists, draining, eviction, and slot snapshots.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from minions.tools.scheduler_helpers import _json_loads, _now_iso

logger = logging.getLogger(__name__)


@dataclass
class GpuSlot:
    """Mutable scheduling view for one GPU."""

    target_id: str
    gpu_id: int
    free_mb: int
    total_mb: int | None = None
    running_reserved_mb: int = 0
    new_reserved_mb: int = 0
    active_run_count: int = 0
    new_run_count: int = 0

    @property
    def remaining_mb(self) -> int:
        return self.free_mb - self.running_reserved_mb - self.new_reserved_mb

    @property
    def total_run_count(self) -> int:
        """Live + speculative run count, used by spread-first tie-break."""
        return self.active_run_count + self.new_run_count


def build_gpu_slots(
    conn: sqlite3.Connection,
    query_gpus_fn: Any,
    target_ids: list[str],
) -> list[GpuSlot]:
    """Build current GPU slot snapshot with running reservations deducted."""
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
        reserve_mb = _unit_reserve_mb(row)
        for gpu_id in _json_loads(row["gpu_ids_json"], []):
            key = (str(row["target_id"]), int(gpu_id))
            running_reservations[key] = running_reservations.get(key, 0) + reserve_mb
            running_run_counts[key] = running_run_counts.get(key, 0) + 1

    slots: list[GpuSlot] = []
    for target_id in target_ids:
        for gpu in query_gpus_fn(target_id):
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


def set_gpu_pool(
    conn: sqlite3.Connection,
    query_gpus_fn: Any,
    exp_kill_fn: Any,
    target_ids: list[str],
    *,
    target_id: str = "all",
    allowed_gpu_ids: list[int] | str = "all",
    draining: bool = True,
    evict: bool = False,
    reason: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Set GPU pool allowlist and optionally evict runs from removed GPUs.

    Returns (changed_targets, evicted_runs).
    """
    targets = target_ids if target_id == "all" else [target_id]
    now = _now_iso()
    changed: dict[str, Any] = {}
    evicted_runs: list[dict[str, Any]] = []

    for tid in targets:
        if allowed_gpu_ids == "all":
            conn.execute("DELETE FROM gpu_pool WHERE target_id=?", (tid,))
            changed[tid] = "all"
            continue
        allowed = {int(g) for g in allowed_gpu_ids}
        seen_ids = {int(g["id"]) for g in query_gpus_fn(tid)}
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
                evict_runs_off_gpus(conn, exp_kill_fn, tid, removed_gpus=seen_ids - allowed)
            )

    return changed, evicted_runs


def evict_runs_off_gpus(
    conn: sqlite3.Connection,
    exp_kill_fn: Any,
    target_id: str,
    *,
    removed_gpus: set[int],
) -> list[dict[str, Any]]:
    """SIGTERM runs on removed GPUs and reset units to pending."""
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
            exp_kill_fn(target_id, str(row["run_id"]))
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


def get_gpu_pool_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return current GPU pool overrides and draining runs."""
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


def gpu_capacity_ceiling(query_gpus_fn: Any, target_ids: list[str]) -> int | None:
    """Return largest single-GPU total VRAM in MB, or None if unavailable."""
    ceiling = 0
    for target_id in target_ids:
        try:
            gpus = query_gpus_fn(target_id)
        except Exception as exc:
            logger.debug("query_gpus failed during reserve cap: %s", exc)
            continue
        for gpu in gpus:
            total = gpu.get("total_mb")
            if isinstance(total, int) and total > ceiling:
                ceiling = total
    return ceiling or None


def _unit_reserve_mb(unit: Any) -> int:
    """Compute effective reserve_mb for a unit row."""
    reserve = unit["reserve_mb"]
    if reserve is not None:
        return max(0, int(reserve))
    min_free = int(unit["min_free_mb"] or 0)
    DEFAULT_RESERVE_MB = 8192
    return max(min_free, DEFAULT_RESERVE_MB)
