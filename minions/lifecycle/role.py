"""Role lifecycle: register, dismiss, list.

MinionsOS Roles are long-lived agent-host processes that call
``mos_await_events`` on their own queue. This module owns the registration
surface used at project bootstrap and by the ``mos`` CLI:

- ``register_role`` / ``register_expert`` register a project-local EACN3
  AgentCard, prepare the Role's workspace, and record a named host session in
  ``projects.json``. They do NOT start an agent-host subprocess.
- ``dismiss_role`` marks a role dismissed and unregisters it from the
  project's EACN3 network.
- ``list_roles`` returns the current registry.

The public ``spawn_role`` / ``spawn_expert`` names are the MCP-facing aliases
for ``register_role`` / ``register_expert``. Resident-Role process startup is
owned by the resident-Role launcher and not by this module.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from minions.config import (
    ROLE_CLASSIFICATION,
    ROLE_WRITE_BOUNDARIES,
    RoleType,
    load_gru_config,
    parse_duration,
    slugify,
)
from minions.errors import BackendError, RoleError
from minions.lifecycle import eacn_client
from minions.lifecycle.agent_registry import register_project_role_agent, role_agent_domains
from minions.lifecycle.eacn_identity import resolve_agent_id
from minions.lifecycle.project import ensure_role_workspace
from minions.paths import project_session_name
from minions.state.store import RoleEntry, StateStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXED_ROLES = {"noter", "coder", "writer", "ethics"}

# Roles bootstrapped automatically at project creation. Writer is on-demand
# (spawned by Gru when the project enters a paper-writing phase).
BOOTSTRAP_ROLES = {"noter", "coder", "ethics"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _resolve_time_trigger_interval(role_name: str, interval: str | None) -> str | None:
    """Resolve optional periodic wakeups for a role.

    Noter gets a default cadence because periodic Draft flushes are part
    of its core contract. Report publication is throttled separately by
    ``noter_report_interval``. Other roles remain event-driven unless
    explicitly configured. The cadence is recorded on the ``RoleEntry`` for
    the resident-Role launcher to consume; this module does not schedule
    wakeups.
    """
    if interval is None and role_name == "noter":
        try:
            interval = load_gru_config().noter_periodic_interval
        except Exception:
            interval = "5m"
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
    "noter": (
        "[Role boundary: observer — Draft curator, NOT on EACN3]\n"
        "You wake on a periodic timer (`mos_noter_wait`, default 5m) "
        "to (a) flush the buffered Draft via "
        "`mos_draft_commit_shared` and (b) consider whether a fresh "
        "staged report is due (target cadence `noter_report_interval`, "
        "default 30m). You observe the project by reading `events/*.jsonl` "
        "and `branches/shared/` — you do NOT have EACN3 tools and are not "
        "registered on the network.\n"
        "Write boundaries: your drafts go in your branch `branches/noter/`; "
        "publish to `branches/shared/notes/<file>.md` via "
        "`mos_publish_to_shared`. The Draft itself lives at "
        "`branches/shared/draft/draft.json` and is flushed by "
        "you.\n"
        "Do NOT write to any other role's `branches/<role>/` directory. Do "
        "NOT publish into any shared subdir other than `notes/`, "
        "`draft/`, `book/`, or `handoffs/`.\n"
    ),
    "coder": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Delegate complex execution to subagents; summarize and write back results.\n"
        "Write boundaries: your branch `branches/coder/` by default. Publish "
        "cross-role handoffs to `branches/shared/handoffs/` via "
        "`mos_publish_to_shared`. Publish completed experiment result bundles to "
        "`branches/shared/exp/exp-<id>/` via `mos_publish_to_shared`. "
        "Conditional system-maintenance boundary: "
        "MinionsOS repository runtime code only when Gru or the author "
        "explicitly assigns that implementation work through EACN and names the "
        "scope, allowed paths, and verification target.\n"
        "Cross-cycle memory: use the Draft (`mos_draft_append` / "
        "`mos_draft_summary` / `mos_draft_query`).\n"
    ),
    "writer": (
        "[Role boundary: EACN-visible agent]\n"
        "Do NOT invent claims. Output must be based on available evidence, expert feedback, "
        "experiment results, and competitor positioning. "
        "Claims must be supported by evidence, experiment, derivation, citation, "
        "or explicit speculation markers.\n"
        "Write boundaries: your branch `branches/writer/` (primary: "
        "`branches/writer/paper/`). Publish cross-role handoffs (e.g. a "
        "submission package for review) to `branches/shared/handoffs/` via "
        "`mos_publish_to_shared`.\n"
        "Cross-cycle memory: use the Draft (`mos_draft_append` / "
        "`mos_draft_summary` / `mos_draft_query`).\n"
    ),
    "ethics": (
        "[Role boundary: EACN-visible agent — continuous evidence validation]\n"
        "You continuously check whether agent behavior, communication, theory, code, "
        "and claims have real evidence support. You MAY inspect internal materials: "
        "experiment artifacts, evidence/claim maps, appendix plans, known limitations, "
        "unresolved risks, agent communications, and all claim types.\n"
        "Write boundaries: your branch `branches/ethics/` for working drafts "
        "and investigation notes. Publish finalised reports, flags, "
        "adjudications, and mock-reviews to `branches/shared/ethics/` (flat: "
        "`report-<slug>.md`, `flag-<slug>.md`, `mock-review-<slug>.md`, "
        "`adjudication-<task-id>.md`) via `mos_publish_to_shared`. Do NOT "
        "publish into `branches/shared/reviews/` — that surface is reserved "
        "for `mos_review_run`.\n"
        "Cross-cycle memory: use the Draft (`mos_draft_append` / "
        "`mos_draft_summary` / `mos_draft_query`).\n"
    ),
    "expert": (
        "[Role boundary: EACN-visible agent]\n"
        "Communicate state and task handoffs through EACN3. "
        "Preferably read-mostly; write to your own branch only when necessary.\n"
        "Write boundaries: your branch `branches/<expert>/` (sparingly, scientific "
        "scratch only). Publish cross-role handoffs to "
        "`branches/shared/handoffs/` via `mos_publish_to_shared`.\n"
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
    is_expert = role_name == "expert" or role_name.startswith("expert-")
    normalised = "expert" if is_expert else role_name
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

    If *init_brief* is given it is published as a targeted EACN task (or, for
    Noter, a direct message) so the role's first action uses the same bus as
    every later handoff.
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
    """Register an expert role for event-driven invocation."""
    slug = slugify(domain)
    role_name = name or f"expert-{slug}"
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

    # Noter is not registered on EACN3 — it observes via read-only APIs and
    # wakes on a timer (mos_noter_wait) rather than mos_await_events.
    if role_name == "noter":
        agent_token = ""
    else:
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
        # Noter is not on EACN — skip init_brief delivery for it.
        if role_name == "noter":
            logger.info(
                "init_brief skipped for noter (not on EACN): port=%d",
                project_port,
            )
        else:
            target_agent_id = resolve_agent_id(project_port, role_name)
            initiator_id = resolve_agent_id(project_port, "gru")
            try:
                eacn_client.create_task(
                    port=project_port,
                    description=init_brief,
                    domains=role_agent_domains(role_name),
                    initiator_id=initiator_id,
                    budget=0.0,
                    expected_output={
                        "type": "status_or_artifact",
                        "description": (
                            "Handle the initial role brief and report progress through EACN."
                        ),
                    },
                    invited_agent_ids=[target_agent_id],
                )
            except BackendError as exc:
                raise RoleError(
                    f"Role {role_name!r} joined project-local EACN3 on port {project_port}, "
                    f"but the init_brief task could not be queued through EACN3: {exc}"
                ) from exc
            logger.info(
                "init_brief task published via EACN: role=%r port=%d",
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


# Public aliases used by the MCP surface.
spawn_role = register_role
spawn_expert = register_expert


# ---------------------------------------------------------------------------
# Dismiss / list
# ---------------------------------------------------------------------------


def dismiss_role(
    project_port: int,
    role_name: str,
    store: StateStore | None = None,
) -> dict[str, str]:
    """Mark a role dismissed in the registry and unregister it from EACN3."""
    _store = store or StateStore()
    entry = _store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")

    role = next((r for r in entry.active_roles if r.name == role_name), None)
    if role is None:
        raise RoleError(f"Role {role_name!r} not found on port {project_port}.")

    # Noter is not registered on EACN3 — skip unregistration.
    if role_name != "noter":
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
    _store = store or StateStore()
    entry = _store.get_project(project_port)
    if entry is None:
        raise RoleError(f"Project {project_port} not found.")
    return [
        {
            "name": r.name,
            "state": r.state,
            "pid": r.pid,
            "eacn_agent_id": r.eacn_agent_id or r.name,
            "session_name": getattr(r, "session_name", None),
            "session_resumable": getattr(r, "session_resumable", False),
            "workspace_path": getattr(r, "workspace_path", None),
            "workspace_branch": getattr(r, "workspace_branch", None),
        }
        for r in entry.active_roles
    ]
