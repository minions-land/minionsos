"""mos_reset — MinionsOS-specific context reset tool.

Signals the agent harness to clear the conversation context while keeping
the process alive. The agent MUST have persisted all valuable state to the
Exploration DAG before calling this.

After reset, the conversation returns to system prompt only. The agent
continues running and should call mos_dag_summary() to re-orient, then
mos_await_events() for next work.

This is NOT compact. Compact summarizes and costs tokens. Reset deletes
and costs nothing. The DAG is the external memory that survives the reset.

Evidence for this pattern: all major coding agents (Claude Code, Cursor,
Codex) recommend starting fresh context for new tasks. This tool makes
that transition seamless without process restart overhead.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from minions.paths import project_dir

logger = logging.getLogger(__name__)


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _env_role() -> str:
    return os.environ.get("MINIONS_ROLE_NAME", "unknown")


def mos_reset(reason: str = "") -> dict:
    """Signal the harness to clear conversation context.

    The agent MUST have persisted all valuable state to the Exploration DAG
    before calling this. After reset, context returns to system prompt only.

    Args:
        reason: Why the reset is happening (logged for debugging).
                Typical reasons: "task direction change", "batch complete",
                "switching to unrelated work".

    Returns:
        Acknowledgement dict. The harness intercepts this tool result and
        performs the actual context truncation before delivering it.
    """
    port = _env_port()
    role = _env_role()
    ts = datetime.now(UTC).isoformat(timespec="seconds")

    journal_path = project_dir(port) / "exploration" / "journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "op": "reset",
        "role": role,
        "reason": reason,
        "timestamp": ts,
    }

    try:
        with journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Failed to log reset to journal: %s", exc)

    logger.info(
        "mos_reset called by role=%s port=%d reason=%r",
        role,
        port,
        reason,
    )

    return {
        "status": "reset_acknowledged",
        "instruction": (
            "Context cleared. You are now in a fresh state. "
            "Call mos_dag_summary() to re-orient on team state, "
            "then mos_await_events() for next work."
        ),
        "role": role,
        "timestamp": ts,
    }
