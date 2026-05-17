"""Agent-host command builder for Claude Code (long-lived Role process).

Each MinionsOS Role is a long-lived ``claude`` process that drives its own
event loop via ``mos_await_events``. This module produces the concrete
``claude`` argv plus the initial driver prompt the launcher feeds into the
session.

Codex is not a Role main host; Codex is reachable through the codex-subagent
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
    resume: bool = False,
) -> RoleInvocation:
    """Build the ``claude`` invocation for a long-lived Role.

    The returned ``command`` is the argv to launch (no shell), ``cwd`` is the
    Role's branch workspace (Claude reads ``CLAUDE.md`` / files from cwd), and
    ``initial_prompt`` is the first user message the launcher pipes in. The
    Role's SYSTEM.md is appended to Claude's system prompt so role rules sit
    outside the conversation body and survive auto-compact.

    When ``resume=True``, ``--resume <session_name>`` is appended so Claude
    Code reattaches to the prior conversation (Claude Code resolves the value
    against existing session titles in the current cwd's project index). Use
    on revive; leave False on first launch.
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
    if resume and session_name:
        cmd += ["--resume", session_name]
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
        "Cold start (this is your first cycle on a fresh process):\n"
        "1. Call `mos_dag_summary()` first to orient on team state.\n"
        "2. Inspect `pending_plans` in the summary. These are events your\n"
        "   previous self received but judged unrelated to its context;\n"
        "   it persisted them and reset so YOU could handle them. They\n"
        "   are already dequeued from EACN and will NOT be redelivered.\n"
        "   Drain them now: for each pending_plan node:\n"
        "     - read its full node via `mos_dag_query(related_to=<id>)`,\n"
        "     - perform the work (Plan → Dispatch subagent → Verify →\n"
        "       emit any EACN response),\n"
        "     - call `mos_dag_annotate` (verified/refuted + evidence_tag)\n"
        "       so it stops surfacing.\n"
        "3. Only after pending_plans is drained, call `mos_await_events()`\n"
        "   to enter the steady-state loop below.\n"
        "\n"
        "Steady-state loop:\n"
        "1. Call `mos_await_events()`. It blocks until your project-local EACN3\n"
        "   queue delivers actionable content (real events, or after ~5 minutes\n"
        "   of silence a synthetic `idle_check`).\n"
        "2. Think-then-act — split the batch BEFORE executing:\n"
        "   a. Gru first: scan for events involving Gru (sender_id=`gru`,\n"
        "      initiator_id=`gru`, or events targeting the `gru` queue).\n"
        "      Handle Gru-related events FIRST regardless of relevance.\n"
        "   b. For each remaining event, classify:\n"
        "      - RELEVANT: continues or builds on this process's current\n"
        "        context (same hypothesis, awaited reply, subagent return,\n"
        "        same paper section).\n"
        "      - UNRELATED: a new direction with no overlap.\n"
        "3. Execute the RELEVANT events now (Plan → Dispatch subagent →\n"
        "   Verify → respond via `eacn3_send_message` /\n"
        "   `eacn3_create_task` / `eacn3_submit_bid` / `eacn3_submit_result`).\n"
        "4. Decide next step:\n"
        "   - No unrelated events → call `mos_await_events()` again.\n"
        "   - Unrelated events present → invoke `cognitive-checkpoint`:\n"
        "     persist completed work to the DAG, AND persist each\n"
        "     unrelated event as a node with\n"
        "     `metadata.pending_plan = true` (do NOT execute them now).\n"
        "     Then call `mos_reset_context(reason=...)`. The respawned\n"
        "     process drains those pending plans before its own\n"
        "     `mos_await_events`.\n"
        "\n"
        "Your output is tool calls. Do not emit a final assistant turn that\n"
        "does not end with `mos_await_events()` (or `mos_reset_context()`,\n"
        "which terminates this process so the watchdog respawns it).\n"
    )
