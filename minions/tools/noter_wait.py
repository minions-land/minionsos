"""mos_noter_wait — Timer-based wait tool for the Noter role.

Noter is not registered on EACN3 and does not use ``mos_await_events``.
Instead it sleeps for a configurable interval (``noter_periodic_interval``,
default 3 min) and wakes to flush the Draft (L1) and observe project
state.

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
        "not write to the Draft, do not send EACN messages, do not "
        "invoke any other tool."
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
        return 180


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


def _nudge_path(port: int) -> Path:
    """Return the nudge marker path for this project's Noter."""
    from minions.paths import project_state_dir

    return project_state_dir(port) / ".noter_nudge"


def _check_and_clear_nudge(port: int) -> bool:
    """Return True and clear the marker if a nudge is pending."""
    path = _nudge_path(port)
    if path.exists():
        import contextlib

        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        return True
    return False


def nudge_noter(port: int) -> None:
    """Write a nudge marker so Noter wakes early on next sleep-chunk check.

    Called by mos_publish_to_shared after a successful publish. The marker
    is a zero-byte file; its existence is the signal. Noter checks every
    30s during its sleep loop and wakes immediately if found.
    """
    path = _nudge_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.touch(exist_ok=True)
    except OSError as exc:
        logger.debug("nudge_noter: failed to touch %s: %s", path, exc)


_SHELF_GRAPH_SOURCES = ("book", "notes", "ethics", "exp")
_SHELF_GRAPH_REBUILD_TIMEOUT = 300  # seconds


def _newest_source_mtime(workspace: Path | None) -> float:
    """Return the newest mtime under shared/{book,notes,ethics,exp}/, or 0.0."""
    if workspace is None:
        return 0.0
    shared = workspace.parent / "shared"
    if not shared.exists():
        return 0.0
    newest = 0.0
    for sub in _SHELF_GRAPH_SOURCES:
        root = shared / sub
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                m = path.stat().st_mtime
            except OSError:
                continue
            if m > newest:
                newest = m
    return newest


def _maybe_rebuild_shelf_graph(workspace: Path | None) -> dict[str, Any]:
    """Rebuild branches/shared/atlas/atlas.json when stale.

    Compares the existing graph's mtime against the newest source mtime
    under shared/{book,notes,ethics,exp}/. Only invokes the heavy
    `mcp-servers/graphify/extract.py` shell-out when sources are newer.

    Returns a dict embedded into the periodic-wake event:
        {"rebuilt": True, "node_count": N, "duration_s": float, ...}
        {"rebuilt": False, "reason": "..."}.

    Never raises — graphify failures must NOT crash Noter's wake loop.
    """
    try:
        if workspace is None:
            return {"rebuilt": False, "reason": "no workspace"}
        shared = workspace.parent / "shared"
        graph_path = shared / "atlas" / "atlas.json"
        newest_src = _newest_source_mtime(workspace)
        if newest_src == 0.0:
            return {"rebuilt": False, "reason": "no source files"}
        graph_mtime = graph_path.stat().st_mtime if graph_path.exists() else 0.0
        # Treat a stub graph (very small file) as needing rebuild even if newer.
        if graph_path.exists() and graph_path.stat().st_size > 200 and graph_mtime >= newest_src:
            return {"rebuilt": False, "reason": "graph fresh"}

        # Resolve port from workspace path: project_{port}/branches/<role>
        port = int(workspace.parent.parent.name.removeprefix("project_"))
    except Exception as exc:
        logger.warning("atlas rebuild precheck failed: %s", exc)
        return {"rebuilt": False, "reason": f"precheck error: {exc}"}

    repo_root = Path(__file__).resolve().parent.parent.parent
    extract_script = repo_root / "mcp-servers" / "graphify" / "extract.py"
    venv_python = repo_root / "mcp-servers" / "graphify" / ".venv" / "bin" / "python"
    if not extract_script.exists() or not venv_python.exists():
        return {
            "rebuilt": False,
            "reason": (
                "graphify venv not installed — run "
                "`cd mcp-servers/graphify && VIRTUAL_ENV=$PWD/.venv uv pip install -e .`"
            ),
        }

    cmd = [str(venv_python), str(extract_script), "--port", str(port)]
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SHELF_GRAPH_REBUILD_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("atlas rebuild timed out after %ds", _SHELF_GRAPH_REBUILD_TIMEOUT)
        return {
            "rebuilt": False,
            "reason": f"timeout after {_SHELF_GRAPH_REBUILD_TIMEOUT}s",
        }
    except Exception as exc:
        logger.warning("atlas rebuild subprocess failed: %s", exc)
        return {"rebuilt": False, "reason": f"subprocess error: {exc}"}

    duration = time.monotonic() - started
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").strip().splitlines()[-20:])
        logger.info("atlas rebuild non-zero exit (rc=%d): %s", result.returncode, tail)
        return {
            "rebuilt": False,
            "reason": f"extract exit {result.returncode}",
            "stderr_tail": tail,
            "duration_s": round(duration, 2),
        }

    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        payload = {}
    return {
        "rebuilt": bool(payload.get("rebuilt")),
        "node_count": payload.get("node_count", 0),
        "edge_count": payload.get("edge_count", 0),
        "file_count": payload.get("file_count", 0),
        "duration_s": round(duration, 2),
        "reason": payload.get("reason", ""),
    }


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

        if _check_and_clear_nudge(port):
            logger.info("noter_wait: nudge detected, waking early at %.1fs", elapsed)
            break

    shelf_graph = _maybe_rebuild_shelf_graph(workspace)
    # Register project graph into global cross-project Atlas (Gru reads this).
    try:
        from minions.tools.shelf import mos_shelf_register

        shelf_global_reg = mos_shelf_register(port)
    except Exception as exc:
        logger.warning("atlas registration failed: %s", exc)
        shelf_global_reg = {"registered": False, "reason": str(exc)}

    try:
        from minions.tools.book import mos_book_lint

        lint_result = mos_book_lint(port=port)
    except Exception as exc:
        logger.warning("book lint failed: %s", exc)
        lint_result = {"error": str(exc)}

    return {
        "count": 1,
        "events": [
            {
                "type": "periodic_wake",
                "slept_seconds": int(elapsed),
                "delta": {
                    "shared_branch": _shared_branch_delta(workspace),
                    "events": _events_jsonl_delta(port),
                    "shelf_graph": shelf_graph,
                    "shelf_global": shelf_global_reg,
                    "book_lint": lint_result,
                },
                "suggested_action": (
                    "Periodic wake. Flush the Draft "
                    "(mos_draft_commit_shared), read recent EACN "
                    "activity and shared branch changes, update the "
                    "Draft if needed, and consider whether a fresh "
                    "observation report is due."
                ),
            }
        ],
    }
