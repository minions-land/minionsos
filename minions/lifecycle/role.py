"""Role lifecycle: register, dismiss, list.

MinionsOS Roles are long-lived agent-host processes that call
``mos_await_events`` on their own queue. This module owns the registration
surface used at project bootstrap and by the ``mos`` CLI:

- ``register_role`` / ``register_expert`` register a project-local EACN3
  AgentCard, prepare the Role's workspace, and record a named host session in
  ``projects.json``. They do NOT start an agent-host subprocess. The MCP
  layer imports them as ``mos_spawn_role`` / ``mos_spawn_expert``.
- ``dismiss_role`` marks a role dismissed and unregisters it from the
  project's EACN3 network.
- ``list_roles`` returns the current registry.

Resident-Role process startup is owned by the resident-Role launcher and
not by this module.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from minions.config import (
    ROLE_CLASSIFICATION,
    ROLE_WRITE_BOUNDARIES,
    RoleType,
    parse_duration,
    slugify,
)
from minions.errors import BackendError, RoleError
from minions.lifecycle import eacn_client
from minions.lifecycle.agent_registry import register_project_role_agent
from minions.lifecycle.eacn_identity import resolve_agent_id
from minions.lifecycle.project import ensure_role_workspace
from minions.paths import project_session_name
from minions.state.store import RoleEntry, StateStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXED_ROLES = {"ethics"}

# Fixed roles bootstrapped automatically at project creation. The project's
# general worker (one generalist Expert) is bootstrapped separately via
# register_expert (it needs a domain), so it is NOT in this set.
BOOTSTRAP_ROLES = {"ethics"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _resolve_time_trigger_interval(role_name: str, interval: str | None) -> str | None:
    """Resolve optional periodic wakeups for a role.

    All roles are event-driven (``mos_await_events``); none gets a default
    timer cadence. Ethics — the merged memory curator + auditor — does its
    periodic Draft-flush / Book-maintenance work on the ``idle_check`` ticks
    that ``mos_await_events`` already emits after ~5 minutes of silence, so it
    needs no separate timer. A cadence is only set when a caller explicitly
    passes one; it is recorded on the ``RoleEntry`` for the launcher.
    """
    del role_name  # no role gets a default timer cadence anymore
    if not interval:
        return None
    try:
        seconds = parse_duration(interval)
    except Exception as exc:
        raise RoleError(f"Invalid time_trigger_interval {interval!r}: {exc}") from exc
    if seconds <= 0:
        return None
    return interval


# ---------------------------------------------------------------------------
# Role boundary text (consumed by the resident-Role launcher when seeding
# a new Role process). Boundary semantics live here so roles, MCP profiles,
# and tests share one source of truth.
# ---------------------------------------------------------------------------


_BOUNDARY_TEXT: dict[str, str] = {
    "gru": (
        "[Role boundary: human-side agent]\n"
        "You receive and interpret human instructions, recommend workflow options, "
        "drive project progress, dispatch tasks through EACN3, and inspect health/status. "
        "You do NOT implement code, run experiments, write final paper text, or "
        "participate in Review.\n"
        "Write boundaries: your branch `branches/main/` (this is Gru's own branch) "
        "and project-level files (`CLAUDE.md`, `meta.json`). Do NOT edit other "
        "roles' branches directly; ask the owning role through EACN instead. "
        "Cross-role artefacts go to `branches/shared/<subdir>/` via "
        "`mos_publish_to_shared` — Gru may publish into any subdir.\n"
        "Cross-cycle memory: use the Draft (`mos_draft_append` / "
        "`mos_draft_summary` / `mos_draft_query`) — Noter flushes "
        "it to the shared branch on its periodic wake.\n"
    ),
    "ethics": (
        "[Role boundary: EACN-visible agent — memory curator + evidence auditor + adjudicator]\n"
        "You are the merged Ethics role: you (1) curate the team memory — maintain "
        "the Draft graph (flush/decay/dedup, draw motif edges), ingest/promote/"
        "crystallize the Book; (2) audit whether agent behaviour, theory, code, and "
        "claims have real evidence support; (3) adjudicate EACN tasks. You MAY "
        "inspect internal materials: experiment artifacts, evidence/claim maps, "
        "agent communications, and all claim types; and you read any role's Reel.\n"
        "RED LINE: you NEVER produce a substantive research claim — claims come only "
        "from Expert. You organize, audit, seal, and adjudicate. Edges you draw "
        "yourself are held to the SAME evidence standard you apply to Expert claims.\n"
        "Triage: handle audit/adjudication events first (they gate the whole team); "
        "do memory hygiene (Draft flush, Book maintenance) on idle ticks.\n"
        "Write boundaries: your branch `branches/ethics/` for working drafts and "
        "investigation notes. Publish reports/flags/adjudications/mock-reviews to "
        "`branches/shared/ethics/`; curate the Book under `branches/shared/book/`; "
        "flush the Draft at `branches/shared/draft/draft.json`. Do NOT publish into "
        "`branches/shared/reviews/` — reserved for `mos_review_run`.\n"
        "Cross-cycle memory: the Draft (`mos_draft_*`) is your primary instrument.\n"
    ),
    "expert": (
        "[Role boundary: EACN-visible agent — the project's general worker]\n"
        "You are the unified worker (the 'Common Agent'): you drive science AND "
        "carry it out — write/run experiments, debug, write the paper, build "
        "figures, search literature. Coding, writing, and figure-making are "
        "baseline capabilities (their skills live in `common/skills/`).\n"
        "Communicate state and task handoffs through EACN3; delegate heavy "
        "execution to Workflow/subagents and write back size-bounded results.\n"
        "Write boundaries: your branch `branches/<expert>/` "
        "(`src/experiments/`, `exp/exp-<id>/`, `paper/`, `notes/`). Publish "
        "cross-role handoffs to `branches/shared/handoffs/` via "
        "`mos_publish_to_shared`; experiment bundles to "
        "`branches/shared/exp/exp-<id>/`.\n"
        "Conditional system-maintenance boundary: MinionsOS runtime code only "
        "when Gru or the author explicitly assigns it through EACN with named "
        "scope, paths, and verification target.\n"
        "Cross-cycle memory: use the Draft (`mos_draft_append` / "
        "`mos_draft_summary` / `mos_draft_query`).\n"
    ),
}


def _boundary_context(role_name: str, project_port: int) -> str:
    """Return boundary enforcement text for injection into the role prompt.

    The *project_port* argument is reserved for future per-project boundary
    customization; today the text is identical for every project.
    """
    del project_port  # currently unused; kept for API stability
    from minions.config import normalise_role_name

    normalised = normalise_role_name(role_name)
    if normalised in _BOUNDARY_TEXT:
        return _BOUNDARY_TEXT[normalised]
    role_type = ROLE_CLASSIFICATION.get(normalised, RoleType.eacn_visible)
    label = "human-side" if role_type == RoleType.human_side else "EACN-visible"
    dirs = ROLE_WRITE_BOUNDARIES.get(normalised, ["branches/<role>/"])
    return f"[Role boundary: {label} agent]\nWrite boundaries: {', '.join(dirs)}.\n"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_role(
    project_port: int,
    role: str,
    init_brief: str | None = None,
    store: StateStore | None = None,
    time_trigger_interval: str | None = None,
) -> dict[str, object]:
    """Register a fixed role for event-driven invocation.

    Does NOT launch an agent-host subprocess. Registration prepares the EACN
    identity, canonical workspace, and stable host session name; the
    resident-Role launcher consumes the resulting registry entry to start
    the actual long-lived Role process.

    If *init_brief* is given it is delivered as an addressable EACN message
    (advisory, not a Task) so the cold-started Role wakes with role-specific
    guidance but no bid/claim contract to satisfy. Noter is on a timer
    backbone so its brief is logged-and-dropped.
    """
    if role not in FIXED_ROLES:
        raise RoleError(
            f"register_role only handles fixed roles {FIXED_ROLES}; "
            "use register_expert for experts."
        )
    return _do_register(
        project_port=project_port,
        role_name=role,
        init_brief=init_brief,
        store=store or StateStore(),
        time_trigger_interval=time_trigger_interval,
    )


def register_expert(
    project_port: int,
    domain: str,
    name: str | None = None,
    init_brief: str | None = None,
    store: StateStore | None = None,
    time_trigger_interval: str | None = None,
    workflow_plugin: str | None = None,
) -> dict[str, object]:
    """Register an expert role for event-driven invocation.

    The registered role name is always shaped as an Expert authz key —
    ``expert-<slug>`` — so :func:`minions.config.is_expert_role` collapses
    it to the ``expert`` server-side authz bucket. Caller-supplied *name*
    that already carries the ``expert-`` prefix or ``-expert`` suffix is
    accepted verbatim; bare slugs (e.g. ``"coda-epilogue"``) are coerced
    to ``expert-<slug>`` instead of being trusted. Without this guard a
    Gru that calls ``mos_spawn_expert(name="coda-epilogue")`` registers
    a bare-slug AgentCard whose authz lookup falls through to the empty
    list, and every MCP tool the spawned Role calls is server-side
    denied — including ``mos_issue_report``, leaving the operator blind.
    See coda-epilogue/p37596 incident 2026-05-26.
    """
    from minions.config import is_expert_role

    slug = slugify(domain)
    if name is None:
        role_name = f"expert-{slug}"
    elif is_expert_role(name):
        role_name = name
    else:
        coerced_slug = slugify(name) or slug
        role_name = f"expert-{coerced_slug}"
        logger.warning(
            "register_expert: caller name=%r lacks expert- prefix/suffix; "
            "coerced to %r so server authz collapses to bucket 'expert'.",
            name,
            role_name,
        )
    brief = init_brief or (
        "Survey the current state of your specialty in the context of this project's topic."
    )
    return _do_register(
        project_port=project_port,
        role_name=role_name,
        init_brief=brief,
        store=store or StateStore(),
        time_trigger_interval=time_trigger_interval,
        workflow_plugin_slug=workflow_plugin,
    )


def _do_register(
    project_port: int,
    role_name: str,
    init_brief: str | None,
    store: StateStore,
    time_trigger_interval: str | None,
    workflow_plugin_slug: str | None = None,
) -> dict[str, object]:
    entry = store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    existing = next((r for r in entry.active_roles if r.name == role_name), None)
    if existing and existing.state == "active":
        # Smart re-spawn: if the tmux session is alive, do nothing; if it
        # has died, relaunch in place. Either way, we do not run the full
        # registration path again — EACN AgentCard / workspace are already
        # set up.
        try:
            from minions.lifecycle.role_launcher import (
                attach_command,
                launch_role_process,
                session_alive,
            )
            from minions.lifecycle.role_launcher import (
                session_name as _session_name,
            )

            if session_alive(project_port, role_name):
                return {
                    "name": role_name,
                    "session_name": existing.session_name,
                    "workspace_path": existing.workspace_path,
                    "workspace_branch": existing.workspace_branch,
                    "time_trigger_interval": existing.time_trigger_interval,
                    "eacn_agent_id": existing.eacn_agent_id,
                    "tmux_session": _session_name(project_port, role_name),
                    "attach_cmd": attach_command(project_port, role_name),
                    "launch_started": False,
                    "respawn": False,
                }
            launch_status = launch_role_process(existing, project_port)
            return {
                "name": role_name,
                "session_name": existing.session_name,
                "workspace_path": existing.workspace_path,
                "workspace_branch": existing.workspace_branch,
                "time_trigger_interval": existing.time_trigger_interval,
                "eacn_agent_id": existing.eacn_agent_id,
                "tmux_session": launch_status.get("session_name"),
                "attach_cmd": launch_status.get("attach_cmd"),
                "launch_started": launch_status.get("started"),
                "respawn": True,
            }
        except RoleError:
            raise
        except Exception as exc:
            raise RoleError(
                f"Role {role_name!r} marked active but smart-respawn failed: {exc}"
            ) from exc

    resolved_time_trigger = _resolve_time_trigger_interval(role_name, time_trigger_interval)

    try:
        workspace_branch, workspace_path = ensure_role_workspace(
            project_port,
            role_name,
            base_branch=entry.current_branch or None,
        )
    except Exception as exc:
        raise RoleError(
            f"Role {role_name!r} could not prepare its workspace on port {project_port}: {exc}"
        ) from exc
    session_name = project_session_name(project_port, role_name)

    # Every role registers on the project-local EACN3 network and drives its
    # loop via mos_await_events (Ethics, the merged memory-curator + auditor,
    # included — it does periodic memory maintenance on idle ticks).
    try:
        agent_token, _seeds = register_project_role_agent(project_port, role_name)
    except BackendError as exc:
        raise RoleError(
            f"Role {role_name!r} could not join project-local EACN3 network "
            f"on port {project_port}: {exc}"
        ) from exc

    now = _now_iso()
    role_entry = RoleEntry(
        name=role_name,
        state="active",
        pid=None,
        spawned_at=now,
        session_name=session_name,
        session_resumable=False,
        workspace_path=str(workspace_path.resolve()),
        workspace_branch=workspace_branch,
        github_push_target=getattr(entry, "github_push_target", None),
        time_trigger_interval=resolved_time_trigger,
        workflow_plugin_slug=workflow_plugin_slug,
        eacn_agent_id=resolve_agent_id(project_port, role_name),
        eacn_agent_token=agent_token,
        eacn_registered_at=now,
    )

    if init_brief:
        # Cold-start delivery is an advisory message, NOT a Task.
        # A Task would carry a bid/claim contract and require the
        # cold-started Role to issue eacn3_submit_bid before doing
        # anything productive — a contract that often deadlocks a
        # freshly woken Role with no peers yet to negotiate against.
        # The B-000 bootstrap node already provides project-level
        # context; this message just hands the Role its role-specific
        # brief as a normal addressable event that mos_await_events
        # surfaces without a bid obligation.
        target_agent_id = resolve_agent_id(project_port, role_name)
        initiator_id = resolve_agent_id(project_port, "gru")
        try:
            eacn_client.send_message(
                port=project_port,
                to_agent_id=target_agent_id,
                from_agent_id=initiator_id,
                content={
                    "kind": "role_init_brief",
                    "role": role_name,
                    "brief": init_brief,
                    "guidance": (
                        "This is an advisory init brief, not a Task. "
                        "Read B-000 in the Draft for project context, then "
                        "actively collaborate with your peers. "
                        "Use eacn3_send_message to exchange ideas with other roles, "
                        "or eacn3_create_task to propose collaborative work. "
                        "Wisdom emerges from discussion — you are an autonomous team, "
                        "not passive workers waiting for assignments."
                    ),
                },
            )
        except BackendError as exc:
            raise RoleError(
                f"Role {role_name!r} joined project-local EACN3 on port {project_port}, "
                f"but the init_brief message could not be sent through EACN3: {exc}"
            ) from exc
        logger.info(
            "init_brief message sent via EACN: role=%r port=%d",
            role_name,
            project_port,
        )

    store.upsert_role(project_port, role_entry)
    logger.info("register_role: role=%r port=%d", role_name, project_port)

    # Launch the long-lived Role process in tmux. If the launcher fails we
    # leave the role registered so the operator can inspect / retry; the
    # error is surfaced via RoleError with the original exception chained.
    launch_status: dict[str, object] = {}
    try:
        from minions.lifecycle.role_launcher import launch_role_process

        launch_status = launch_role_process(role_entry, project_port)
    except RoleError:
        raise
    except Exception as exc:
        raise RoleError(
            f"Role {role_name!r} registered on port {project_port} but the "
            f"resident-Role launcher failed: {exc}"
        ) from exc

    return {
        "name": role_name,
        "session_name": session_name,
        "workspace_path": str(workspace_path.resolve()),
        "workspace_branch": workspace_branch,
        "time_trigger_interval": resolved_time_trigger,
        "eacn_agent_id": role_entry.eacn_agent_id,
        "tmux_session": launch_status.get("session_name"),
        "attach_cmd": launch_status.get("attach_cmd"),
        "launch_started": launch_status.get("started"),
    }


# ---------------------------------------------------------------------------
# Dismiss / list
# ---------------------------------------------------------------------------


def dismiss_role(
    project_port: int,
    role_name: str,
    store: StateStore | None = None,
    *,
    reason: str | None = None,
    caller: str | None = None,
) -> dict[str, str]:
    """Mark a role dismissed in the registry and unregister it from EACN3.

    The optional ``reason`` and ``caller`` arguments feed the audit-trail
    log line so operators can later trace who terminated what and why
    (e.g. caller="gru" when invoked by the watchdog/role-evolution path,
    caller="operator" when invoked from the CLI).
    """
    _store = store or StateStore()
    entry = _store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    role = next((r for r in entry.active_roles if r.name == role_name), None)
    if role is None:
        raise RoleError(f"Role {role_name!r} not found on port {project_port}.")

    logger.info(
        "role dismissed: role=%s port=%d reason=%s caller=%s",
        role_name,
        project_port,
        reason or "unspecified",
        caller or "unspecified",
    )

    # Every role is registered on EACN3 — unregister on dismiss.
    try:
        eacn_client.unregister_agent(project_port, role.eacn_agent_id or role_name)
    except Exception as exc:
        logger.warning(
            "dismiss_role: EACN unregister failed for role=%r port=%d: %s",
            role_name,
            project_port,
            exc,
        )

    try:
        from minions.lifecycle.role_launcher import kill_session

        killed = kill_session(project_port, role_name)
    except Exception as exc:
        logger.warning(
            "dismiss_role: tmux kill failed for role=%r port=%d: %s",
            role_name,
            project_port,
            exc,
        )
        killed = False

    _store.upsert_role(project_port, role.model_copy(update={"state": "dismissed", "pid": None}))
    logger.info(
        "dismiss_role done: role=%r port=%d tmux_killed=%s",
        role_name,
        project_port,
        killed,
    )
    return {"name": role_name, "tmux_killed": "1" if killed else "0"}


def list_roles(
    project_port: int,
    store: StateStore | None = None,
) -> list[dict[str, object]]:
    """List roles for a project, reconciling state with tmux reality.

    Issue #52: projects.json can drift from reality after backend crashes.
    This function cross-checks tmux session liveness and decorates the
    returned state accordingly.
    """
    from minions.lifecycle.role_launcher import session_alive

    _store = store or StateStore()
    entry = _store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    result = []
    for r in entry.active_roles:
        tmux_alive = session_alive(project_port, r.name)
        # Reconcile state with tmux reality
        if r.state == "active" and not tmux_alive:
            actual_state = "dead"
        elif r.state == "dismissed" and tmux_alive:
            actual_state = "dismissed"  # keep dismissed, but flag orphan
        else:
            actual_state = r.state

        result.append(
            {
                "name": r.name,
                "state": actual_state,
                "pid": r.pid,
                "eacn_agent_id": r.eacn_agent_id or r.name,
                "session_name": getattr(r, "session_name", None),
                "session_resumable": getattr(r, "session_resumable", False),
                "workspace_path": getattr(r, "workspace_path", None),
                "workspace_branch": getattr(r, "workspace_branch", None),
                "tmux_alive": tmux_alive,
                "tmux_orphan": r.state == "dismissed" and tmux_alive,
            }
        )
    return result
