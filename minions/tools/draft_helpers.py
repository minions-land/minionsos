"""Draft helpers — shared utilities for path resolution, JSON I/O, and validation.

Extracted from draft.py to reduce module size and improve maintainability.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import minions.paths
from minions.errors import DraftError


# Access path functions through module reference for test monkeypatch compatibility
def _get_project_shared_subdir(port: int, subdir: str):
    """Indirection for test monkeypatching."""
    return minions.paths.project_shared_subdir(port, subdir)


def _get_project_shared_draft_json(port: int):
    """Indirection for test monkeypatch compatibility."""
    return minions.paths.project_shared_draft_json(port)


logger = logging.getLogger(__name__)


def draft_dir(port: int) -> Path:
    return _get_project_shared_subdir(port, "draft")


def draft_path(port: int) -> Path:
    return _get_project_shared_draft_json(port)


def journal_path(port: int) -> Path:
    return draft_dir(port) / "journal.jsonl"


def decay_path(port: int) -> Path:
    """Sidecar with effective_confidence per node, computed by Ethics."""
    return draft_dir(port) / "decay.json"


def env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise DraftError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def env_role() -> str:
    """Return the current role name from env, or empty string."""
    return os.environ.get("MINIONS_ROLE_NAME", "")


def env_reel_context() -> str | None:
    """Return the current reel context as '<role>/<session_id>' or None."""
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    session = os.environ.get("MINIONS_SESSION_ID", "").strip()
    if not role or not session:
        return None
    return f"{role}/{session}"


def load_draft(port: int) -> dict[str, Any]:
    path = draft_path(port)
    if not path.exists():
        return {"project_port": port, "root_question": "", "nodes": [], "edges": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "draft.json corrupt for port %s (%s); falling back to empty stub",
            port,
            exc,
        )
        return {"project_port": port, "root_question": "", "nodes": [], "edges": []}


def save_draft(port: int, draft: dict[str, Any]) -> None:
    path = draft_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def append_journal(port: int, entry: dict[str, Any]) -> None:
    path = journal_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_decay(port: int) -> dict[str, Any]:
    path = decay_path(port)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    nodes = payload.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def validate_confidence(confidence: Any) -> float:
    try:
        value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise DraftError(f"Node confidence must be a number, got {confidence!r}") from exc
    if not (0.0 <= value <= 1.0):
        raise DraftError(f"Node confidence must be 0.0-1.0, got {value}")
    return value


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
