"""Role/expert spawn tools."""

from __future__ import annotations

from minions.lifecycle.role import (
    dismiss_role as _dismiss_role,
)
from minions.lifecycle.role import (
    list_roles as _list_roles,
)
from minions.lifecycle.role import (
    register_expert as _spawn_expert,
)
from minions.lifecycle.role import (
    register_role as _spawn_role,
)
from minions.tools.mcp import mcp
from minions.tools.mcp._common import (
    DismissRoleArgs,
    ListRolesArgs,
    SpawnExpertArgs,
    SpawnRoleArgs,
    _require_tool_allowed,
)


@mcp.tool()
def mos_spawn_role(args: SpawnRoleArgs) -> dict:
    """Register a fixed role and start its long-lived ``claude`` process.

    Side effects:

    1. Registers a project-local EACN3 AgentCard for the role (ethics) so it
       can receive messages and bid on tasks.
    2. Prepares the role's git branch worktree under
       ``project_{port}/branches/<role>/``.
    3. Starts a detached tmux session ``mos-{port}-{role}`` running
       ``claude`` — EACN roles enter their forever loop on
       ``mos_await_events``.

    Idempotent: calling this when the role's tmux session is already
    alive returns the existing session metadata without starting a
    second process.

    ``role`` must be the fixed role ``"ethics"``.
    For the project's general worker, use ``mos_spawn_expert`` (the unified
    Expert handles code, experiments, writing, and figures).

    Returns ``{role, session_name, eacn_agent_id, started, attach_cmd}``.
    """
    _require_tool_allowed("mos_spawn_role")
    return _spawn_role(
        project_port=args.project_port,
        role=args.role,
        init_brief=args.init_brief,
        time_trigger_interval=args.time_trigger_interval,
    )


@mcp.tool()
def mos_spawn_expert(args: SpawnExpertArgs) -> dict:
    """Register a domain expert role and start its long-lived ``claude`` process.

    Same lifecycle as ``mos_spawn_role`` — registers an EACN AgentCard,
    creates a git worktree at ``branches/expert-<slug>/``, starts a tmux
    session, and the expert enters the forever loop on
    ``mos_await_events``. The differentiator is the *domain* parameter,
    which selects an Expert domain pack (``minions/domains/<slug>.md``)
    to be appended to the role system prompt.

    Idempotent on existing live tmux session.

    Returns ``{role, session_name, eacn_agent_id, started, attach_cmd}``.
    """
    _require_tool_allowed("mos_spawn_expert")
    return _spawn_expert(
        project_port=args.project_port,
        domain=args.domain,
        name=args.name,
        init_brief=args.init_brief,
        time_trigger_interval=args.time_trigger_interval,
        workflow_plugin=args.workflow_plugin,
    )


@mcp.tool()
def mos_list_workflow_plugins() -> dict:
    """List available workflow plugins under ``workflow-plugins/``.

    Returns a list of registered workflow plugin manifests with their slug,
    name, description, and capability summary. Gru uses this to discover
    what external workflows are available for spawning as Expert instances.
    """
    _require_tool_allowed("mos_list_workflow_plugins")
    from minions.lifecycle.workflow_plugins import list_available

    plugins = list_available()
    return {"workflow_plugins": plugins, "count": len(plugins)}


@mcp.tool()
def mos_dismiss_role(args: DismissRoleArgs) -> dict:
    """Terminate a resident role and remove its EACN registration.

    Side effects:

    1. Kills the role's tmux session ``mos-{port}-<role>`` if alive.
       The Claude Code session jsonl under
       ``~/.claude/projects/<cwd-slug>/`` is **kept** so a future
       ``mos_project_revive`` (or manual ``mos role inspect``) can
       resume the prior conversation.
    2. Removes the role's project-local EACN AgentCard so peers stop
       routing direct messages and tasks to it.
    3. Marks the role ``dismissed`` in ``projects.json``.

    Use sparingly — sleeping roles cost nothing. Dismiss only when the
    role is genuinely done with the project (e.g. closing a phase) or
    misbehaving and needs a fresh start.

    Returns ``{name, eacn_unregistered: bool, session_killed: bool}``.
    """
    _require_tool_allowed("mos_dismiss_role")
    return _dismiss_role(
        project_port=args.project_port,
        role_name=args.role_name,
        caller="mcp:mos_dismiss_role",
    )


@mcp.tool()
def mos_list_roles(args: ListRolesArgs) -> list[dict]:
    """List all roles for a project."""
    _require_tool_allowed("mos_list_roles")
    return _list_roles(project_port=args.project_port)
