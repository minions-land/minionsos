"""mos_compact_context — compress conversation without killing the process.

Unlike ``mos_reset_context`` which kills the tmux session and forces a full
cold start (losing the prompt cache), this tool triggers Claude Code's native
``/compact`` command which:

1. Preserves the system prompt cache (the largest prefix, ~50k tokens).
2. Replaces conversation history with a compressed summary.
3. Keeps the process alive — no watchdog respawn, no cold start.

The tool persists durable state to the Scratchpad (L1) (same as
cognitive-checkpoint), then schedules ``/compact`` via tmux send-keys.
The ``/compact`` fires as the next "user input" after the agent's current
turn completes.

PreCompact hook (``minions/hooks/pre_compact_science.py``) automatically
injects science-aware retention instructions. PostCompact hook
(``minions/hooks/post_compact_scratchpad.py``) extracts Scratchpad nodes
from the resulting summary.

Cache interaction:
- The 5-minute cache keepalive in ``mos_await_events`` is unaffected.
  After compact, the agent calls ``mos_await_events()`` which resumes
  its internal poll loop with heartbeat writes. The prompt cache prefix
  (system prompt + tools) is still warm because the process never died.
- Compact only replaces the conversation body (~2-5k tokens of summary
  vs potentially 100k+ of raw history). The system prompt prefix stays
  byte-identical and cache-hit.

When to use compact vs reset:
- Compact: context is large but process is healthy, no contract drift.
- Reset: process behavior has drifted, SYSTEM.md was updated externally,
  or compact alone cannot recover coherent state.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime

from minions.paths import project_shared_subdir

logger = logging.getLogger(__name__)


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _env_role() -> str:
    return os.environ.get("MINIONS_ROLE_NAME", "unknown")


def _env_session() -> str:
    port = _env_port()
    role = _env_role()
    return f"mos-{port}-{role}"


def mos_compact_context(
    reason: str = "",
    pending_plans: list[dict] | None = None,
) -> dict:
    """Persist state to Scratchpad, then schedule /compact via tmux send-keys.

    After this tool returns, the agent MUST produce no further tool calls
    or text output. The scheduled ``/compact`` fires as the next user input
    once the agent's turn ends. The agent wakes up in a compacted context
    and should immediately call ``mos_await_events()``.

    Args:
        reason: Why compact is happening (logged to journal).
        pending_plans: Optional list of pending plan dicts to persist to
            the Scratchpad before compacting. Each dict should have at
            minimum ``type`` and ``text`` fields. These are written with
            ``metadata.pending_plan = true`` so the post-compact agent
            (same process, just compressed context) can find them via
            ``mos_scratchpad_summary()``.

    Returns:
        Status dict with instructions for the agent.
    """
    port = _env_port()
    role = _env_role()
    session = _env_session()
    ts = datetime.now(UTC).isoformat(timespec="seconds")

    # 1. Journal the compact event (same location as reset journal)
    scratchpad_dir = project_shared_subdir(port, "scratchpad")
    scratchpad_dir.mkdir(parents=True, exist_ok=True)
    journal_path = scratchpad_dir / "journal.jsonl"
    entry = {"op": "compact", "role": role, "reason": reason, "timestamp": ts}
    try:
        with journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Failed to log compact to journal: %s", exc)

    # 2. Persist pending_plans to Scratchpad if provided
    scratchpad_node_ids: list[str] = []
    if pending_plans:
        try:
            from minions.tools.scratchpad import mos_scratchpad_append

            nodes = []
            for plan in pending_plans:
                node = {
                    "type": plan.get("type", "question"),
                    "text": plan.get("text", ""),
                    "support_status": plan.get("support_status", "unverified"),
                    "metadata": {
                        "pending_plan": True,
                        "source": plan.get("source", "compact_handoff"),
                        "compact_reason": reason,
                    },
                }
                nodes.append(node)
            result = mos_scratchpad_append(nodes=nodes)
            scratchpad_node_ids = result.get("node_ids", [])
        except Exception as exc:
            logger.warning("Failed to persist pending_plans to Scratchpad: %s", exc)

    # 3. Schedule /compact via tmux send-keys
    # The /compact command will fire AFTER this tool returns and the agent's
    # turn completes. PreCompact hook injects science-aware instructions
    # automatically, so we don't need to pass custom instructions here.
    compact_scheduled = _schedule_compact(session, reason)

    logger.info(
        "mos_compact_context: session=%s reason=%r pending_plans=%d compact_scheduled=%s",
        session,
        reason,
        len(pending_plans or []),
        compact_scheduled,
    )

    return {
        "status": "compact_scheduled" if compact_scheduled else "compact_failed",
        "scratchpad_nodes_persisted": scratchpad_node_ids,
        "instruction": (
            "STOP NOW. Do not call any more tools. Do not produce any more text. "
            "The /compact command has been scheduled and will fire as the next "
            "input after your turn ends. After compact completes, you will wake "
            "up in a compressed context. Your first action should be "
            "mos_await_events() to resume the event loop. The prompt cache "
            "prefix (system prompt + tools) is preserved — no cold start penalty."
        ),
        "role": role,
        "timestamp": ts,
    }


def _schedule_compact(session: str, reason: str) -> bool:
    """Inject /compact into the tmux session's input buffer.

    Returns True if send-keys succeeded. The /compact will execute after
    the current assistant turn completes (when Claude Code is waiting for
    user input).
    """
    # Small delay to ensure the current tool response is fully processed
    # before /compact arrives in the input buffer.
    try:
        subprocess.run(
            [
                "tmux",
                "send-keys",
                "-t",
                session,
                "-l",
                "/compact",
            ],
            check=True,
            capture_output=True,
            timeout=5,
        )
        # Send Enter to execute the command
        subprocess.run(
            ["tmux", "send-keys", "-t", session, "Enter"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error(
            "_schedule_compact: tmux send-keys failed for %s: %s",
            session,
            exc,
        )
        return False
