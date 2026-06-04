"""Shared helpers and constants for experiment scheduler.

Type aliases, JSON utilities, ID generation, and common constants.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.errors import ConfigError

# Constants
DEFAULT_RESERVE_MB = 8192
DEFAULT_MAX_RETRIES = 3
OOM_ESCALATION_FACTOR = 1.5

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

OOM_EXIT_CODES = frozenset({137, 139, -9, -11})

# Anomaly detection patterns
ANOMALY_NAN_PATTERN = re.compile(r"\b(nan|NaN|NAN|inf|Inf|INF)\b")
ANOMALY_LOSS_LINE_PATTERN = re.compile(r"(?i)(loss|train_loss|val_loss|nll|perplexity)")
GPU_UTIL_COLLAPSE_SECONDS = 300


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


class _UnitRowView:
    """sqlite3.Row-shaped view over QueueUnit for dry-run planning."""

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


def resolve_project_port(project_port: int | None = None) -> int:
    """Resolve project port from argument or environment."""
    if project_port is not None:
        return project_port
    import os

    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    raise ConfigError(
        "Experiment queue tools require MINIONS_PROJECT_PORT or an explicit project_port."
    )


def default_db_path(project_port: int) -> Path:
    """Return the durable scheduler DB path for a project."""
    from minions.paths import project_artifacts_dir

    return project_artifacts_dir(project_port) / "experiment-queue" / "scheduler.sqlite"


def check_hard_anomalies(run_id: str, target_id: str, log_tail: str) -> str | None:
    """Check for hard-metric anomalies in log tail.

    Returns reason string if anomaly detected, None otherwise.
    """
    # Check for NaN/Inf in loss-related lines
    for line in log_tail.splitlines():
        if ANOMALY_LOSS_LINE_PATTERN.search(line) and ANOMALY_NAN_PATTERN.search(line):
            return f"NaN/Inf detected in loss metric: {line.strip()[:120]}"

    # Check for GPU utilization collapse
    gpu_zero_pattern = re.compile(
        r"(?i)(gpu[_ ]?util\w*\s*[:=]\s*0[%\s]|utilization\.gpu\s*\[%\]\s*:\s*0\b)"
    )
    zero_util_lines = [line for line in log_tail.splitlines() if gpu_zero_pattern.search(line)]
    if len(zero_util_lines) >= 10:
        return "GPU utilization collapsed to 0% (sustained in recent log tail)"

    return None
