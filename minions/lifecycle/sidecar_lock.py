"""Sidecar registry lock for MinionsOS-spawned Claude Code sessions.

Claude Code installations may have a global ``auto_title`` hook (under
``~/.claude/hooks/``) that auto-renames sessions for a friendlier
``/resume`` picker. Role processes and review/adjudication one-shot
sessions must keep the session names MinionsOS assigns at spawn time
(e.g. ``mos-{port}-{role}``).

The lock mechanism is the global ``~/.claude/title-registry.json`` sidecar
that the auto-namer consults: if a session's entry has ``locked=true``,
both ``auto_title_session_start.py`` and ``auto_title_user_prompt.py``
early-exit without writing a placeholder or invoking Haiku.

This module provides ``lock_session_title(session_id, title)`` — a
best-effort, fail-open helper that:

1. No-ops silently when the sidecar parent directory doesn't exist
   (user hasn't installed the auto_title hook family — nothing to lock).
2. Atomically updates the registry file under ``flock`` so concurrent
   spawns serialize cleanly.
3. Stamps ``source="minionsos"`` so the entry is unmistakable in audit.

Importantly: this module does NOT depend on any user-side hook being
installed. If ``~/.claude/`` exists but ``title-registry.json`` doesn't,
we create it; if ``~/.claude/`` itself is missing, we no-op. The lock is
a *protective annotation* — it costs nothing when no auto-namer is
present and prevents drift when one is.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def _claude_home() -> Path:
    """Return the Claude Code home directory (``~/.claude`` by default).

    Honours ``CLAUDE_CONFIG_DIR`` if set, matching Claude Code's own
    convention. Test code can also point at a fake home via this env var.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def _registry_path() -> Path:
    return _claude_home() / "title-registry.json"


def lock_session_title(
    session_id: str,
    title: str,
    *,
    source: str = "minionsos",
) -> bool:
    """Lock a Claude Code session's display title in the global sidecar registry.

    Args:
        session_id: The Claude Code session UUID. Must be the value passed to
            ``claude --session-id`` so the auto-namer hooks see the same key.
        title: The fixed display title. Convention: match the tmux session
            name (e.g. ``mos-{port}-{role}``) so /resume and tmux agree.
        source: Free-form provenance tag stored in the row. Defaults to
            ``minionsos`` so audits can identify locked rows by author.

    Returns:
        True if the lock was written; False if the sidecar wasn't present
        and the call no-opped. Never raises — failures are logged at debug
        and swallowed so a sidecar issue can't break a Role spawn.
    """
    if not session_id or not title:
        return False
    home = _claude_home()
    if not home.exists():
        return False
    path = _registry_path()
    try:
        return _write_locked_entry(path, session_id, title, source)
    except Exception as exc:
        logger.debug("lock_session_title: best-effort write failed: %s", exc)
        return False


def _write_locked_entry(path: Path, session_id: str, title: str, source: str) -> bool:
    """Atomically merge a locked row for *session_id* into the registry.

    Uses ``fcntl.flock`` to serialize against any concurrent writer
    (including the auto_title hooks themselves).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.lseek(fd, 0, os.SEEK_SET)
        raw = b""
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            raw += chunk
        try:
            data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[session_id] = {
            "title": title,
            "source": source,
            "locked": True,
            "pending_auto_name": False,
            "updated_at": int(time.time()),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def allocate_session_id() -> str:
    """Return a fresh UUID4 string suitable for ``claude --session-id``."""
    return str(uuid.uuid4())


__all__ = ["allocate_session_id", "lock_session_title"]
