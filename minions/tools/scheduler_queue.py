"""Queue management operations for experiment scheduler.

Handles batch and unit submission, cancellation, and status queries.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from minions.tools.scheduler_helpers import (
    _json_dumps,
    _json_loads,
    _new_id,
    _now_iso,
)

logger = logging.getLogger(__name__)


def submit_batch(
    conn: sqlite3.Connection,
    units: list[dict[str, Any]],
    *,
    requester: str | None = None,
    batch_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """Append a new logical batch into the queue.

    Returns (batch_id, unit_ids).
    """
    bid = batch_id or _new_id("batch")
    now = _now_iso()
    unit_ids: list[str] = []

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
                unit["cmd"],
                unit.get("target_id", "auto"),
                _json_dumps(unit["gpu_ids"]) if unit.get("gpu_ids") is not None else None,
                max(1, int(unit.get("gpus_needed", 1))),
                max(0, int(unit.get("min_free_mb", 0))),
                unit.get("reserve_mb"),
                int(unit.get("priority", 0)),
                max(0, int(unit.get("max_retries", 3))),
                _json_dumps(unit.get("metadata") or {}),
                now,
                now,
            ),
        )

    return bid, unit_ids


def get_pending_units(
    conn: sqlite3.Connection,
    batch_id: str | None = None,
) -> list[sqlite3.Row]:
    """Fetch pending units ordered by priority and creation time."""
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


def get_status(
    conn: sqlite3.Connection,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Return status summary and detail for one batch or entire queue."""
    where = ""
    params: tuple[Any, ...] = ()
    if batch_id:
        where = "WHERE batch_id=?"
        params = (batch_id,)

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


def get_blocked_units(
    conn: sqlite3.Connection,
    batch_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return units stuck in blocked or failed state."""
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


def note_no_capacity(conn: sqlite3.Connection, unit: sqlite3.Row, reason: str) -> None:
    """Mark unit with capacity block reason."""
    conn.execute(
        "UPDATE units SET last_error=?, updated_at=? WHERE unit_id=?",
        (reason, _now_iso(), unit["unit_id"]),
    )


def refresh_batches(conn: sqlite3.Connection) -> None:
    """Update batch status based on constituent unit states."""
    batch_ids = [row["batch_id"] for row in conn.execute("SELECT batch_id FROM batches").fetchall()]
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
