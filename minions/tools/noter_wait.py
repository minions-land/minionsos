"""mos_noter_wait — Timer-based wait tool for the Noter role.

Noter is not registered on EACN3 and does not use ``mos_await_events``.
Instead it sleeps for a configurable interval (``noter_periodic_interval``,
default 5 min) and wakes to flush the DAG and observe project state.

This tool provides the same cache-keepalive guard as ``mos_await_events``
so Noter's prompt cache stays warm during long idle periods. The keepalive
logic is identical: a stable synthetic event is returned just before the
TTL cliff, the Role acks, and re-enters the wait.

Token efficiency: the LLM is suspended while this tool blocks. Tokens are
consumed only at call time (input) and return time (output).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_KEEPALIVE_EVENT: dict[str, Any] = {
    "type": "cache_keepalive",
    "suggested_action": (
        "Cache keepalive — no work to do. Reply with a single short ack "
        "(e.g. 'ack') and immediately call mos_noter_wait() again. Do "
        "not write to the DAG, do not send EACN messages, do not invoke "
        "any other tool."
    ),
}


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set.")
    return int(raw)


def _env_workspace() -> Path | None:
    val = os.environ.get("MINIONS_WORKSPACE", "")
    return Path(val) if val else None


def _touch_heartbeat(workspace: Path | None) -> None:
    if workspace is None:
        return
    hb_path = workspace / ".minionsos" / "heartbeat"
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent_id": "noter",
        "alive_at": datetime.now(tz=UTC).isoformat(),
        "pid": os.getpid(),
    }
    tmp = hb_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, hb_path)


def _load_interval_seconds() -> int:
    try:
        from minions.config import load_gru_config, parse_duration

        return parse_duration(load_gru_config().noter_periodic_interval)
    except Exception:
        return 300


def _load_keepalive_seconds() -> int:
    try:
        from minions.config import load_gru_config

        return int(load_gru_config().cache_keepalive_seconds)
    except Exception:
        return 0


def _shared_branch_delta(workspace: Path | None) -> dict[str, Any]:
    """Count new commits on the shared branch since last wake."""
    if workspace is None:
        return {"new_commits": 0}
    shared = workspace.parent / "shared"
    if not shared.exists():
        return {"new_commits": 0}
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=5 minutes ago", "--format=%h %s"],
            cwd=str(shared),
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [line for line in result.stdout.strip().splitlines() if line]
        return {"new_commits": len(lines), "recent": lines[:10]}
    except Exception:
        return {"new_commits": 0}


def _events_jsonl_delta(port: int) -> dict[str, Any]:
    """Count new lines in the events/ audit stream since last check."""
    from minions.paths import project_workspace_root

    events_dir = project_workspace_root(port) / "events"
    if not events_dir.exists():
        return {"new_events": 0}
    total = 0
    for jsonl in events_dir.glob("*.jsonl"):
        try:
            with jsonl.open("r", encoding="utf-8") as f:
                for _ in f:
                    total += 1
        except Exception:
            pass
    return {"total_event_lines": total}


def noter_wait() -> dict[str, Any]:
    """Block for the noter periodic interval, then return a wake event.

    Includes cache-keepalive guard identical to mos_await_events.
    The LLM is suspended while this blocks — zero token cost during sleep.

    Returns:
        {type: "periodic_wake", delta: {shared_branch: ..., events: ...}}
        or {type: "cache_keepalive", ...} if the keepalive cliff is hit first.
    """
    port = _env_port()
    workspace = _env_workspace()
    interval = _load_interval_seconds()
    keepalive_seconds = _load_keepalive_seconds()

    started = time.monotonic()
    elapsed = 0.0

    while elapsed < interval:
        sleep_chunk = min(30.0, interval - elapsed)
        time.sleep(sleep_chunk)
        _touch_heartbeat(workspace)
        elapsed = time.monotonic() - started

        if keepalive_seconds > 0 and elapsed >= keepalive_seconds:
            return {"count": 1, "events": [_KEEPALIVE_EVENT]}

    return {
        "count": 1,
        "events": [
            {
                "type": "periodic_wake",
                "slept_seconds": int(elapsed),
                "delta": {
                    "shared_branch": _shared_branch_delta(workspace),
                    "events": _events_jsonl_delta(port),
                },
                "suggested_action": (
                    "Periodic wake. Flush the DAG (mos_dag_commit_shared), "
                    "read recent EACN activity and shared branch changes, "
                    "update the DAG if needed, and consider whether a fresh "
                    "observation report is due."
                ),
            }
        ],
    }
