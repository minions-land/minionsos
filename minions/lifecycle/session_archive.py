"""Archive host session files into each role's branch.

After a role wake window exits, copy the host's session transcript (Claude's
``~/.claude/projects/<hashed-cwd>/<session-uuid>.jsonl`` or Codex's
``~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-<ts>-<uuid>.jsonl``) into the role
branch's ``.minionsos/sessions/`` directory. The archive is committed on the
role branch alongside any workspace changes, so the branch git history carries
the full per-wake transcript.

Rationale (V5 design):

- Host compact pressure cannot reshape these files because the role contract
  is re-injected on each wake (``AGENTS.md`` for Codex, ``--append-system-prompt``
  for Claude); the archive is purely for project-local observability.
- Noter can diff this directory to reconstruct a role-level timeline without
  calling into the host's private storage.
- Resume continuity stays with the host's own session store; the archive is an
  additional, project-owned copy.

These helpers are best-effort. Any failure is logged and suppressed; it never
stops the lifecycle.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def claude_project_dir(workspace: Path) -> Path:
    """Return ``~/.claude/projects/<hashed-cwd>/`` for *workspace*.

    Claude Code mangles the absolute cwd path by replacing ``/`` with ``-``;
    the result has a leading ``-`` because absolute paths start with ``/``.
    Example: ``/Users/mjm/MinionsOS_V5`` -> ``-Users-mjm-MinionsOS-V5``.
    """
    resolved = str(workspace.resolve())
    # Replace both '/' and the rarer but real-in-this-codebase '_' with '-'
    # to match the format seen on disk (e.g. ``MinionsOS_V5`` lands as
    # ``MinionsOS-V5`` under ~/.claude/projects/).
    hashed = resolved.replace("/", "-").replace("_", "-")
    return Path.home() / ".claude" / "projects" / hashed


def find_claude_session_file(
    workspace: Path,
    started_after: float,
) -> Path | None:
    """Return the most recently-modified Claude session jsonl for *workspace*,
    filtered to files touched after *started_after* (unix mtime)."""
    proj_dir = claude_project_dir(workspace)
    if not proj_dir.is_dir():
        return None
    candidates = [
        p
        for p in proj_dir.glob("*.jsonl")
        if p.is_file() and p.stat().st_mtime >= started_after - 1.0
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def find_codex_session_file(
    workspace: Path,
    started_after: float,
    scan_days: int = 2,
) -> Path | None:
    """Return the most recent Codex rollout jsonl whose ``session_meta.cwd``
    matches *workspace* and whose mtime is >= *started_after*.

    *scan_days* bounds how far back to scan; for wake windows this is always 0
    or 1 days ago, but we allow a small slack.
    """
    sessions_root = Path.home() / ".codex" / "sessions"
    if not sessions_root.is_dir():
        return None
    resolved = str(workspace.resolve())
    best: tuple[float, Path] | None = None
    # Walk only the last *scan_days+1* day directories to stay cheap.
    day_dirs: list[Path] = []
    today = datetime.now()
    for days in range(scan_days + 1):
        ts = today.timestamp() - days * 86400
        d = datetime.fromtimestamp(ts)
        day_dir = sessions_root / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
        if day_dir.is_dir():
            day_dirs.append(day_dir)
    for day_dir in day_dirs:
        for p in day_dir.glob("rollout-*.jsonl"):
            if not p.is_file():
                continue
            mtime = p.stat().st_mtime
            if mtime < started_after - 1.0:
                continue
            try:
                with p.open("r", encoding="utf-8") as fh:
                    first = fh.readline()
                if not first:
                    continue
                meta = json.loads(first)
                cwd = meta.get("payload", {}).get("cwd", "")
            except Exception:
                continue
            if cwd != resolved:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, p)
    return best[1] if best else None


def _sessions_dir(branch_dir: Path) -> Path:
    return branch_dir / ".minionsos" / "sessions"


def _next_wake_index(branch_dir: Path) -> int:
    """Return the next wake counter by inspecting existing archive filenames."""
    d = _sessions_dir(branch_dir)
    if not d.is_dir():
        return 1
    highest = 0
    for p in d.glob("*-wake*.jsonl"):
        name = p.stem
        marker = name.rfind("-wake")
        if marker < 0:
            continue
        try:
            n = int(name[marker + len("-wake") :])
        except ValueError:
            continue
        if n > highest:
            highest = n
    return highest + 1


def archive_session(
    *,
    host: str,
    workspace: Path,
    started_at: float,
) -> Path | None:
    """Copy the host session jsonl for this wake into the branch archive.

    *host* is ``"claude"`` or ``"codex"``. *workspace* is the role branch dir
    (the subprocess cwd). *started_at* is the unix timestamp when the
    subprocess was launched; we only consider session files whose mtime is at
    or after this.

    Returns the archive path on success, ``None`` if no source session file
    was found or copy failed. All errors are logged, never raised.
    """
    try:
        if host == "claude":
            src = find_claude_session_file(workspace, started_at)
        elif host == "codex":
            src = find_codex_session_file(workspace, started_at)
        else:
            logger.debug("archive_session: unknown host %r; skipping", host)
            return None
        if src is None:
            logger.debug(
                "archive_session: no %s session jsonl found for workspace=%s (started_at=%s)",
                host,
                workspace,
                started_at,
            )
            return None

        dest_dir = _sessions_dir(workspace)
        dest_dir.mkdir(parents=True, exist_ok=True)
        wake_idx = _next_wake_index(workspace)
        ts = time.strftime("%Y-%m-%dT%H-%M-%S", time.localtime(started_at))
        dest = dest_dir / f"{ts}-wake{wake_idx:03d}.jsonl"
        if dest.exists():
            # Extremely rare (same-second next wake). Bump until free.
            bumped = wake_idx
            while dest.exists():
                bumped += 1
                dest = dest_dir / f"{ts}-wake{bumped:03d}.jsonl"
        shutil.copy2(src, dest)
        logger.info(
            "archived %s session: workspace=%s src=%s dest=%s",
            host,
            workspace,
            src,
            dest,
        )
        return dest
    except Exception as exc:
        logger.warning(
            "archive_session failed (host=%s workspace=%s): %s",
            host,
            workspace,
            exc,
        )
        return None
