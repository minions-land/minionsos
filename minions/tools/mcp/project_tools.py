"""Project lifecycle tools.

Covers: create / close / dormant / kill / revive / list / phase / checkpoint / bridge.
"""

from __future__ import annotations

from minions.lifecycle.project import (
    project_checkpoint_workspace as _project_checkpoint_workspace,
)
from minions.lifecycle.project import project_close as _project_close
from minions.lifecycle.project import project_create as _project_create
from minions.lifecycle.project import project_dormant as _project_dormant
from minions.lifecycle.project import project_kill as _project_kill
from minions.lifecycle.project import project_phase_snapshot
from minions.lifecycle.project import project_revive as _project_revive
from minions.lifecycle.project import project_set_phase as _project_set_phase
from minions.lifecycle.project_bridge import project_bridge as _project_bridge
from minions.state.store import StateStore
from minions.tools.mcp import mcp
from minions.tools.mcp._common import (
    ProjectBridgeArgs,
    ProjectCheckpointArgs,
    ProjectCreateArgs,
    ProjectListArgs,
    ProjectPhaseArgs,
    ProjectPortArgs,
    ProjectReviveArgs,
    _require_tool_allowed,
)


@mcp.tool()
def mos_project_create(args: ProjectCreateArgs) -> dict:
    """Create a new MinionsOS project — heavy side effects.

    What happens:

    1. Allocates a fresh port and reserves it in ``state/projects.json``.
    2. Creates ``project_{port}/`` with ``branches/main/`` as a **new git
       worktree** off the parent repo (the directory containing this
       MinionsOS checkout must be a git repo).
    3. Spawns the project's EACN3 backend as a long-lived subprocess on
       that port and registers a server card.
    4. Writes ``meta.json``, ``CLAUDE.md``, and the
       initial role workspaces.

    Use this only when the author asks to start a new project. To bring
    back a previously-dormant project, use ``mos_project_revive`` instead.

    Returns ``{port, branch, workspace_path, project_dir, claude_md}``.
    Raises ``ProjectError`` / ``BackendError`` on failure (no rollback —
    the operator may need to clean up partial state with ``mos project
    repair``).
    """
    _require_tool_allowed("mos_project_create")
    from minions.paths import project_dir as _pdir
    from minions.paths import project_workspace as _pws

    entry = _project_create(
        real_name=args.real_name,
        venue=args.venue,
        base_branch=args.base_branch,
        upstream=args.upstream,
        brief=args.brief,
        topic_doc=args.topic_doc,
        template_dir=args.template_dir,
        profile=args.profile,
    )
    pdir = _pdir(entry.port).resolve()
    ws = _pws(entry.port).resolve()
    profile_name = getattr(entry, "profile", None) or args.profile or "scientific-paper"
    return {
        "port": entry.port,
        "branch": entry.current_branch,
        "workspace_path": str(ws),
        "project_dir": str(pdir),
        "claude_md": str(pdir / "CLAUDE.md"),
        "profile": profile_name,
    }


@mcp.tool()
def mos_project_close(args: ProjectPortArgs) -> dict:
    """Close a project permanently (stops backend, retires port)."""
    _require_tool_allowed("mos_project_close")
    entry = _project_close(port=args.port)
    return {"port": entry.port}


@mcp.tool()
def mos_project_dormant(args: ProjectPortArgs) -> dict:
    """Put a project into dormant state (stops backend, dismisses roles)."""
    _require_tool_allowed("mos_project_dormant")
    entry = _project_dormant(port=args.port)
    return {"port": entry.port}


@mcp.tool()
def mos_project_kill(args: ProjectPortArgs) -> dict:
    """Hard-stop a project runtime without deleting EACN data or retiring its port."""
    _require_tool_allowed("mos_project_kill")
    return _project_kill(port=args.port)


@mcp.tool()
def mos_project_revive(args: ProjectReviveArgs) -> dict:
    """Revive a dormant project (restarts backend, restores roles)."""
    _require_tool_allowed("mos_project_revive")
    entry = _project_revive(
        port=args.port,
        external_feedback=args.external_feedback,
        feedback_source=args.feedback_source,
    )
    return {"port": entry.port}


@mcp.tool()
def mos_project_list(args: ProjectListArgs) -> list[dict]:
    """List projects, optionally filtered by status."""
    _require_tool_allowed("mos_project_list")
    store = StateStore()
    projects = store.list_projects(filter=args.filter)
    return [
        {
            "port": p.port,
            "name": p.real_name,
            "status": p.status,
            "venue": p.venue,
            "created": p.created,
            "current_branch": p.current_branch,
        }
        for p in projects
    ]


@mcp.tool()
def mos_project_set_phase(args: ProjectPhaseArgs) -> dict:
    """Record the current project phase and wake roles to reconcile."""
    _require_tool_allowed("mos_project_set_phase")
    entry = _project_set_phase(
        port=args.port,
        phase=args.phase,
        allowed_roles=args.allowed_roles or None,
        reason=args.reason,
    )
    phase_snapshot = project_phase_snapshot(entry)
    return {
        "port": entry.port,
        "phase": getattr(entry, "current_phase", None),
        "allowed_roles": phase_snapshot["phase_allowed_roles"],
        "online_roles": phase_snapshot["phase_online_roles"],
        "phase_version": getattr(entry, "phase_version", 0),
    }


@mcp.tool()
def mos_project_checkpoint_workspace(args: ProjectCheckpointArgs) -> dict:
    """Commit the project workspace to its branch and optionally push.

    Side effects (all on the role's git worktree):

    1. ``git add -A`` followed by ``git commit -m <message>`` on the
       role's branch — creates a real commit even if no remote is
       configured.
    2. If ``gru.yaml`` has ``github_push_target`` set for this role,
       also ``git push`` to that remote. The push is best-effort:
       failure logs a warning, the local commit stands.

    Use this at natural durable-state boundaries (between coherent batches
    of work). Calling it on every wake is wasteful; calling it never means
    Role work lives only in the running process.

    Returns ``{commit_sha, branch, pushed: bool, push_error?}``.
    """
    _require_tool_allowed("mos_project_checkpoint_workspace")
    return _project_checkpoint_workspace(
        args.port,
        role_name=args.role_name,
        message=args.message,
    )


@mcp.tool()
def mos_project_bridge(args: ProjectBridgeArgs) -> dict:
    """Bridge a message from one project to a specific agent on another project.

    Cross-project communication is intentionally Gru-only: only Gru sees
    every active project's Local EACN, and only Gru is registered as a
    real ``gru`` agent on each one. This tool performs a single
    ``POST /api/messages`` to ``to_port``'s backend, with sender = that
    backend's real ``gru`` and recipient = ``to_agent_id``. A
    ``[Bridged from project-<from_port>]`` attribution header is prepended
    to the body for traceability.

    Use this when a Role on project A needs to surface a question, finding,
    or hand-off to a specific Role on project B. Messages addressed to
    Gru on the source project are how the request reaches you in the
    first place — pull them with ``mos_get_events(port=A)``.
    """
    _require_tool_allowed("mos_project_bridge")
    return _project_bridge(
        from_port=args.from_port,
        to_port=args.to_port,
        to_agent_id=args.to_agent_id,
        content=args.content,
        mode=args.mode,
        source_note=args.source_note,
    )
