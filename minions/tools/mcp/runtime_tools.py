"""Runtime/event/process tools.

Covers everything not in a clean domain bucket:
- mos_start_monitor (Gru heartbeat thread)
- mos_await_events (Role main-loop blocking)
- mos_get_events / mos_unread_summary (Gru pull-mode events)
- mos_attach_role / mos_kill_role (tmux helpers)
- mos_reset_context / mos_compact_context (LLM context management)
- mos_issue_report (scaffolding bug reports)
"""

from __future__ import annotations

import logging
import threading

from pydantic import BaseModel, Field

from minions.tools import await_events as _await_events
from minions.tools import compact as _compact
from minions.tools import issues as _issues
from minions.tools import reset as _reset
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed, running_sidecar_monitor

logger = logging.getLogger(__name__)

_GRU_START_MONITOR_THREAD: threading.Thread | None = None
_GRU_START_MONITOR_INTERVAL: int | None = None


@mcp.tool()
def mos_start_monitor(heartbeat_interval: int | None = None) -> dict:
    """Start the Gru heartbeat/health monitor as a background daemon thread.

    Idempotent: a second call while the monitor is still alive is a no-op.
    """
    _require_tool_allowed("mos_start_monitor")
    from minions.gru.loop import GruLoop

    global _GRU_START_MONITOR_THREAD, _GRU_START_MONITOR_INTERVAL

    existing = _GRU_START_MONITOR_THREAD
    if existing is not None and existing.is_alive():
        return {
            "started": False,
            "already_running": True,
            "interval": _GRU_START_MONITOR_INTERVAL,
        }

    sidecar = running_sidecar_monitor()
    if sidecar is not None:
        return {
            "started": False,
            "already_running": True,
            "external": True,
            "interval": None,
            **sidecar,
        }

    loop = GruLoop(heartbeat_interval=heartbeat_interval)
    t = threading.Thread(target=loop.run, daemon=True, name="gru-monitor")
    t.start()
    _GRU_START_MONITOR_THREAD = t
    _GRU_START_MONITOR_INTERVAL = loop.interval
    logger.info("Gru monitor thread started (interval=%ds).", loop.interval)
    return {"started": True, "already_running": False, "interval": loop.interval}


# ── mos_await_events ────────────────────────────────────────────────────


@mcp.tool()
def mos_await_events() -> dict:
    """Block until EACN3 delivers events, then return them annotated.

    Internally loops 60s HTTP long-polls. Writes a heartbeat file to the
    workspace on every cycle (git-visible liveness signal for external observers).
    Only returns when events actually arrive — the LLM never sees empty results.

    Returns {count, events: [{event, suggested_action, suggested_tool,
    suggested_params, urgency}]} where count > 0 always.

    Identity read from env: MINIONS_PROJECT_PORT, MINIONS_AGENT_ID, MINIONS_WORKSPACE.
    """
    _require_tool_allowed("mos_await_events")
    return _await_events.await_events()


# ── mos_issue_report ───────────────────────────────────────────────────


@mcp.tool()
def mos_issue_report(args: _issues.IssueReportArgs) -> dict:
    """File a runtime issue against MinionsOS scaffolding — fire-and-forget.

    Drop a structured bug report when you notice something wrong with the
    system itself: a tool that keeps failing, a SYSTEM.md instruction that
    contradicts observed behavior, a referenced skill that does not exist,
    a tool-surface gap, an environment misconfiguration, anything that
    feels like the floor rather than the work.

    Not for science questions, peer disagreement, or task-level blockers
    — those go through EACN. This tool is strictly for "the scaffolding
    is broken / unclear / missing".

    Behavior:

    1. Identity (role, project_port, phase) is read from the calling
       process environment — you cannot file under another role's name.
    2. The record is appended atomically to
       ``project_{port}/issues/issues.jsonl`` under a per-project flock.
    3. No coordination, no EACN traffic, no review. Filing succeeds or
       raises; nobody else is notified.

    The record uses the standard bug-report shape (title, severity P0-P3,
    component, steps_to_reproduce, expected, actual, evidence, impact,
    workaround) so a downstream triage agent can ingest the file
    directly. On project close / dormant the lifecycle copies the file
    to ``~/.minionsos/issues/{port}-{ts}.jsonl``.

    Returns the persisted record (including its ``ISS-<port>-<n>`` id).
    """
    _require_tool_allowed("mos_issue_report")
    return _issues.report_issue(args)


# ── mos_reset_context ──────────────────────────────────────────────────────────


class MosResetArgs(BaseModel):
    reason: str = Field(
        default="",
        description="Why the reset is happening (e.g. task direction change).",
    )


@mcp.tool()
def mos_reset_context(args: MosResetArgs) -> dict:
    """Clear conversation context and continue with fresh state.

    Call AFTER persisting all discoveries to the Draft. After reset,
    call mos_draft_summary() to re-orient, then mos_await_events().
    """
    _require_tool_allowed("mos_reset_context")
    return _reset.mos_reset_context(reason=args.reason)


# ── mos_compact_context ───────────────────────────────────────────────────────


class MosCompactArgs(BaseModel):
    reason: str = Field(
        default="",
        description="Why compact is happening (e.g. context too large, switching direction).",
    )
    pending_plans: list[dict] = Field(
        default_factory=list,
        description=(
            "Events or planned steps to persist as pending_plan Draft nodes. "
            "Each dict needs at minimum 'type' and 'text' fields."
        ),
    )


@mcp.tool()
def mos_compact_context(args: MosCompactArgs) -> dict:
    """Compress conversation context without killing the process.

    Persists pending plans to the Draft, then schedules /compact. Unlike
    mos_reset_context, this preserves the prompt cache (no cold start).
    After calling this, STOP immediately — produce no more tool calls or
    text. The /compact fires as the next input after your turn ends.
    Then call mos_await_events() to resume.
    """
    _require_tool_allowed("mos_compact_context")
    return _compact.mos_compact_context(
        reason=args.reason,
        pending_plans=args.pending_plans or None,
    )


# ── Resident-Role tmux helpers ─────────────────────────────────────────


class RoleSessionArgs(BaseModel):
    project_port: int = Field(description="Project port.")
    role_name: str = Field(description="Role name.")


class KillRoleArgs(BaseModel):
    project_port: int = Field(description="Project port.")
    role_name: str = Field(description="Role name.")
    purge: bool = Field(
        default=False,
        description=(
            "When False (default), recycle: kill tmux but keep state=active "
            "so the Gru watchdog respawns the role on the next tick. When "
            "True, retire: kill tmux AND flip the registry row to "
            "state=dismissed so the watchdog skips it. Use purge=True when "
            "you actually want the role gone (e.g. after the role filed an "
            "issue and you've handled it manually)."
        ),
    )


@mcp.tool()
def mos_attach_role(args: RoleSessionArgs) -> dict:
    """Return the tmux command to attach to a Role's resident session.

    The launcher itself does not attach. The caller (operator) runs the
    returned command in their own terminal. Read-only — does not change
    the session or the registry.
    """
    _require_tool_allowed("mos_attach_role")
    from minions.lifecycle.role_launcher import (
        attach_command,
        session_alive,
    )
    from minions.lifecycle.role_launcher import (
        session_name as _session_name,
    )

    name = _session_name(args.project_port, args.role_name)
    alive = session_alive(args.project_port, args.role_name)
    return {
        "session_name": name,
        "alive": alive,
        "attach_cmd": attach_command(args.project_port, args.role_name),
    }


@mcp.tool()
def mos_kill_role(args: KillRoleArgs) -> dict:
    """Kill the tmux session for a Role.

    Two semantics, controlled by ``purge``:

    - ``purge=False`` (default, **recycle**): kill tmux only. The registry
      row stays at ``state=active``; the Gru watchdog will see the missing
      session and respawn the role on its next loop tick. Use this when a
      role process is wedged and you want a clean restart.

    - ``purge=True`` (**retire**): kill tmux AND flip the registry row to
      ``state=dismissed`` (and clear ``pid`` / ``session_resumable``). The
      watchdog skips dismissed rows, so the role stays gone until the
      operator explicitly respawns it. Use this when you want the role
      gone — for example, after the role filed a P0/P1 issue and you've
      handled it by hand.

    Returning ``mos_list_roles`` afterwards reflects whichever state the
    operator chose, so observers don't have to special-case
    "active+pid=null+session_resumable=false" as a third-state. See
    GitHub Issue #3 for the failure mode the purge mode fixes.

    To permanently retire a role with full registry cleanup (EACN
    unregister, workspace marker, etc.), prefer ``mos_dismiss_role``.
    """
    _require_tool_allowed("mos_kill_role")
    from minions.lifecycle.role_launcher import kill_session
    from minions.state.store import StateStore

    killed = kill_session(args.project_port, args.role_name)

    purged = False
    new_state: str | None = None
    if args.purge:
        # Retire mode: flip the registry row so the watchdog stops
        # respawning. Best-effort — failures don't unkill tmux.
        try:
            store = StateStore()
            project = store.get_project(args.project_port)
            if project is not None:
                target = next(
                    (r for r in project.active_roles if r.name == args.role_name),
                    None,
                )
                if target is not None and target.state == "active":
                    store.upsert_role(
                        args.project_port,
                        target.model_copy(
                            update={
                                "state": "dismissed",
                                "pid": None,
                                "session_resumable": False,
                            }
                        ),
                    )
                    purged = True
                    new_state = "dismissed"
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "mos_kill_role(purge=True): registry update failed for port=%d role=%s: %s",
                args.project_port,
                args.role_name,
                exc,
            )
    return {
        "project_port": args.project_port,
        "role_name": args.role_name,
        "killed": killed,
        "purged": purged,
        "state": new_state,
    }


# ── Gru pull-mode event tools ──────────────────────────────────────────


class MosGetEventsArgs(BaseModel):
    port: int = Field(description="Project port whose Gru queue to drain.")


@mcp.tool()
def mos_get_events(args: MosGetEventsArgs) -> dict:
    """Drain this project's Gru EACN queue once (non-blocking) and mirror to disk.

    Pull-mode counterpart to ``mos_await_events``. Used by Gru to pick up
    Role-to-Gru messages on demand. Each call appends new events to
    ``project_{port}/events/gru.jsonl`` and advances ``gru.last_seen``,
    so the next ``mos_unread_summary`` reflects that this project is
    caught up.
    """
    _require_tool_allowed("mos_get_events")
    from minions.tools import get_events as _get_events

    return _get_events.get_events(args.port)


@mcp.tool()
def mos_unread_summary() -> dict:
    """Return per-project Gru unread counts across all active projects.

    Pure read — does not drain or modify any queue. Returns
    ``{ports: [{port, name, unread}], total_unread}`` so Gru can decide
    which project to inspect next.
    """
    _require_tool_allowed("mos_unread_summary")
    from minions.tools import get_events as _get_events

    return _get_events.unread_summary()
