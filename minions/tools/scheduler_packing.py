"""Task packing and placement logic for experiment scheduler.

Handles candidate GPU selection, multi-GPU placement, and spread-first tie-breaking.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from minions.tools.scheduler_gpu import GpuSlot
from minions.tools.scheduler_helpers import (
    OOM_ESCALATION_FACTOR,
    OOM_EXIT_CODES,
    OOM_NEEDLES,
    UnitLike,
    _json_loads,
)

logger = logging.getLogger(__name__)


def pick_candidate(
    unit: UnitLike,
    slots: list[GpuSlot],
    target_ids: list[str],
) -> tuple[str, list[int], int] | None:
    """Pick target and GPU IDs for a unit, or None if blocked.

    Returns (target_id, gpu_ids, reserve_mb) or None.
    """
    reserve_mb = _unit_reserve_mb(unit)
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

    # Explicit GPU pinning
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

    # Single GPU: spread-first tie-break
    if gpus_needed == 1:
        slot = sorted(
            candidates,
            key=lambda s: (s.total_run_count, -s.remaining_mb, s.target_id, s.gpu_id),
        )[0]
        return slot.target_id, [slot.gpu_id], reserve_mb

    # Multi-GPU: pick target with enough slots, spread-first
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


def reserve_slots(
    slots: list[GpuSlot],
    target_id: str,
    gpu_ids: list[int],
    reserve_mb: int,
) -> None:
    """Speculatively reserve capacity on selected slots (mutates in place)."""
    gpu_set = set(gpu_ids)
    for slot in slots:
        if slot.target_id == target_id and slot.gpu_id in gpu_set:
            slot.new_reserved_mb += reserve_mb
            slot.new_run_count += 1


def block_reason(unit: UnitLike, target_ids: list[str]) -> str:
    """Return reason why a pending unit could not be placed."""
    target_constraint = str(unit["target_id"] or "auto")
    if target_constraint != "auto" and target_constraint not in target_ids:
        return f"target_pin: {target_constraint!r} not in active fleet"
    if unit["gpu_ids_json"]:
        return "explicit_gpu: pinned GPUs not available in current pool"
    return "no_capacity: no allowed GPU has enough free VRAM"


def placement_summary(
    conn: sqlite3.Connection,
    launched: list[dict[str, Any]],
    slots_at_start: list[GpuSlot],
) -> dict[str, Any]:
    """Summarize GPU distribution and blocked reasons."""
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


def is_oom(log_tail: str, exit_code: int | None = None) -> bool:
    """Return True if run died from memory issue."""
    if exit_code is not None and int(exit_code) in OOM_EXIT_CODES:
        return True
    lowered = log_tail.lower()
    return any(needle in lowered for needle in OOM_NEEDLES)


def escalate_reserve(
    unit_row: sqlite3.Row,
    gpu_capacity_ceiling: int | None,
) -> int:
    """Bump reserve_mb after OOM to target roomier GPU."""
    current = _unit_reserve_mb(unit_row)
    bumped = max(current + 1024, int(current * OOM_ESCALATION_FACTOR))
    if gpu_capacity_ceiling is not None:
        bumped = min(bumped, int(gpu_capacity_ceiling * 0.95))
    return max(bumped, current)


def _unit_reserve_mb(unit: UnitLike) -> int:
    """Compute effective reserve_mb for a unit."""
    reserve = unit["reserve_mb"]
    if reserve is not None:
        return max(0, int(reserve))
    min_free = int(unit["min_free_mb"] or 0)
    DEFAULT_RESERVE_MB = 8192
    return max(min_free, DEFAULT_RESERVE_MB)
