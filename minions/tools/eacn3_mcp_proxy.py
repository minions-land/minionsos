"""stdio MCP proxy that trims the EACN3 tool surface for Codex.

The EACN3 plugin remains unmodified. This process starts the real plugin as a
child process, forwards JSON-RPC traffic, and filters ``tools/list`` plus
``tools/call`` at the MinionsOS boundary.
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


def allowed_tool_names_for_profile(profile: str | None = None) -> set[str] | None:
    """Return allowed EACN3 tool names, or None for the full unfiltered surface."""
    custom = _csv_names(os.environ.get("EACN3_MCP_TOOLS"))
    if custom:
        return custom

    profile = (profile or os.environ.get("EACN3_MCP_PROFILE", "full")).strip().lower()
    if profile in {"", "full", "all"}:
        return None
    if profile in {"codex", "codex-core"}:
        return set(CODEX_CORE_TOOL_NAMES)

    logger.error("Unknown EACN3_MCP_PROFILE=%s; exposing no EACN3 tools.", profile)
    return set()


def filter_tools(tools: Iterable[dict[str, Any]], allowed: set[str] | None) -> list[dict[str, Any]]:
    """Filter MCP tool descriptors according to the selected profile."""
    if allowed is None:
        return list(tools)
    return [tool for tool in tools if str(tool.get("name", "")) in allowed]


def _request_id(message: dict[str, Any]) -> str | None:
    if "id" not in message:
        return None
    try:
        return json.dumps(message["id"], sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(message["id"])


def _is_blocked_tool_call(message: dict[str, Any], allowed: set[str] | None) -> str | None:
    if allowed is None or message.get("method") != "tools/call":
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    name = str(params.get("name", ""))
    return name if name and name not in allowed else None


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


def proxy_stdio(child_cmd: list[str], allowed: set[str] | None) -> int:
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

    pending_tools_list: set[str] = set()
    pending_lock = threading.Lock()

    def child_stdout_to_parent() -> None:
        for raw in proc.stdout:
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
                    result["tools"] = filter_tools(result["tools"], allowed)
                    out = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
            except Exception:
                pass
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()

    def child_stderr_to_parent() -> None:
        for raw in proc.stderr:
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
                blocked = _is_blocked_tool_call(message, allowed)
                if blocked:
                    _write_json_line(sys.stdout.buffer, _blocked_tool_response(message, blocked))
                    continue
            except Exception:
                pass
            proc.stdin.write(forward)
            proc.stdin.flush()
    finally:
        with contextlib.suppress(Exception):
            proc.stdin.close()

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
    allowed = allowed_tool_names_for_profile()
    logger.warning(
        "EACN3 MCP proxy profile=%s advertised_tools=%s",
        os.environ.get("EACN3_MCP_PROFILE", "full"),
        "full" if allowed is None else len(allowed),
    )
    return proxy_stdio(child, allowed)


if __name__ == "__main__":
    raise SystemExit(main())
