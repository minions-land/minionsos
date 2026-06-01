"""Reel (L0) — lightweight index of native Claude session traces.

The Reel layer maintains a flat JSONL index per role pointing to native
session files. No transcript copying — pointers only.

**Storage layout:**

    project_{port}/branches/<role>/reel-index.jsonl

**Index entry schema (one JSON object per line):**

    {
      "ref": "<role>/<session_id>/<tool_use_id>",
      "ts": "2026-05-22T12:34:56.789Z",
      "kind": "subagent",
      "tool_name": "Agent" | "Task",
      "claude_jsonl": "/abs/path/to/<session_id>.jsonl",
      "draft_node_refs": ["H-003", "Q-007"]
    }

**Authz:**
- Gru: cross-role read.
- Ethics: cross-role read (audit privilege).
- Other roles: own reel only.

MCP tools:
    mos_reel_get(ref) — read lines from the native jsonl a ref points to.
    mos_reel_window(ref, span) — read index entries around a ref.
    mos_reel_backfill_draft_ref(ref, draft_node_id) — add a Draft pointer.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Any

from minions.errors import ReelError
from minions.paths import project_role_workspace

logger = logging.getLogger(__name__)

# Roles with cross-role read access
_CROSS_READ_ROLES = {"gru", "ethics"}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _reel_index_path(port: int, role: str) -> Path:
    """Return the flat reel-index.jsonl path for (port, role)."""
    return project_role_workspace(port, role) / "reel-index.jsonl"


def _validate_ref_component(value: str, label: str) -> str:
    """Reject path components that could escape the reel root."""
    cleaned = value.strip()
    if not cleaned:
        raise ReelError(f"Invalid reel ref {label}: empty")
    if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned or cleaned.startswith("."):
        raise ReelError(f"Invalid reel ref {label}: {value!r}")
    return cleaned


# ---------------------------------------------------------------------------
# Authz
# ---------------------------------------------------------------------------


def _check_reel_read_permission(target_role: str) -> None:
    """Raise PermissionError if the current role cannot read *target_role*'s reel."""
    current_role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    if not current_role:
        raise PermissionError("MINIONS_ROLE_NAME not set; cannot determine caller identity")
    if current_role in _CROSS_READ_ROLES:
        return
    if current_role != target_role:
        raise PermissionError(
            f"Role '{current_role}' cannot read reel for role '{target_role}' "
            "(only Gru/Ethics may read cross-role reels)"
        )


# ---------------------------------------------------------------------------
# Low-level index reader
# ---------------------------------------------------------------------------


def _read_index(index_path: Path) -> list[dict[str, Any]]:
    """Read all entries from a reel-index.jsonl; return [] if absent."""
    if not index_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    with contextlib.suppress(json.JSONDecodeError):
                        entries.append(json.loads(line))
    except OSError as exc:
        logger.warning("_read_index: failed to read %s: %s", index_path, exc)
    return entries


# ---------------------------------------------------------------------------
# MCP-facing tools
# ---------------------------------------------------------------------------


def mos_reel_get(ref: str) -> dict[str, Any]:
    """Read lines from the native jsonl file a reel ref points to.

    Args:
        ref: Reel reference "<role>/<session_id>/<tool_use_id>".

    Returns:
        dict with ref, role, session_id, tool_use_id, kind, ts,
        claude_jsonl, draft_node_refs, lines.

    Raises:
        PermissionError: caller lacks cross-role read permission.
        ValueError: malformed ref or entry not found.
    """
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0"))
    if port == 0:
        raise ReelError("MINIONS_PROJECT_PORT not set")

    parts = ref.split("/")
    if len(parts) != 3:
        raise ReelError(f"Invalid reel ref format: {ref!r} (want <role>/<session>/<id>)")
    role, session_id, tool_use_id = parts
    role = _validate_ref_component(role, "role")
    session_id = _validate_ref_component(session_id, "session_id")
    tool_use_id = _validate_ref_component(tool_use_id, "tool_use_id")

    _check_reel_read_permission(role)

    index_path = _reel_index_path(port, role)
    entries = _read_index(index_path)
    entry = next((e for e in entries if e.get("ref") == ref), None)
    if entry is None:
        raise ReelError(f"Ref {ref!r} not found in reel index")

    lines: list[Any] = []
    claude_jsonl = entry.get("claude_jsonl", "")
    if claude_jsonl and Path(claude_jsonl).exists():
        try:
            with Path(claude_jsonl).open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            lines.append({"_raw": line.rstrip()})
        except OSError as exc:
            raise ReelError(f"Failed to read claude_jsonl: {exc}") from exc

    return {
        "ref": ref,
        "role": role,
        "session_id": session_id,
        "tool_use_id": tool_use_id,
        "kind": entry.get("kind"),
        "ts": entry.get("ts"),
        "claude_jsonl": claude_jsonl,
        "draft_node_refs": entry.get("draft_node_refs", []),
        "lines": lines,
    }


def mos_reel_window(ref: str, span: int = 5) -> list[dict[str, Any]]:
    """Read index entries around a reel reference.

    Args:
        ref: Reel reference "<role>/<session_id>/<tool_use_id>".
        span: Entries before and after the target (default 5).

    Returns:
        List of index entries sorted by ts, centred on target.

    Raises:
        PermissionError: caller lacks cross-role read permission.
        ValueError: malformed ref or session not found.
    """
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0"))
    if port == 0:
        raise ReelError("MINIONS_PROJECT_PORT not set")

    parts = ref.split("/")
    if len(parts) != 3:
        raise ReelError(f"Invalid reel ref format: {ref!r} (expected <role>/<session>/<id>)")
    role, session_id, tool_use_id = parts
    role = _validate_ref_component(role, "role")
    session_id = _validate_ref_component(session_id, "session_id")
    tool_use_id = _validate_ref_component(tool_use_id, "tool_use_id")

    _check_reel_read_permission(role)

    index_path = _reel_index_path(port, role)
    entries = _read_index(index_path)

    # Filter to this session
    session_entries = [e for e in entries if e.get("ref", "").startswith(f"{role}/{session_id}/")]
    session_entries.sort(key=lambda e: e.get("ts", ""))

    # Find target index
    target_idx = next((i for i, e in enumerate(session_entries) if e.get("ref") == ref), None)
    if target_idx is None:
        raise ReelError(f"Ref {ref!r} not found in reel index")

    lo = max(0, target_idx - span)
    hi = min(len(session_entries), target_idx + span + 1)
    return session_entries[lo:hi]


def mos_reel_backfill_draft_ref(ref: str, draft_node_id: str) -> dict[str, str]:
    """Add a Draft node pointer to an existing reel index entry.

    Args:
        ref: Reel reference "<role>/<session_id>/<tool_use_id>".
        draft_node_id: Draft node ID to add (e.g. "H-003").

    Returns:
        {"status": "ok", "ref": ref, "draft_node_id": draft_node_id}

    Raises:
        PermissionError: caller lacks cross-role read permission.
        ValueError: malformed ref or entry not found.
    """
    port = int(os.environ.get("MINIONS_PROJECT_PORT", "0"))
    if port == 0:
        raise ReelError("MINIONS_PROJECT_PORT not set")

    parts = ref.split("/")
    if len(parts) != 3:
        raise ReelError(f"Invalid reel ref format: {ref!r}")
    role, session_id, tool_use_id = parts
    role = _validate_ref_component(role, "role")
    session_id = _validate_ref_component(session_id, "session_id")
    tool_use_id = _validate_ref_component(tool_use_id, "tool_use_id")

    _check_reel_read_permission(role)

    index_path = _reel_index_path(port, role)
    entries = _read_index(index_path)

    updated = False
    for entry in entries:
        if entry.get("ref") == ref:
            refs = entry.setdefault("draft_node_refs", [])
            if draft_node_id not in refs:
                refs.append(draft_node_id)
            updated = True
            break

    if not updated:
        raise ReelError(f"Ref {ref!r} not found in reel index")

    # Rewrite index atomically
    tmp_path = index_path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                for entry in entries:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        tmp_path.replace(index_path)
    except OSError as exc:
        logger.error("mos_reel_backfill_draft_ref: write failed: %s", exc)
        raise

    return {"status": "ok", "ref": ref, "draft_node_id": draft_node_id}
