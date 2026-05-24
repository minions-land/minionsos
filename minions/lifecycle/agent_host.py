"""Agent-host command builder for Claude Code (long-lived Role process).

Each MinionsOS Role is a long-lived ``claude`` process that drives its own
event loop via ``mos_await_events``. This module produces the concrete
``claude`` argv plus the initial driver prompt the launcher feeds into the
session.

Codex is not a Role main host; Codex is reachable through the codex-subagent
MCP as a subagent. There is therefore no Codex branch here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from minions.config import GruConfig
from minions.paths import MINIONS_ROOT, project_shared_subdir

logger = logging.getLogger(__name__)

HOT_CACHE_BYTE_LIMIT = 4096
HOT_CACHE_TRUNCATION_LINE = "(truncated for wake-up injection — see book/hot.md for full)"


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
    model: str | None = None,
    mcp_config_path: Path | None = None,
    role_system_paths: list[Path] | None = None,
    claude_session_id: str | None = None,
) -> RoleInvocation:
    """Build the ``claude`` invocation for a long-lived Role.

    The returned ``command`` is the argv to launch (no shell), ``cwd`` is the
    Role's branch workspace (Claude reads ``CLAUDE.md`` / files from cwd), and
    ``initial_prompt`` is the first user message the launcher pipes in.

    Cache optimization: ``system_path`` should point ONLY to the common Role
    contract (``minions/roles/SYSTEM.md``), which is byte-identical across all
    roles. Role-specific instructions (from ``role_system_paths``) are injected
    into the first user message instead, so the system-prompt prefix stays
    identical and maximizes cross-role KV cache sharing at the API level.

    When ``resume=True``, ``--resume <session_name>`` is appended so Claude
    Code reattaches to the prior conversation (Claude Code resolves the value
    against existing session titles in the current cwd's project index).

    When ``claude_session_id`` is provided, ``--session-id <uuid>`` is appended
    so MinionsOS can pre-lock the registry entry against any host-side
    auto-rename hook (see ``minions.lifecycle.sidecar_lock``).

    .. warning::

        ``resume=True`` resets the prompt cache. Claude Code rebuilds the
        cache from scratch on resume and replays the entire prior
        conversation history as new uncached input. For Roles whose
        long-horizon memory already lives in the Draft (L1), cold
        start is strictly cheaper than ``--resume``. The MinionsOS revive
        flow therefore launches with ``resume=False``; ``resume=True`` is
        reserved for manual operator debugging.
    """
    del cfg, project_agent_id  # not used yet; reserved for parity
    cmd: list[str] = [
        "uv",
        "run",
        "--project",
        str(MINIONS_ROOT),
        "claude",
    ]
    if model:
        cmd += ["--model", model]
    if session_name:
        cmd += ["--name", session_name]
    if claude_session_id:
        cmd += ["--session-id", claude_session_id]
    if system_path and system_path.exists():
        cmd += ["--append-system-prompt", f"@{system_path}"]
    cmd += [
        "--mcp-config",
        str(mcp_config_path or (MINIONS_ROOT / ".mcp.json")),
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
        initial_prompt=build_forever_loop_prompt(
            role_name=role_name,
            port=project_port,
            role_system_paths=role_system_paths,
        ),
        session_name=session_name,
    )


def build_forever_loop_prompt(
    *,
    role_name: str,
    port: int | None = None,
    role_system_paths: list[Path] | None = None,
) -> str:
    """Compose the first user message that boots the Role into its forever loop.

    The prompt's job is narrow: anchor the Role's identity, name the
    event-loop tool (``mos_await_events`` for EACN roles, ``mos_noter_wait``
    for Noter), and set the supervisor priority rule. All substantive role
    behavior — boundaries, skills, EACN contract — lives in the appended
    SYSTEM.md and the role-specific ``SYSTEM.md`` re-injected by Claude on
    each launch.

    Cache optimization: role-specific SYSTEM.md content is injected here (in
    the first user message) rather than in ``--append-system-prompt``, so the
    system prompt prefix stays byte-identical across all roles and maximizes
    cross-role KV cache sharing at the API level.
    """
    if role_name == "noter":
        return _build_noter_loop_prompt(port=port, role_system_paths=role_system_paths)
    return _build_eacn_role_loop_prompt(role_name, port=port, role_system_paths=role_system_paths)


def _build_noter_loop_prompt(
    *, port: int | None = None, role_system_paths: list[Path] | None = None
) -> str:
    """Forever-loop prompt for Noter (timer-based, not on EACN)."""
    hot_cache = _hot_cache_block(port)
    hot_cache_section = f"{hot_cache}\n" if hot_cache else ""
    role_contract = _role_contract_block(role_system_paths)
    return (
        "You are the MinionsOS `noter` role. Your event loop runs forever.\n"
        "\n"
        f"{hot_cache_section}"
        "Cold start (this is your first cycle on a fresh process):\n"
        "1. Call `mos_draft_summary()` first to orient on team state.\n"
        "2. Inspect `pending_plans` in the summary. These are events your\n"
        "   previous self received but could not handle in its context;\n"
        "   it persisted them and reset so YOU could handle them.\n"
        "   Drain them now: for each pending_plan node:\n"
        "     - read its full node via `mos_draft_query(related_to=<id>)`,\n"
        "     - perform the work,\n"
        "     - call `mos_draft_annotate` (verified/refuted + evidence_tag)\n"
        "       so it stops surfacing.\n"
        "3. Only after pending_plans is drained, call `mos_noter_wait()`\n"
        "   to enter the steady-state loop below.\n"
        "\n"
        "Steady-state loop:\n"
        "1. Call `mos_noter_wait()`. It blocks for the configured interval\n"
        "   (default 5 min), writing heartbeat files during sleep.\n"
        "2. On wake: flush the Draft (`mos_draft_commit_shared()`),\n"
        "   then read project activity **only since `since_iso`** from\n"
        "   the wake event payload. DO NOT re-read full event/handoff\n"
        "   history each cycle — that grows the turn unboundedly\n"
        "   (see GitHub Issue #14):\n"
        "   - `git log --since=<since_iso>` on `branches/shared/`.\n"
        "   - For `events/*.jsonl`, only tail lines whose timestamp\n"
        "     >= `since_iso`.\n"
        "   - Read only artifacts in `branches/shared/exp/`,\n"
        "     `branches/shared/handoffs/` whose mtime > `since_iso`.\n"
        "   On the very first cycle (`since_iso` is null), read the\n"
        "   last 5 minutes only — do not back-fill ancient history.\n"
        "3. Update the Draft with any new observations.\n"
        "4. Check whether enough time has elapsed since the last published\n"
        "   report (target cadence `noter_report_interval`). If due,\n"
        "   draft and publish a fresh observation report.\n"
        "4b. Context self-check: if Claude Code has surfaced a `/clear`\n"
        "    hint or your accumulated context this turn is large,\n"
        '    call `mos_compact_context(reason="periodic noter\n'
        '    compact", pending_plans=[])` instead of step 5. The\n'
        "    post-compact agent picks up via the cold-start path.\n"
        "5. Call `mos_noter_wait()` again.\n"
        "\n"
        "Cache keepalive: if `mos_noter_wait()` returns a single event of\n"
        "type `cache_keepalive`, that is a wall-clock cliff guard for the\n"
        "prompt cache, NOT a real event. Reply with exactly the literal\n"
        "string `ack` and immediately call `mos_noter_wait()` again. Do\n"
        "not write to the Draft, do not invoke any other tool, do not\n"
        "vary the ack text — keeping the reply byte-stable is what makes\n"
        "this turn cacheable.\n"
        "\n"
        "Context management — compact vs reset:\n"
        "- `mos_compact_context(reason, pending_plans)`: PREFERRED. Persists\n"
        "  pending plans to Draft, then triggers /compact. Process stays\n"
        "  alive, prompt cache stays warm. Use when context is large but\n"
        "  process is healthy. After calling, STOP — produce no more output.\n"
        "- `mos_reset_context(reason)`: HARD RESET. Kills the process entirely.\n"
        "  Use only when behavior has drifted or compact cannot recover.\n"
        "\n"
        "Your output is tool calls. Do not emit a final assistant turn that\n"
        "does not end with `mos_noter_wait()` (or `mos_reset_context()`,\n"
        "which terminates this process so the watchdog respawns it).\n"
        f"{role_contract}"
    )


def _build_eacn_role_loop_prompt(
    role_name: str, *, port: int | None = None, role_system_paths: list[Path] | None = None
) -> str:
    """Forever-loop prompt for EACN-registered roles."""
    hot_cache = _hot_cache_block(port)
    hot_cache_section = f"{hot_cache}\n" if hot_cache else ""
    role_contract = _role_contract_block(role_system_paths)
    return (
        f"You are the MinionsOS `{role_name}` role. Your event loop runs forever.\n"
        "\n"
        f"{hot_cache_section}"
        "Cold start (this is your first cycle on a fresh process):\n"
        "1. Call `mos_draft_summary()` first to orient on team state.\n"
        "2. Inspect `pending_plans` in the summary. These are events your\n"
        "   previous self received but judged unrelated to its context;\n"
        "   it persisted them and reset so YOU could handle them. They\n"
        "   are already dequeued from EACN and will NOT be redelivered.\n"
        "   Drain them now: for each pending_plan node:\n"
        "     - read its full node via `mos_draft_query(related_to=<id>)`,\n"
        "     - perform the work (Plan → Dispatch subagent → Verify →\n"
        "       emit any EACN response),\n"
        "     - call `mos_draft_annotate` (verified/refuted + evidence_tag)\n"
        "       so it stops surfacing.\n"
        "3. Only after pending_plans is drained, call `mos_await_events()`\n"
        "   to enter the steady-state loop below.\n"
        "\n"
        "Steady-state loop:\n"
        "1. Call `mos_await_events()`. It blocks until your project-local EACN3\n"
        "   queue delivers actionable content (real events, or after ~5 minutes\n"
        "   of silence a synthetic `idle_check`).\n"
        "2. Triage the batch — split BEFORE executing:\n"
        "   a. Gru first: scan for events involving Gru (sender_id=`gru`,\n"
        "      initiator_id=`gru`, or events targeting the `gru` queue).\n"
        "      Handle Gru-related events FIRST regardless of relevance.\n"
        "   b. Lightweight replies: messages you can answer directly without\n"
        "      subagent work (ack, status, short clarification, yes/no).\n"
        "      Reply immediately via `eacn3_send_message` (<30 words).\n"
        "      Do NOT dispatch a subagent for these.\n"
        "   c. For each remaining event, classify:\n"
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
        "     persist completed work to the Draft, AND persist each\n"
        "     unrelated event as a node with\n"
        "     `metadata.pending_plan = true` (do NOT execute them now).\n"
        "     Then call `mos_compact_context(reason=..., pending_plans=[...])`\n"
        "     (preferred — keeps cache warm) or `mos_reset_context(reason=...)`\n"
        "     (only if behavior has drifted). After compact, STOP — produce\n"
        "     no more output. You wake in compressed context; call\n"
        "     `mos_await_events()` to resume.\n"
        "\n"
        "Cache keepalive: if `mos_await_events()` returns a single event of\n"
        "type `cache_keepalive`, that is a wall-clock cliff guard for the\n"
        "prompt cache, NOT a real event. Reply with exactly the literal\n"
        "string `ack` and immediately call `mos_await_events()` again. Do\n"
        "not write to the Draft, do not send EACN messages, do not\n"
        "invoke any other tool, do not vary the ack text — keeping the\n"
        "reply byte-stable is what makes this turn cacheable.\n"
        "\n"
        "Context management — compact vs reset:\n"
        "- `mos_compact_context(reason, pending_plans)`: PREFERRED. Persists\n"
        "  pending plans to Draft, then triggers /compact. Process stays\n"
        "  alive, prompt cache stays warm (no cold start). Use when context is\n"
        "  large but process is healthy. After calling, STOP — produce no more\n"
        "  output. You wake up in compressed context; call mos_await_events().\n"
        "- `mos_reset_context(reason)`: HARD RESET. Kills the process entirely.\n"
        "  Use only when behavior has drifted, SYSTEM.md changed externally,\n"
        "  or compact cannot recover coherent state. Costs ~50k uncached\n"
        "  tokens on cold start.\n"
        "\n"
        "Your output is tool calls. Do not emit a final assistant turn that\n"
        "does not end with `mos_await_events()` (or `mos_reset_context()`,\n"
        "which terminates this process so the watchdog respawns it).\n"
        f"{role_contract}"
    )


def _role_contract_block(role_system_paths: list[Path] | None = None) -> str:
    """Return the role-specific contract text for injection into the user message.

    Reads each path in *role_system_paths* and concatenates them under a
    ``[Role-Specific Contract]`` header. Returns empty string if no paths
    are provided or none exist.
    """
    if not role_system_paths:
        return ""
    parts: list[str] = []
    for path in role_system_paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(text)
    if not parts:
        return ""
    combined = "\n\n---\n\n".join(parts)
    return (
        "\n\n"
        "## [Role-Specific Contract]\n"
        "\n"
        "The following role-specific rules supplement the common contract in\n"
        "the system prompt. They take precedence on role-specific matters.\n"
        "\n"
        f"{combined}\n"
    )


def _hot_cache_block(port: int | None = None) -> str | None:
    """Return the wake-up hot-cache prompt block for *port*, if available."""
    resolved_port = _resolve_hot_cache_port(port)
    if resolved_port is None:
        return None

    path = project_shared_subdir(resolved_port, "book") / "hot.md"
    try:
        if not path.exists() or path.stat().st_size == 0:
            return None
        raw = path.read_bytes()
        full_content = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("failed to read book hot cache from %s: %s", path, exc)
        return None

    if not full_content.strip():
        return None

    truncated = len(raw) > HOT_CACHE_BYTE_LIMIT
    content = (
        raw[:HOT_CACHE_BYTE_LIMIT].decode("utf-8", errors="ignore") if truncated else full_content
    )
    if truncated:
        content = f"{content}\n" if not content.endswith("\n") else content
        content = f"{content}{HOT_CACHE_TRUNCATION_LINE}\n"
    elif not content.endswith("\n"):
        content = f"{content}\n"

    return (
        "## [Hot Cache]\n"
        "\n"
        "Brief rolling cache of recent project-wide context, maintained by\n"
        "Noter. Read silently — do NOT explicitly cite this in EACN messages.\n"
        "\n"
        f"{content}"
    )


def _resolve_hot_cache_port(port: int | None) -> int | None:
    """Resolve the project port used to locate the book hot cache."""
    if port is not None:
        return port

    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if not raw:
        logger.debug("MINIONS_PROJECT_PORT not set; omitting book hot cache")
        return None

    try:
        return int(raw)
    except ValueError:
        logger.warning("MINIONS_PROJECT_PORT is not a valid int: %r", raw)
        return None
