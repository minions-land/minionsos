"""Agent-host command builder for Claude Code (long-lived Role process).

Each MinionsOS Role is a long-lived ``claude`` process that drives its own
event loop via ``mos_await_events``. This module produces the concrete
``claude`` argv plus the initial driver prompt the launcher feeds into the
session.

Claude Code is the only Role host.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from minions.config import GruConfig
from minions.errors import RoleError
from minions.paths import MINIONS_ROOT, project_shared_subdir

logger = logging.getLogger(__name__)

HOT_CACHE_BYTE_LIMIT = 4096
HOT_CACHE_TRUNCATION_LINE = "(truncated for wake-up injection — see book/hot.md for full)"

# Per-role ToolSearch warmup lists. Cold-start expert / ethics roles
# repeatedly missed deferred-tool schemas in project_37596 logs (e.g.
# expert-gpu-perf: "The ToolSearch for MinionsOS tools didn't find them as
# deferred tools"; many minionsos calls with retries on args wrapping).
# `ENABLE_TOOL_SEARCH=auto:30` (set in role_launcher) is a Claude-Code internal
# heuristic that warms by call frequency; on cold start no calls have been made
# yet, so high-frequency role-specific tools start deferred and keyword search
# misses them. We pin the cold-start warmup explicitly.
# Frequencies derived from project_37596/logs/role-*.log (CODA-MoE, 2026-05-27).
_TOOL_WARMUP: dict[str, tuple[str, ...]] = {
    "expert": (
        "mos_await_events",
        "mos_draft_summary",
        "mos_draft_query",
        "mos_draft_append",
        "mos_draft_annotate",
        "mos_publish_to_shared",
        "mos_compact_context",
        "mos_exp_run",
        "mos_exp_status",
        "mos_exp_list",
        "eacn3_send_message",
        "eacn3_create_task",
        "eacn3_submit_bid",
        "eacn3_submit_result",
    ),
    "ethics": (
        "mos_await_events",
        "mos_draft_summary",
        "mos_draft_query",
        "mos_draft_append",
        "mos_draft_annotate",
        "mos_draft_commit_shared",
        "mos_book_ingest",
        "mos_book_hot_update",
        "mos_book_promote_verified",
        "mos_publish_to_shared",
        "mos_compact_context",
        "eacn3_send_message",
        "eacn3_create_task",
        "eacn3_submit_result",
    ),
}


def _tool_warmup_block(role_name: str) -> str:
    """Cold-start ToolSearch warmup nudge.

    Roles run with `ENABLE_TOOL_SEARCH=auto:30`; on cold start no call history
    exists, so high-frequency tools begin deferred. Telling the role to issue
    a single `select:`-form ToolSearch with the canonical hot list eliminates
    the keyword-search miss that previously cost ~6 min thrash + N retries.
    """
    from minions.config import is_expert_role

    key = "expert" if is_expert_role(role_name) else role_name
    names = _TOOL_WARMUP.get(key)
    if not names:
        return ""
    select_query = "select:" + ",".join(names)
    return (
        "Step 0 (warmup, do this BEFORE step 1):\n"
        '  ToolSearch with `query="' + select_query + '"`,\n'
        "  `max_results=" + str(len(names)) + "`. This pre-loads the schemas\n"
        "  for the high-frequency tools you will use this cycle. Do this\n"
        "  exactly once on cold start. If a tool you need is NOT in this list,\n"
        "  use `python3 MANUAL/scripts/lookup.py <keyword>` to find its exact\n"
        '  id, then `ToolSearch(query="select:<id>")`. Never call ToolSearch\n'
        "  with a fuzzy keyword query for MinionsOS tools — keyword search is\n"
        "  for tool *discovery*, not schema loading.\n"
        "\n"
    )


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
    hermetic_cwd: Path | None = None,
    add_dirs: list[Path] | None = None,
    ultracode: bool = False,
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
    if ultracode:
        # ultracode == xhigh reasoning effort + standing dynamic-workflow
        # orchestration. It is a Claude Code *session setting*, NOT an
        # --effort value: `claude --effort ultracode` is rejected by the CLI
        # validator (valid --effort levels are low/medium/high/xhigh/max).
        # The binary documents it as "set per session via the `ultracode`
        # settings key (--settings ...)", and internally
        # `settings.ultracode===true` resolves the effort to "xhigh" while
        # enabling the standing workflow-orchestration posture. We therefore
        # pass it through --settings as a JSON literal. --settings merges
        # additively over the resolved settings stack, so this does not clobber
        # other settings the role inherits. Verified working against
        # claude 2.1.156 via a live --print probe (2026-05-29).
        cmd += ["--settings", '{"ultracode": true}']
    # NOTE: --fallback-model is intentionally NOT applied here. The Claude
    # Code 2.1.152 CLI documents it as "only works with --print", and
    # empirical testing under a real PTY confirms the flag is silently
    # ignored for interactive long-lived sessions (no error, no fallback).
    # The auto-fallback feature is wired into the --print spawn sites
    # instead: see minions/tools/review.py.
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
    if add_dirs:
        # --add-dir grants R/W/E access to extra paths without changing cwd.
        # CLAUDE.md walk goes upward from cwd only, so adding dirs does NOT
        # introduce new walk roots — exactly the property that makes
        # hermetic-cwd safe.
        for extra in add_dirs:
            cmd += ["--add-dir", str(extra)]
    if resume and session_name:
        cmd += ["--resume", session_name]
    effective_cwd = hermetic_cwd if hermetic_cwd is not None else workspace
    if not effective_cwd.exists():
        # Silent fallback to MINIONS_ROOT used to write Workflow / Task /
        # subagent scratchpads into the developer-shared
        # /Users/mjm/MinionsOS/.claude/ directory, corrupting the dev
        # workspace and bypassing the per-role isolation contract
        # (common §10.1). Fail loudly instead so the launcher can surface
        # the missing-branch / missing-hermetic-stub condition before any
        # tmux session is spawned.
        raise RoleError(
            f"build_role_invocation: effective cwd does not exist: {effective_cwd!s}. "
            "If this is a Role process, the role's branch worktree (or hermetic "
            "stub) must be prepared by lifecycle.project / role_hermetic before "
            "launch. Refusing to fall back to MINIONS_ROOT — that fallback "
            "leaks Workflow scratchpad into the dev workspace."
        )
    return RoleInvocation(
        host_name="claude",
        command=cmd,
        cwd=effective_cwd,
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
    event-loop tool (``mos_await_events`` for every role), and set the
    supervisor priority rule. All substantive role behavior — boundaries,
    skills, EACN contract — lives in the appended SYSTEM.md and the
    role-specific ``SYSTEM.md`` re-injected by Claude on each launch.

    Cache optimization: role-specific SYSTEM.md content is injected here (in
    the first user message) rather than in ``--append-system-prompt``, so the
    system prompt prefix stays byte-identical across all roles and maximizes
    cross-role KV cache sharing at the API level.
    """
    return _build_eacn_role_loop_prompt(role_name, port=port, role_system_paths=role_system_paths)


def _build_eacn_role_loop_prompt(
    role_name: str, *, port: int | None = None, role_system_paths: list[Path] | None = None
) -> str:
    """Forever-loop prompt for EACN-registered roles."""
    hot_cache = _hot_cache_block(port)
    hot_cache_section = f"{hot_cache}\n" if hot_cache else ""
    role_contract = _role_contract_block(role_system_paths)
    warmup = _tool_warmup_block(role_name)
    return (
        f"You are the MinionsOS `{role_name}` role. Your event loop runs forever.\n"
        "\n"
        f"{hot_cache_section}"
        "Cold start (this is your first cycle on a fresh process):\n"
        f"{warmup}"
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
        "4. Draft discipline (REQUIRED before next `mos_await_events()`):\n"
        "   if you handled at least one real (non-`cache_keepalive`) event\n"
        "   in this cycle, you MUST call `mos_draft_append` at least once\n"
        "   summarizing what you decided or produced. Even a one-line\n"
        "   `result` node with `evidence_tag` pointing to a published\n"
        "   artifact is sufficient. The Draft is the durable cold-start\n"
        "   trail other roles read; published files (`mos_publish_*`,\n"
        "   `eacn3_send_message`) are NOT a substitute. Skip this step\n"
        "   ONLY when the cycle's only delivery was a `cache_keepalive`.\n"
        "   `mos_await_events` audits this and will surface a reminder if\n"
        "   you skipped a Draft write after a real-event cycle.\n"
        "5. Decide next step:\n"
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
        "Quiet turns — drain-silently vs. initiate (PAIRED, do not split):\n"
        "- No-decision event (ack of your ack, courtesy close, an already-\n"
        "  resolved item): acknowledge by DRAINING ONLY — no eacn3 reply, no\n"
        "  Draft node — and return to mos_await_events(). Do not burn a full\n"
        "  reasoning turn arriving at 'I'll let it rest'.\n"
        "- idle_check, or you are waiting on a peer, or the project has gone\n"
        "  quiet with your responsibility unmet: INITIATE, do not wait.\n"
        "  Passively re-polling is how the team deadlocks (everyone yields,\n"
        "  nobody moves). The deadlock-breaker is TASK OWNERSHIP, not chat:\n"
        "  a DM carries no claim obligation, so DM threads let peers defer\n"
        "  to each other forever; a task carries a claim/bid/result\n"
        "  obligation, so once a peer claims it SOMEONE OWNS the next move.\n"
        "  For a cross-role dependency, prefer eacn3_create_task with\n"
        "  invited_agent_ids=[<peer role name>] (a peer's agent_id IS just\n"
        "  its role name: coder / ethics / expert-<slug> — you do not need\n"
        "  anyone to hand you an id). Use eacn3_send_message only for a short\n"
        "  unblock nudge or status. And on the executor side: bid / claim /\n"
        "  submit-result on fitting open tasks and retrieve results promptly\n"
        "  rather than waiting to be invited. eacn3_send_message and\n"
        "  eacn3_create_task are first-class tools, on the same footing as\n"
        "  mos_await_events — reaching for them on an idle/blocked turn is\n"
        "  the intended behaviour, not an exception.\n"
        "  (This is NOT the cache_keepalive turn below, which is ack-only.)\n"
        "\n"
        "Cache keepalive: if `mos_await_events()` returns a single event of\n"
        "type `cache_keepalive`, that is a wall-clock cliff guard for the\n"
        "prompt cache, NOT a real event. Reply with exactly the literal\n"
        "string `ack` and immediately call `mos_await_events()` again. Do\n"
        "not write to the Draft, do not send EACN messages, do not\n"
        "invoke any other tool, do not vary the ack text — keeping the\n"
        "reply byte-stable is what makes this turn cacheable.\n"
        "\n"
        "Wedge guard: the `ack` reply is ONLY valid when\n"
        "the prior tool result was a `cache_keepalive` event. If you ever\n"
        "notice (a) two consecutive turns where you produced empty content\n"
        "or a bare `ack` despite the prior tool result NOT being a\n"
        "`cache_keepalive`, or (b) the pane shows `[upstream returned no\n"
        "content]` repeating, you are wedged in an empty-upstream loop —\n"
        "DO NOT keep acking. Immediately call\n"
        '`mos_reset_context(reason="upstream-empty-loop")` to terminate\n'
        "this process so the watchdog cold-starts you from Draft. The\n"
        "Gru-side wedge watchdog will eventually kill the session for you,\n"
        "but self-reset is cheaper and faster.\n"
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
