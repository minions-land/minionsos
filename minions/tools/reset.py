"""mos_reset_context — kill the current Role's tmux session for a clean restart.

The agent calls this at a natural batch boundary after persisting durable
state to the Exploration DAG. The session is killed; the Gru watchdog
respawns a fresh ``claude`` process under the same session name with no
``--resume`` flag, so SYSTEM.md re-injects but conversation history starts
empty. The DAG is the external memory that bridges the gap.

Why this is not Claude's compact:
- Compact summarizes (costs tokens, lossy, can drift role contract).
- Reset deletes (costs zero tokens, lossless because state lives in DAG).

A marker file under ``project_{port}/state/.reset_markers/{role}`` is
written before the kill so the watchdog can distinguish a deliberate reset
from a real crash and not increment the crash counter. Markers live under
``state/`` (gitignored) rather than under the audited shared tree, since
they are runtime control signals and have no review value.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime

from minions.paths import project_reset_markers_dir, project_shared_subdir

logger = logging.getLogger(__name__)


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _env_role() -> str:
    return os.environ.get("MINIONS_ROLE_NAME", "unknown")


def mos_reset_context(reason: str = "") -> dict:
    """Kill this Role's tmux session so the watchdog respawns it cold.

    The agent MUST have persisted all valuable state — including any
    pending plans not yet executed — to the Exploration DAG before
    calling this. After respawn, conversation context is empty; the new
    process re-orients via ``mos_dag_summary()`` which surfaces those
    pending plans, then enters its event loop.

    Args:
        reason: Why the reset is happening (logged for debugging and
                surfaced in the Gru-side respawn audit).

    Returns:
        Acknowledgement dict. In practice the agent rarely sees this —
        the tmux session dies before the LLM gets to read it.
    """
    port = _env_port()
    role = _env_role()
    ts = datetime.now(UTC).isoformat(timespec="seconds")

    # Journal lives in the audited shared tree alongside the DAG, since it
    # is genuine project history. Markers live in gitignored state/.
    exploration = project_shared_subdir(port, "exploration")
    exploration.mkdir(parents=True, exist_ok=True)

    journal_path = exploration / "journal.jsonl"
    entry = {"op": "reset", "role": role, "reason": reason, "timestamp": ts}
    try:
        with journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Failed to log reset to journal: %s", exc)

    marker_dir = project_reset_markers_dir(port)
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker_path = marker_dir / role
    try:
        marker_path.write_text(json.dumps({"reason": reason, "timestamp": ts}))
    except OSError as exc:
        logger.warning("Failed to write reset marker: %s", exc)

    session = f"mos-{port}-{role}"
    logger.info(
        "mos_reset_context: killing tmux session=%s reason=%r role=%s",
        session,
        reason,
        role,
    )

    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("mos_reset_context: tmux kill-session failed: %s", exc)
        return {
            "status": "reset_failed",
            "error": str(exc),
            "instruction": (
                "Reset could not kill the tmux session. Persist state to the "
                "DAG and exit your event loop manually if needed."
            ),
        }

    return {
        "status": "reset_acknowledged",
        "instruction": "Session terminating; watchdog will respawn cold.",
        "role": role,
        "timestamp": ts,
    }
