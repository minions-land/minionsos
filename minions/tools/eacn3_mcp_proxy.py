"""stdio MCP proxy that trims the EACN3 tool surface for Codex.

The EACN3 plugin remains unmodified. This process starts the real plugin as a
child process, forwards JSON-RPC traffic, and filters ``tools/list`` plus
``tools/call`` at the MinionsOS boundary.

Profile selection (via ``EACN3_MCP_PROFILE``):

- ``full`` / ``all`` / unset: no filtering (dev default).
- ``codex-core``: legacy fixed subset, frozen before the MOS Agent Pool
  migration. Kept for backward compatibility only. It exposes drain tools
  (``eacn3_await_events`` / ``eacn3_next`` / ``eacn3_get_events``) and
  write tools (``eacn3_send_message`` / ``eacn3_create_task``) that MOS
  now owns, and it hides several read-safe tools internal roles need.
  Do not use for new role launches.
- ``minions-role``: per-role filtering that mirrors
  :func:`minions.config.resolve_whitelist` on the ``eacn3_*`` prefix.
  This is the profile MinionsOS uses at role wake-up on both hosts so
  Codex and Claude see the same EACN3 surface for the same role.

``MINIONS_ROLE_NAME`` / ``MINIONS_AGENT_TYPE`` are read for ``minions-role``
and are set by ``minions/lifecycle/role.py`` when launching a bounded wake.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Iterable
from fnmatch import fnmatchcase
from typing import Any

logger = logging.getLogger(__name__)

CODEX_CORE_TOOL_NAMES = frozenset(
    {
        "eacn3_connect",
        "eacn3_claim_agent",
        "eacn3_register_agent",
        "eacn3_list_my_agents",
        "eacn3_next",
        "eacn3_get_events",
        "eacn3_await_events",
        "eacn3_send_message",
        "eacn3_get_messages",
        "eacn3_list_sessions",
        "eacn3_create_task",
        "eacn3_create_subtask",
        "eacn3_get_task",
        "eacn3_get_task_status",
        "eacn3_list_open_tasks",
        "eacn3_list_tasks",
        "eacn3_submit_bid",
        "eacn3_submit_result",
        "eacn3_reject_task",
        "eacn3_get_task_results",
        "eacn3_select_result",
        "eacn3_close_task",
        "eacn3_update_deadline",
        "eacn3_update_discussions",
        "eacn3_confirm_budget",
        "eacn3_invite_agent",
    }
)


def _csv_names(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def _role_eacn3_patterns() -> list[str] | None:
    """Return the ``eacn3_*`` patterns from the active role's whitelist.

    Returns ``None`` (full surface) if the role/agent-type env vars are not
    set, which happens when a developer runs ``codex`` by hand on this
    checkout. In role wake-ups ``role.py`` always sets both.
    """
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    agent_type = (os.environ.get("MINIONS_AGENT_TYPE", "main").strip() or "main").lower()
    if not role:
        return None
    if agent_type not in {"main", "subagent"}:
        agent_type = "main"
    try:
        from minions.config import resolve_whitelist
    except Exception as exc:
        logger.warning("minions-role profile: resolve_whitelist unavailable: %s", exc)
        return None
    patterns = resolve_whitelist(role, agent_type)
    eacn_patterns = [p for p in patterns if p == "eacn3_*" or p.startswith("eacn3_")]
    return eacn_patterns


def _patterns_match(name: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(name, pat) for pat in patterns)


def allowed_tool_surface(
    profile: str | None = None,
) -> tuple[set[str] | None, list[str] | None]:
    """Return ``(exact_names, fnmatch_patterns)`` — either may be ``None``.

    - ``exact_names`` is a literal name set for profiles that enumerate tools.
    - ``fnmatch_patterns`` lets role-scoped profiles carry ``eacn3_*`` wildcards.
    - If both are ``None`` the full surface is exposed.
    """
    custom = _csv_names(os.environ.get("EACN3_MCP_TOOLS"))
    if custom:
        return custom, None

    profile = (profile or os.environ.get("EACN3_MCP_PROFILE", "full")).strip().lower()
    if profile in {"", "full", "all"}:
        return None, None
    if profile in {"codex", "codex-core"}:
        return set(CODEX_CORE_TOOL_NAMES), None
    if profile in {"minions-role", "role"}:
        patterns = _role_eacn3_patterns()
        if patterns is None:
            return None, None
        return None, patterns

    logger.error("Unknown EACN3_MCP_PROFILE=%s; exposing no EACN3 tools.", profile)
    return set(), None


def allowed_tool_names_for_profile(profile: str | None = None) -> set[str] | None:
    """Legacy helper retained for tests: returns an exact-name set or ``None``.

    Role-scoped (``minions-role``) profiles use fnmatch patterns and cannot be
    expressed as a flat name set; callers needing full fidelity should use
    :func:`allowed_tool_surface`.
    """
    exact, patterns = allowed_tool_surface(profile=profile)
    if patterns is not None and exact is None:
        return None  # wildcard-based profile — caller should switch to allowed_tool_surface
    return exact


def filter_tools(
    tools: Iterable[dict[str, Any]],
    allowed: set[str] | None,
    patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter MCP tool descriptors according to the selected profile."""
    if allowed is None and patterns is None:
        return list(tools)
    result: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name", ""))
        if allowed is not None and name in allowed:
            result.append(tool)
            continue
        if patterns is not None and _patterns_match(name, patterns):
            result.append(tool)
    return result


def _request_id(message: dict[str, Any]) -> str | None:
    if "id" not in message:
        return None
    try:
        return json.dumps(message["id"], sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(message["id"])


def _is_blocked_tool_call(
    message: dict[str, Any],
    allowed: set[str] | None,
    patterns: list[str] | None = None,
) -> str | None:
    if allowed is None and patterns is None:
        return None
    if message.get("method") != "tools/call":
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    name = str(params.get("name", ""))
    if not name:
        return None
    if allowed is not None and name in allowed:
        return None
    if patterns is not None and _patterns_match(name, patterns):
        return None
    return name


def _blocked_tool_response(message: dict[str, Any], tool_name: str) -> dict[str, Any]:
    response: dict[str, Any] = {
        "jsonrpc": message.get("jsonrpc", "2.0"),
        "error": {
            "code": -32601,
            "message": f"EACN3 MCP tool {tool_name!r} is not exposed in this profile.",
        },
    }
    if "id" in message:
        response["id"] = message["id"]
    return response


def _write_json_line(stream: Any, message: dict[str, Any]) -> None:
    stream.write((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
    stream.flush()


def proxy_stdio(
    child_cmd: list[str],
    allowed: set[str] | None,
    patterns: list[str] | None = None,
) -> int:
    """Run the child MCP server and proxy stdio until either side closes."""
    proc = subprocess.Popen(
        child_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdin = proc.stdin
    stdout = proc.stdout
    stderr = proc.stderr

    pending_tools_list: set[str] = set()
    pending_lock = threading.Lock()

    def child_stdout_to_parent() -> None:
        for raw in stdout:
            out = raw
            try:
                message = json.loads(raw.decode("utf-8"))
                msg_id = _request_id(message)
                with pending_lock:
                    is_tools_list = msg_id is not None and msg_id in pending_tools_list
                    if is_tools_list:
                        pending_tools_list.discard(msg_id)
                result = message.get("result")
                if (
                    is_tools_list
                    and isinstance(result, dict)
                    and isinstance(result.get("tools"), list)
                ):
                    result["tools"] = filter_tools(result["tools"], allowed, patterns)
                    out = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
            except Exception:
                pass
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()

    def child_stderr_to_parent() -> None:
        for raw in stderr:
            sys.stderr.buffer.write(raw)
            sys.stderr.buffer.flush()

    out_thread = threading.Thread(target=child_stdout_to_parent, daemon=True)
    err_thread = threading.Thread(target=child_stderr_to_parent, daemon=True)
    out_thread.start()
    err_thread.start()

    try:
        for raw in sys.stdin.buffer:
            forward = raw
            try:
                message = json.loads(raw.decode("utf-8"))
                if message.get("method") == "tools/list":
                    msg_id = _request_id(message)
                    if msg_id is not None:
                        with pending_lock:
                            pending_tools_list.add(msg_id)
                blocked = _is_blocked_tool_call(message, allowed, patterns)
                if blocked:
                    _write_json_line(sys.stdout.buffer, _blocked_tool_response(message, blocked))
                    continue
            except Exception:
                pass
            stdin.write(forward)
            stdin.flush()
    finally:
        with contextlib.suppress(Exception):
            stdin.close()

    return proc.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "child",
        nargs=argparse.REMAINDER,
        help="Child MCP command after --. Defaults to node EACN3/plugin/dist/server.js.",
    )
    args = parser.parse_args(argv)
    child = list(args.child)
    if child and child[0] == "--":
        child = child[1:]
    if not child:
        child = ["node", "EACN3/plugin/dist/server.js"]

    logging.basicConfig(level=os.environ.get("MINIONS_LOG_LEVEL", "WARNING"))
    allowed, patterns = allowed_tool_surface()
    if allowed is None and patterns is None:
        advertised: str | int = "full"
    elif patterns is not None and allowed is None:
        advertised = f"patterns={len(patterns)}"
    else:
        advertised = len(allowed or set())
    logger.warning(
        "EACN3 MCP proxy profile=%s role=%s agent_type=%s advertised_tools=%s",
        os.environ.get("EACN3_MCP_PROFILE", "full"),
        os.environ.get("MINIONS_ROLE_NAME", ""),
        os.environ.get("MINIONS_AGENT_TYPE", ""),
        advertised,
    )
    return proxy_stdio(child, allowed, patterns)


if __name__ == "__main__":
    raise SystemExit(main())
