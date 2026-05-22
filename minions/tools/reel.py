"""Reel (L0) — raw session-level execution traces for multi-agent memory.

The Reel layer captures verbatim transcripts of role sessions and subagent
dispatches, providing the lowest-level audit trail for all reasoning that
produces Draft nodes, Book pages, and Shelf entries. It is the foundation
for Library's "executable + recoverable" properties.

**Design principles:**

1. **Zero role burden** — roles never call reel tools directly; capture is
   automatic via PostToolUse hooks.
2. **Drill-down only** — reel content is never injected at wake-up; it is
   read on-demand when auditing or replaying a decision.
3. **Full fidelity** — transcripts are stored verbatim, not summarized.
4. **Role-private by default** — each role writes to its own branch; Gru
   holds cross-role read permission.

**Storage layout:**

    project_{port}/branches/<role>/reel/<session_id>/
        index.jsonl          # one line per captured event
        transcripts/
            <task_id>.jsonl  # verbatim subagent/codex transcript
            role_main.jsonl  # role's own session (on exit)

**Index schema (one JSON object per line):**

    {
      "seq": 17,
      "ts": "2026-05-22T12:34:56.789Z",
      "kind": "subagent" | "codex" | "role_main",
      "task_id": "a1b2c3d4e5f6",
      "draft_refs": ["H-003", "Q-007"]  # backfilled when Draft nodes cite this
    }

**Pointer schema:**

Draft/Book/Shelf metadata carries ``reel_ref`` strings in the form:
``<role>/<session_id>/<task_id>``. Example: ``coder/sess-20260522-123456/a1b2c3d4e5f6``.

**Lifecycle:**

- Transcripts are written once and never modified.
- Noter periodic lint marks sessions as ``archived: true`` after 30 days
  if no verified Draft nodes reference them.
- Archived sessions remain readable (for Library export) but disappear
  from ``mos_unread_summary``.

Environment:
    MINIONS_PROJECT_PORT — identifies the project.
    MINIONS_ROLE_NAME — identifies the calling role (for authz).

MCP tools:
    mos_reel_get(ref) — read a single transcript by ref.
    mos_reel_window(ref, span) — read index entries around a ref.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.paths import project_role_workspace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _reel_dir(port: int, role: str) -> Path:
    """Return the reel root for *(port, role)*."""
    return project_role_workspace(port, role) / "reel"


def _validate_ref_component(value: str, label: str) -> str:
    """Reject path components that could escape the reel root.

    Reel refs come from model output (``mos_reel_get(ref)``); a malicious or
    confused ref like ``coder/../foo/bar`` could otherwise resolve outside the
    project's reel directory. Reject path separators, parent traversal, and
    leading dots so every component is a single safe directory name.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"Invalid reel ref {label}: empty")
    if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned or cleaned.startswith("."):
        raise ValueError(f"Invalid reel ref {label}: {value!r}")
    return cleaned


def _reel_session_dir(port: int, role: str, session_id: str) -> Path:
    """Return the session directory for *(port, role, session_id)*."""
    return _reel_dir(port, role) / session_id


def _reel_index_path(port: int, role: str, session_id: str) -> Path:
    """Return the index.jsonl path for a session."""
    return _reel_session_dir(port, role, session_id) / "index.jsonl"


def _reel_transcripts_dir(port: int, role: str, session_id: str) -> Path:
    """Return the transcripts/ directory for a session."""
    return _reel_session_dir(port, role, session_id) / "transcripts"


def _reel_transcript_path(port: int, role: str, session_id: str, task_id: str) -> Path:
    """Return the transcript file path for a specific task."""
    return _reel_transcripts_dir(port, role, session_id) / f"{task_id}.jsonl"


# ---------------------------------------------------------------------------
# Authz
# ---------------------------------------------------------------------------


def _check_reel_read_permission(port: int, target_role: str) -> None:
    """Raise PermissionError if the current role cannot read *target_role*'s reel.

    Rules:
    - Gru can read any role's reel (cross-role coordinator).
    - Any other role can only read its own reel.
    """
    current_role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    if not current_role:
        raise PermissionError("MINIONS_ROLE_NAME not set; cannot determine caller identity")

    if current_role == "gru":
        return  # Gru has global read access

    if current_role != target_role:
        raise PermissionError(
            f"Role '{current_role}' cannot read reel for role '{target_role}' "
            "(only Gru may read cross-role reels)"
        )


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def append_reel_index(
    port: int,
    role: str,
    session_id: str,
    *,
    kind: str,
    task_id: str,
    draft_refs: list[str] | None = None,
) -> None:
    """Append a new entry to the reel index for *(port, role, session_id)*.

    Args:
        port: Project port.
        role: Role name (e.g., "coder", "writer").
        session_id: Session identifier (e.g., "sess-20260522-123456").
        kind: Entry kind — "subagent", "codex", or "role_main".
        task_id: Task/agent ID for this entry.
        draft_refs: Optional list of Draft node IDs that reference this entry.

    The index is append-only; existing entries are never modified.
    """
    index_path = _reel_index_path(port, role, session_id)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing entries to determine next seq
    seq = 0
    if index_path.exists():
        try:
            with index_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        seq += 1
        except Exception as exc:
            logger.warning("append_reel_index: failed to count existing entries: %s", exc)

    entry = {
        "seq": seq,
        "ts": datetime.now(UTC).isoformat(),
        "kind": kind,
        "task_id": task_id,
        "draft_refs": draft_refs or [],
    }

    try:
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(
            "append_reel_index: port=%d role=%s session=%s seq=%d kind=%s task=%s",
            port,
            role,
            session_id,
            seq,
            kind,
            task_id,
        )
    except Exception as exc:
        logger.error("append_reel_index: write failed: %s", exc)
        raise


def archive_transcript(
    port: int,
    role: str,
    session_id: str,
    task_id: str,
    source_path: Path,
    *,
    kind: str,
) -> None:
    """Copy a transcript from *source_path* into the reel archive.

    Args:
        port: Project port.
        role: Role name.
        session_id: Session identifier.
        task_id: Task/agent ID.
        source_path: Path to the source transcript (e.g., /private/tmp/.../task.output).
        kind: Entry kind — "subagent", "codex", or "role_main".

    This function:
    1. Creates the transcripts/ directory if needed.
    2. Copies the source file to transcripts/<task_id>.jsonl.
    3. Appends an entry to index.jsonl.
    """
    transcripts_dir = _reel_transcripts_dir(port, role, session_id)
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    dest_path = _reel_transcript_path(port, role, session_id, task_id)

    try:
        if not source_path.exists():
            logger.warning("archive_transcript: source does not exist: %s (skipping)", source_path)
            return

        # Copy verbatim
        import shutil

        shutil.copy2(source_path, dest_path)
        logger.info(
            "archive_transcript: port=%d role=%s session=%s task=%s kind=%s size=%d",
            port,
            role,
            session_id,
            task_id,
            kind,
            dest_path.stat().st_size,
        )

        # Append index entry
        append_reel_index(port, role, session_id, kind=kind, task_id=task_id)

    except Exception as exc:
        logger.error("archive_transcript: failed to archive %s: %s", source_path, exc)
        raise


# ---------------------------------------------------------------------------
# MCP-facing tools
# ---------------------------------------------------------------------------


def mos_reel_get(ref: str) -> dict[str, Any]:
    """Read a single transcript by reel reference.

    Args:
        ref: Reel reference in the form "<role>/<session_id>/<task_id>".
             Example: "coder/sess-20260522-123456/a1b2c3d4e5f6"

    Returns:
        A dict with keys:
        - ref: The input reference.
        - role: Role name.
        - session_id: Session identifier.
        - task_id: Task identifier.
        - kind: Entry kind (from index).
        - ts: Timestamp (from index).
        - lines: List of transcript lines (parsed JSON objects).

    Raises:
        PermissionError: If the caller lacks permission to read this reel.
        ValueError: If the ref is malformed or the transcript does not exist.
    """
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0"))
    if port == 0:
        raise ValueError("MINIONS_PROJECT_PORT not set")

    # Parse ref
    parts = ref.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid reel ref format: {ref} (expected <role>/<session>/<task>)")
    role, session_id, task_id = parts
    role = _validate_ref_component(role, "role")
    session_id = _validate_ref_component(session_id, "session_id")
    task_id = _validate_ref_component(task_id, "task_id")

    # Check permission
    _check_reel_read_permission(port, role)

    # Read index to find metadata
    index_path = _reel_index_path(port, role, session_id)
    if not index_path.exists():
        raise ValueError(f"Reel index not found for {role}/{session_id}")

    entry_meta = None
    try:
        with index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("task_id") == task_id:
                    entry_meta = entry
                    break
    except Exception as exc:
        raise ValueError(f"Failed to read reel index: {exc}") from exc

    if entry_meta is None:
        raise ValueError(f"Task {task_id} not found in reel index for {role}/{session_id}")

    # Read transcript
    transcript_path = _reel_transcript_path(port, role, session_id, task_id)
    if not transcript_path.exists():
        raise ValueError(f"Transcript not found: {transcript_path}")

    lines = []
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        # Keep malformed lines as raw strings
                        lines.append({"_raw": line.rstrip()})
    except Exception as exc:
        raise ValueError(f"Failed to read transcript: {exc}") from exc

    return {
        "ref": ref,
        "role": role,
        "session_id": session_id,
        "task_id": task_id,
        "kind": entry_meta.get("kind"),
        "ts": entry_meta.get("ts"),
        "draft_refs": entry_meta.get("draft_refs", []),
        "lines": lines,
    }


def mos_reel_window(ref: str, span: int = 5) -> list[dict[str, Any]]:
    """Read index entries around a reel reference.

    Args:
        ref: Reel reference in the form "<role>/<session_id>/<task_id>".
        span: Number of entries to return before and after the target (default 5).

    Returns:
        A list of index entries (dicts with seq, ts, kind, task_id, draft_refs).
        The target entry is included; the list is sorted by seq.

    Raises:
        PermissionError: If the caller lacks permission to read this reel.
        ValueError: If the ref is malformed or the session does not exist.
    """
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0"))
    if port == 0:
        raise ValueError("MINIONS_PROJECT_PORT not set")

    # Parse ref
    parts = ref.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid reel ref format: {ref} (expected <role>/<session>/<task>)")
    role, session_id, task_id = parts
    role = _validate_ref_component(role, "role")
    session_id = _validate_ref_component(session_id, "session_id")
    task_id = _validate_ref_component(task_id, "task_id")

    # Check permission
    _check_reel_read_permission(port, role)

    # Read index
    index_path = _reel_index_path(port, role, session_id)
    if not index_path.exists():
        raise ValueError(f"Reel index not found for {role}/{session_id}")

    entries = []
    target_seq = None
    try:
        with index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                entries.append(entry)
                if entry.get("task_id") == task_id:
                    target_seq = entry.get("seq")
    except Exception as exc:
        raise ValueError(f"Failed to read reel index: {exc}") from exc

    if target_seq is None:
        raise ValueError(f"Task {task_id} not found in reel index for {role}/{session_id}")

    # Filter to window
    window = [e for e in entries if abs(e.get("seq", 0) - target_seq) <= span]
    window.sort(key=lambda e: e.get("seq", 0))

    return window
