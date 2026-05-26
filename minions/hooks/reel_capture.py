#!/usr/bin/env python3
"""PostToolUse hook: capture subagent/codex calls into Reel V2 index (L0).

Trigger: tool_name in {Agent, Task, mcp__codex-subagent__codex}.
No output_file requirement — we index native Claude/Codex session files.

Design:
- Zero role burden: roles never call reel tools; capture is automatic.
- Lightweight index: no transcript copying; pointers to native jsonl files.
- Role-private: each role writes to its own branch reel-index.jsonl.

Index file: branches/<role>/reel-index.jsonl (flat, one line per event).

Index entry shape:
  {"ref": "<role>/<sessionId>/<tool_use_id>",
   "ts": "<iso>",
   "kind": "subagent|codex",
   "tool_name": "...",
   "claude_jsonl": "/abs/path/to/<sid>.jsonl",
   "codex_children": ["/abs/path/.../rollout-*.jsonl"],
   "draft_node_refs": []}

Exits 0 always (advisory). Emits JSON to stderr when triggered.
Performance budget: <100ms per call.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

CAPTURE_TOOLS = {"Agent", "Task", "mcp__codex-subagent__codex"}

TOOL_TO_KIND = {
    "Agent": "subagent",
    "Task": "subagent",
    "mcp__codex-subagent__codex": "codex",
}

CODEX_MATCH_WINDOW_S = 30


def _encode_cwd(cwd: str) -> str:
    """Encode a filesystem path as a Claude projects directory name."""
    return cwd.replace("/", "-")


def _find_claude_jsonl(session_id: str, cwd: str) -> str:
    """Locate the native Claude session jsonl file."""
    # Try env var first (most reliable)
    env_path = os.environ.get("CLAUDE_SESSION_FILE", "")
    if env_path and Path(env_path).exists():
        return env_path

    # Fall back to computed path
    encoded = _encode_cwd(cwd)
    candidate = Path.home() / ".claude" / "projects" / encoded / f"{session_id}.jsonl"
    if candidate.exists():
        return str(candidate)

    return ""


def _find_codex_children(cwd: str, ts: datetime) -> list[str]:
    """Find Codex session jsonl files matching cwd and timestamp window."""
    sessions_root = Path.home() / ".codex" / "sessions"
    date_dir = sessions_root / ts.strftime("%Y") / ts.strftime("%m") / ts.strftime("%d")
    if not date_dir.exists():
        return []

    results: list[str] = []
    try:
        for p in sorted(date_dir.glob("rollout-*.jsonl")):
            # Extract timestamp from filename: rollout-<ts_ms>-<sid>.jsonl
            stem = p.stem  # rollout-<ts_ms>-<sid>
            parts = stem.split("-", 2)
            if len(parts) < 2:
                continue
            try:
                file_ts_ms = int(parts[1])
                file_ts = datetime.fromtimestamp(file_ts_ms / 1000, tz=UTC)
                delta = abs((file_ts - ts).total_seconds())
                if delta <= CODEX_MATCH_WINDOW_S:
                    results.append(str(p))
            except (ValueError, OSError):
                continue
    except OSError:
        pass
    return results


def _append_reel_index(index_path: Path, entry: dict) -> None:
    """Append one JSON line to the reel index using O_APPEND atomic write."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with index_path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(line)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def main() -> None:
    raw = sys.stdin.read()
    try:
        hook = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name: str = hook.get("tool_name", "")
    if tool_name not in CAPTURE_TOOLS:
        sys.exit(0)

    # Required env vars
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    session_id = os.environ.get("CLAUDE_SESSION_ID", "").strip()
    project_port = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    cwd = os.environ.get("PWD", os.getcwd())

    if not role or not project_port:
        sys.exit(0)

    # Extract tool_use_id from hook payload, fall back to uuid4
    tool_use_id: str = hook.get("tool_use_id", "")
    if not tool_use_id:
        import uuid
        tool_use_id = str(uuid.uuid4())

    now = datetime.now(UTC)
    kind = TOOL_TO_KIND[tool_name]

    # Locate native session files
    claude_jsonl = _find_claude_jsonl(session_id, cwd) if session_id else ""
    codex_children: list[str] = []
    if kind == "codex":
        codex_children = _find_codex_children(cwd, now)

    # Build index entry
    ref = f"{role}/{session_id or 'unknown'}/{tool_use_id}"
    entry = {
        "ref": ref,
        "ts": now.isoformat(),
        "kind": kind,
        "tool_name": tool_name,
        "claude_jsonl": claude_jsonl,
        "codex_children": codex_children,
        "draft_node_refs": [],
    }

    # Locate project workspace
    from minions.paths import project_role_workspace
    try:
        workspace = project_role_workspace(int(project_port), role)
        index_path = workspace / "reel-index.jsonl"
        _append_reel_index(index_path, entry)
        json.dump({"captured": ref, "kind": kind}, sys.stderr)
        sys.stderr.write("\n")
    except Exception as exc:  # advisory hook — never crash caller
        json.dump({"reel_capture_error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
