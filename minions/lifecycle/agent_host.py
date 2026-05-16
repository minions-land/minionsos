"""Agent-host command builder for Claude Code (long-lived Role process).

Each MinionsOS Role is a long-lived ``claude`` process that drives its own
event loop via ``mos_await_events``. This module produces the concrete
``claude`` argv plus the initial driver prompt the launcher feeds into the
session.

Codex is not a Role main host; Codex is reachable through the codex-bridge
MCP as a subagent. There is therefore no Codex branch here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from minions.config import GruConfig
from minions.paths import MINIONS_ROOT


@dataclass(frozen=True)
class RoleInvocation:
    """Concrete subprocess invocation for one Role's long-lived process."""

    host_name: str
    command: list[str]
    cwd: Path
    initial_prompt: str
    session_name: str


def build_role_invocation(
    *,
    cfg: GruConfig,
    role_name: str,
    project_port: int,
    project_agent_id: str,
    system_path: Path | None,
    allowed_tools: str,
    workspace: Path,
    session_name: str,
) -> RoleInvocation:
    """Build the ``claude`` invocation for a long-lived Role.

    The returned ``command`` is the argv to launch (no shell), ``cwd`` is the
    Role's branch workspace (Claude reads ``CLAUDE.md`` / files from cwd), and
    ``initial_prompt`` is the first user message the launcher pipes in. The
    Role's SYSTEM.md is appended to Claude's system prompt so role rules sit
    outside the conversation body and survive auto-compact.
    """
    del cfg, project_port, project_agent_id  # not used yet; reserved for parity
    cmd: list[str] = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "claude",
    ]
    if session_name:
        cmd += ["--name", session_name]
    if system_path and system_path.exists():
        cmd += ["--append-system-prompt", f"@{system_path}"]
    cmd += [
        "--mcp-config",
        str(MINIONS_ROOT / ".mcp.json"),
        "--allowed-tools",
        allowed_tools,
        "--permission-mode",
        "bypassPermissions",
    ]
    return RoleInvocation(
        host_name="claude",
        command=cmd,
        cwd=workspace if workspace.exists() else MINIONS_ROOT,
        initial_prompt=build_forever_loop_prompt(role_name=role_name),
        session_name=session_name,
    )


def build_forever_loop_prompt(*, role_name: str) -> str:
    """Compose the first user message that boots the Role into its forever loop.

    The prompt's job is narrow: anchor the Role's identity, name the
    event-loop tool (``mos_await_events``), and set the supervisor priority
    rule. All substantive role behavior — boundaries, skills, EACN
    contract — lives in the appended SYSTEM.md and the role-specific
    ``SYSTEM.md`` re-injected by Claude on each launch.
    """
    return (
        f"You are the MinionsOS `{role_name}` role. Your event loop runs forever.\n"
        "\n"
        "Loop:\n"
        "1. Call `mos_await_events()`. It blocks until your project-local EACN3\n"
        "   queue delivers actionable content (real events, or after ~5 minutes\n"
        "   of silence a synthetic `idle_check`).\n"
        "2. When it returns:\n"
        "   a. Scan first for events involving Gru (sender_id=`gru`,\n"
        "      initiator_id=`gru`, or events targeting the `gru` queue that\n"
        "      mention you). Handle Gru-related events FIRST — supervisor\n"
        "      consistency is non-negotiable, never starve Gru traffic.\n"
        "   b. Then run think-then-act on the remaining events: Plan in 3-6\n"
        "      lines, Dispatch substantive work to a host-native subagent\n"
        "      (Task tool), Verify the subagent's return, emit EACN responses\n"
        "      with `eacn3_send_message` / `eacn3_create_task` /\n"
        "      `eacn3_submit_bid` / `eacn3_submit_result`.\n"
        "3. When the current cycle is done, call `mos_await_events()` again.\n"
        "\n"
        "When the current context is no longer serving the next task — at a\n"
        "natural boundary between coherent batches — checkpoint durable state\n"
        "to the Exploration DAG (`mos_dag_append` / `mos_dag_annotate`), then\n"
        "call `mos_reset(reason=...)` to clear conversation context. After\n"
        "reset call `mos_dag_summary()` to re-orient and `mos_await_events()`\n"
        "to receive the next event.\n"
        "\n"
        "Your output is tool calls. Do not emit a final assistant turn that\n"
        "does not end with `mos_await_events()` — the process must stay\n"
        "resident. Begin now: call `mos_await_events()`.\n"
    )
