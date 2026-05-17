"""stdio MCP server exposing MinionsOS project and role management tools.

Each tool is a thin wrapper around ``minions/lifecycle/``.  The server is
started by the ``.mcp.json`` configuration and communicates over stdio.

Tools exposed:
- project_create / project_kill / project_close / project_dormant / project_revive / project_list
- project_set_phase
- project_checkpoint_workspace
- spawn_role / spawn_expert / dismiss_role / list_roles
- project_bridge
- search_arxiv / search_pubmed / search_biorxiv / search_medrxiv / search_google_scholar
- read_*_paper / download_* for supported paper sources
- gru_start_monitor  (starts the Gru heartbeat loop as a background thread)
- exp_* / exp_queue_* / exp_gpu_pool_* experiment tools
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import suppress
from fnmatch import fnmatchcase
from typing import Any, Literal, cast

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from minions.config import resolve_whitelist
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
from minions.lifecycle.role import (
    dismiss_role as _dismiss_role,
)
from minions.lifecycle.role import (
    list_roles as _list_roles,
)
from minions.lifecycle.role import (
    spawn_expert as _spawn_expert,
)
from minions.lifecycle.role import (
    spawn_role as _spawn_role,
)
from minions.logging_setup import configure_logging
from minions.paths import STATE_DIR
from minions.state.store import StateStore
from minions.tools import await_events as _await_events
from minions.tools import experiment_ssh as _exp
from minions.tools import exploration_dag as _dag
from minions.tools import paper_search as _paper_search
from minions.tools import reset as _reset
from minions.tools import review as _review

configure_logging()
logger = logging.getLogger(__name__)

_GRU_START_MONITOR_THREAD: threading.Thread | None = None
_GRU_START_MONITOR_INTERVAL: int | None = None

mcp = FastMCP("minions")

_MINIONS_MCP_TOOL_NAMES = {
    "mos_reset_context",
    "mos_dag_annotate",
    "mos_dag_append",
    "mos_dag_path",
    "mos_dag_query",
    "mos_dag_summary",
    "mos_download_arxiv",
    "mos_download_biorxiv",
    "mos_download_medrxiv",
    "mos_download_pubmed",
    "mos_await_events",
    "mos_get_events",
    "mos_unread_summary",
    "mos_exp_get",
    "mos_exp_gpu_pool_get",
    "mos_exp_gpu_pool_set",
    "mos_exp_kill",
    "mos_exp_list",
    "mos_exp_put",
    "mos_exp_queue_plan",
    "mos_exp_queue_reconcile",
    "mos_exp_queue_status",
    "mos_exp_queue_submit",
    "mos_exp_run",
    "mos_exp_status",
    "mos_exp_tail",
    "mos_exp_wait",
    "mos_spawn_expert",
    "mos_query_gpus",
    "mos_start_monitor",
    "mos_project_checkpoint_workspace",
    "mos_project_close",
    "mos_project_create",
    "mos_project_dormant",
    "mos_project_kill",
    "mos_project_list",
    "mos_project_revive",
    "mos_project_set_phase",
    "mos_read_arxiv_paper",
    "mos_read_biorxiv_paper",
    "mos_read_medrxiv_paper",
    "mos_read_pubmed_paper",
    "mos_project_bridge",
    "mos_review_run",
    "mos_attach_role",
    "mos_dismiss_role",
    "mos_kill_role",
    "mos_list_roles",
    "mos_spawn_role",
    "mos_search_arxiv",
    "mos_search_biorxiv",
    "mos_search_google_scholar",
    "mos_search_medrxiv",
    "mos_search_pubmed",
}


def _csv_names(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def allowed_tool_names_for_profile(
    *,
    profile: str | None = None,
    role: str | None = None,
    agent_type: str | None = None,
) -> set[str]:
    """Return MinionsOS MCP tool names advertised for the current profile."""
    custom = os.environ.get("MINIONS_MCP_TOOLS", "").strip()
    if custom:
        return _csv_names(custom) & _MINIONS_MCP_TOOL_NAMES

    profile = (profile or os.environ.get("MINIONS_MCP_PROFILE", "full")).strip().lower()
    if profile in {"", "full", "all"}:
        return set(_MINIONS_MCP_TOOL_NAMES)

    role = (role or os.environ.get("MINIONS_ROLE_NAME", "")).strip() or "gru"
    agent_type = (agent_type or os.environ.get("MINIONS_AGENT_TYPE", "main")).strip() or "main"
    if agent_type not in {"main", "subagent"}:
        agent_type = "main"

    patterns = resolve_whitelist(role, cast(Literal["main", "subagent"], agent_type))
    return {
        tool_name
        for tool_name in _MINIONS_MCP_TOOL_NAMES
        if any(fnmatchcase(tool_name, pattern) for pattern in patterns)
    }


def configure_mcp_tool_profile() -> set[str]:
    """Disable tools outside the selected profile before serving MCP."""
    allowed = allowed_tool_names_for_profile()
    for tool_name in _MINIONS_MCP_TOOL_NAMES - allowed:
        with suppress(Exception):
            mcp.remove_tool(tool_name)
    logger.info(
        "MinionsOS MCP profile=%s role=%s advertised_tools=%d",
        os.environ.get("MINIONS_MCP_PROFILE", "full"),
        os.environ.get("MINIONS_ROLE_NAME", ""),
        len(allowed),
    )
    return allowed


def _running_sidecar_monitor() -> dict[str, object] | None:
    """Return metadata for a live launcher-managed Gru monitor, if present."""
    pid_path = STATE_DIR / "gru-monitor.pid"
    host_path = STATE_DIR / "gru-monitor.host"
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    except Exception:
        return None
    try:
        host = host_path.read_text(encoding="utf-8").strip().lower()
    except Exception:
        host = ""
    expected = os.environ.get("MINIONS_AGENT_HOST", "").strip().lower()
    return {
        "pid": pid,
        "host": host,
        "host_mismatch": bool(expected and host and host != expected),
    }


def _require_tool_allowed(tool_name: str) -> None:
    """Enforce MinionsOS role tool boundaries inside the MCP server."""
    if os.environ.get("MINIONS_DISABLE_MCP_AUTHZ", "").strip() == "1":
        return
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    if not role:
        return
    agent_type = os.environ.get("MINIONS_AGENT_TYPE", "main").strip() or "main"
    if agent_type not in {"main", "subagent"}:
        agent_type = "main"
    allowed = resolve_whitelist(role, cast(Literal["main", "subagent"], agent_type))
    if any(fnmatchcase(tool_name, pattern) for pattern in allowed):
        return
    raise PermissionError(f"Tool {tool_name!r} is not allowed for role {role!r} ({agent_type}).")


# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class ProjectCreateArgs(BaseModel):
    real_name: str = Field(description="Human-readable project name (e.g. 'Quantum-EC').")
    venue: str | None = Field(default=None, description="Target venue (e.g. 'NeurIPS 2026').")
    base_branch: str = Field(default="HEAD", description="Git base branch for the worktree.")
    upstream: str | None = Field(default=None, description="Upstream branch name.")
    brief: str | None = Field(
        default=None,
        description="Optional 1-3 paragraph project brief; inlined into generated CLAUDE.md.",
    )
    topic_doc: str | None = Field(
        default=None,
        description="Absolute path to a topic/spec doc; recorded in meta.json & CLAUDE.md.",
    )
    template_dir: str | None = Field(
        default=None,
        description=(
            "Absolute path to venue formatting templates; recorded in meta.json & CLAUDE.md."
        ),
    )


class ProjectPortArgs(BaseModel):
    port: int = Field(description="Project port number.")


class ProjectReviveArgs(BaseModel):
    port: int
    external_feedback: str | None = Field(
        default=None, description="Optional external feedback text."
    )
    feedback_source: str | None = Field(
        default=None, description="Source description for the feedback."
    )


class ProjectListArgs(BaseModel):
    filter: Literal["all", "active", "dormant", "closed"] = Field(
        default="all", description="Filter projects by status."
    )


class ProjectPhaseArgs(BaseModel):
    port: int = Field(description="Project port.")
    phase: str | None = Field(
        default=None,
        description="Current project phase name, or null to clear phase gating.",
    )
    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to stay online for the current phase.",
    )
    reason: str | None = Field(default=None, description="Optional human-readable reason.")


class ProjectCheckpointArgs(BaseModel):
    port: int = Field(description="Project port.")
    role_name: str | None = Field(
        default=None,
        description="Optional role name; defaults to the project's main workspace.",
    )
    message: str | None = Field(
        default=None,
        description="Optional git commit message for the durable checkpoint.",
    )


class SpawnRoleArgs(BaseModel):
    project_port: int
    role: str = Field(description="Role name: noter, coder, experimenter, writer, or ethics.")
    init_brief: str | None = Field(
        default=None, description="Initial EACN message to the new role."
    )
    time_trigger_interval: str | None = Field(
        default=None,
        description="Optional periodic wakeup cadence. Noter defaults to gru.yaml.",
    )


class SpawnExpertArgs(BaseModel):
    project_port: int
    domain: str = Field(description="Expert domain (e.g. 'deep learning architecture').")
    name: str | None = Field(default=None, description="Override the auto-generated role name.")
    init_brief: str | None = Field(
        default=None, description="Initial EACN message to the new expert."
    )
    time_trigger_interval: str | None = Field(
        default=None,
        description="Optional periodic wakeup cadence.",
    )


class DismissRoleArgs(BaseModel):
    project_port: int
    role_name: str


class ListRolesArgs(BaseModel):
    project_port: int


class ProjectBridgeArgs(BaseModel):
    from_port: int
    to_port: int
    to_agent_id: str
    content: str
    mode: Literal["auto", "quote", "paraphrase"] = "auto"
    source_note: str | None = None


class PaperSearchArgs(BaseModel):
    query: str = Field(description="Academic paper search query.")
    max_results: int = Field(default=10, ge=1, le=50)


class PaperIdArgs(BaseModel):
    paper_id: str = Field(description="Paper identifier, such as arXiv id, PMID, or DOI.")
    save_path: str = Field(
        default="paper/references/downloads",
        description="Relative output directory under the current project workspace.",
    )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


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
    4. Writes ``meta.json``, ``CLAUDE.md``, ``AGENTS.md``, and the
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
    )
    pdir = _pdir(entry.port).resolve()
    ws = _pws(entry.port).resolve()
    return {
        "port": entry.port,
        "branch": entry.current_branch,
        "workspace_path": str(ws),
        "project_dir": str(pdir),
        "claude_md": str(pdir / "CLAUDE.md"),
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
def mos_spawn_role(args: SpawnRoleArgs) -> dict:
    """Register a fixed role and start its long-lived ``claude`` process.

    Side effects:

    1. Registers a project-local EACN3 AgentCard for the role (so it can
       receive direct messages and bid on tasks).
    2. Prepares the role's git branch worktree under
       ``project_{port}/branches/<role>/``.
    3. Starts a detached tmux session ``mos-{port}-{role}`` running
       ``claude --append-system-prompt @SYSTEM.md ...`` — the role
       enters its forever loop on ``mos_await_events``.

    Idempotent: calling this when the role's tmux session is already
    alive returns the existing session metadata without starting a
    second process.

    ``role`` must be one of ``"noter"``, ``"coder"``, ``"experimenter"``,
    ``"writer"``, ``"ethics"``. For domain experts, use
    ``mos_spawn_expert`` instead.

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
    )


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
    )


@mcp.tool()
def mos_list_roles(args: ListRolesArgs) -> list[dict]:
    """List all roles for a project."""
    _require_tool_allowed("mos_list_roles")
    return _list_roles(project_port=args.project_port)


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


@mcp.tool()
def mos_review_run(args: _review.ReviewRunArgs) -> dict:
    """Run one Area-Chair review round on a submission package.

    Gates on the submission checklist first: any unchecked Required item
    short-circuits with ``{"status": "rejected", ...}`` and no review is
    spawned. On pass, drives the 3-pass review procedure to completion and
    returns the round number, decision label, and produced artifact paths.

    This tool replaces the previous long-lived Reviewer role. Gru invokes it
    when Writer publishes a submission via EACN; the result is relayed back to
    Writer on the project's Local EACN.
    """
    _require_tool_allowed("mos_review_run")
    return _review.review_run(args)


@mcp.tool()
def mos_exp_run(args: _exp.ExpRunArgs) -> dict:
    """Launch a detached local or SSH experiment run."""
    _require_tool_allowed("mos_exp_run")
    return _exp.exp_run(args)


@mcp.tool()
def mos_exp_status(args: _exp.ExpStatusArgs) -> dict:
    """Check an experiment run state."""
    _require_tool_allowed("mos_exp_status")
    return _exp.exp_status(args)


@mcp.tool()
def mos_exp_wait(args: _exp.ExpWaitArgs) -> dict:
    """Poll up to timeout seconds for a run to exit."""
    _require_tool_allowed("mos_exp_wait")
    return _exp.exp_wait(args)


@mcp.tool()
def mos_exp_kill(args: _exp.ExpKillArgs) -> dict:
    """Send SIGTERM to a running experiment process."""
    _require_tool_allowed("mos_exp_kill")
    return _exp.exp_kill(args)


@mcp.tool()
def mos_exp_list(args: _exp.ExpListArgs) -> list[dict]:
    """List known experiment runs on a target."""
    _require_tool_allowed("mos_exp_list")
    return _exp.exp_list(args)


@mcp.tool()
def mos_exp_put(args: _exp.ExpPutArgs) -> dict:
    """Upload a local file to a target workdir."""
    _require_tool_allowed("mos_exp_put")
    return _exp.exp_put(args)


@mcp.tool()
def mos_exp_get(args: _exp.ExpGetArgs) -> dict:
    """Download a target file, refusing files over the experiment size limit."""
    _require_tool_allowed("mos_exp_get")
    return _exp.exp_get(args)


@mcp.tool()
def mos_exp_tail(args: _exp.ExpTailArgs) -> dict:
    """Tail a target log file."""
    _require_tool_allowed("mos_exp_tail")
    return _exp.exp_tail(args)


@mcp.tool()
def mos_query_gpus(args: _exp.QueryGpusArgs) -> list[dict]:
    """Query GPU memory on a target."""
    _require_tool_allowed("mos_query_gpus")
    return _exp.query_gpus(args)


@mcp.tool()
def mos_exp_queue_submit(args: _exp.ExpQueueSubmitArgs) -> dict:
    """Append experiment units to the project-global GPU queue."""
    _require_tool_allowed("mos_exp_queue_submit")
    return _exp.exp_queue_submit(args)


@mcp.tool()
def mos_exp_queue_reconcile(args: _exp.ExpQueueReconcileArgs) -> dict:
    """Run one Python-side experiment queue reconcile pass."""
    _require_tool_allowed("mos_exp_queue_reconcile")
    return _exp.exp_queue_reconcile(args)


@mcp.tool()
def mos_exp_queue_status(args: _exp.ExpQueueStatusArgs) -> dict:
    """Return experiment queue status."""
    _require_tool_allowed("mos_exp_queue_status")
    return _exp.exp_queue_status(args)


@mcp.tool()
def mos_exp_queue_plan(args: _exp.ExpQueuePlanArgs) -> dict:
    """Dry-run a candidate submission against the live GPU snapshot.

    Returns per-unit placement (target/gpu_ids/reserve_mb) or a block reason
    plus the fleet snapshot used. Read-only — nothing is queued and no run
    is launched. Use before ``mos_exp_queue_submit`` when you want to know
    whether a sweep will actually spread or stall.
    """
    _require_tool_allowed("mos_exp_queue_plan")
    return _exp.exp_queue_plan(args)


@mcp.tool()
def mos_exp_gpu_pool_set(args: _exp.ExpQueueGpuPoolSetArgs) -> dict:
    """Set the dynamic GPU allow-list for new experiment runs."""
    _require_tool_allowed("mos_exp_gpu_pool_set")
    return _exp.exp_gpu_pool_set(args)


@mcp.tool()
def mos_exp_gpu_pool_get(args: _exp.ExpQueueGpuPoolGetArgs) -> dict:
    """Return dynamic GPU pool overrides."""
    _require_tool_allowed("mos_exp_gpu_pool_get")
    return _exp.exp_gpu_pool_get(args)


@mcp.tool()
def mos_search_arxiv(args: PaperSearchArgs) -> list[dict]:
    """Search arXiv papers through the project-local MinionsOS MCP server."""
    _require_tool_allowed("mos_search_arxiv")
    return _paper_search.search_arxiv(args.query, args.max_results)


@mcp.tool()
def mos_search_pubmed(args: PaperSearchArgs) -> list[dict]:
    """Search PubMed papers through the project-local MinionsOS MCP server."""
    _require_tool_allowed("mos_search_pubmed")
    return _paper_search.search_pubmed(args.query, args.max_results)


@mcp.tool()
def mos_search_biorxiv(args: PaperSearchArgs) -> list[dict]:
    """Search bioRxiv-indexed preprints through Europe PMC."""
    _require_tool_allowed("mos_search_biorxiv")
    return _paper_search.search_biorxiv(args.query, args.max_results)


@mcp.tool()
def mos_search_medrxiv(args: PaperSearchArgs) -> list[dict]:
    """Search medRxiv-indexed preprints through Europe PMC."""
    _require_tool_allowed("mos_search_medrxiv")
    return _paper_search.search_medrxiv(args.query, args.max_results)


@mcp.tool()
def mos_search_google_scholar(args: PaperSearchArgs) -> list[dict]:
    """Scholar-like broad search using Semantic Scholar metadata."""
    _require_tool_allowed("mos_search_google_scholar")
    return _paper_search.search_google_scholar(args.query, args.max_results)


@mcp.tool()
def mos_read_arxiv_paper(args: PaperIdArgs) -> str:
    """Read arXiv metadata and abstract text for a paper id."""
    _require_tool_allowed("mos_read_arxiv_paper")
    return _paper_search.read_arxiv_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_read_pubmed_paper(args: PaperIdArgs) -> str:
    """Read PubMed metadata and abstract text for a PMID."""
    _require_tool_allowed("mos_read_pubmed_paper")
    return _paper_search.read_pubmed_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_read_biorxiv_paper(args: PaperIdArgs) -> str:
    """Read bioRxiv metadata pointers for a DOI-like paper id."""
    _require_tool_allowed("mos_read_biorxiv_paper")
    return _paper_search.read_biorxiv_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_read_medrxiv_paper(args: PaperIdArgs) -> str:
    """Read medRxiv metadata pointers for a DOI-like paper id."""
    _require_tool_allowed("mos_read_medrxiv_paper")
    return _paper_search.read_medrxiv_paper(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_arxiv(args: PaperIdArgs) -> str:
    """Download an arXiv PDF to a relative workspace path."""
    _require_tool_allowed("mos_download_arxiv")
    return _paper_search.download_arxiv(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_pubmed(args: PaperIdArgs) -> str:
    """Save PubMed metadata and abstract text to a relative workspace path."""
    _require_tool_allowed("mos_download_pubmed")
    return _paper_search.download_pubmed(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_biorxiv(args: PaperIdArgs) -> str:
    """Download a bioRxiv PDF to a relative workspace path."""
    _require_tool_allowed("mos_download_biorxiv")
    return _paper_search.download_biorxiv(args.paper_id, args.save_path)


@mcp.tool()
def mos_download_medrxiv(args: PaperIdArgs) -> str:
    """Download a medRxiv PDF to a relative workspace path."""
    _require_tool_allowed("mos_download_medrxiv")
    return _paper_search.download_medrxiv(args.paper_id, args.save_path)


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

    sidecar = _running_sidecar_monitor()
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


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


# ── Exploration DAG tools ──────────────────────────────────────────────


class DagQueryArgs(BaseModel):
    node_type: str | None = Field(default=None, description="Filter by node type.")
    support_status: str | None = Field(default=None, description="Filter by support status.")
    author_role: str | None = Field(default=None, description="Filter by author role.")
    text_contains: str | None = Field(default=None, description="Substring search in node text.")
    related_to: str | None = Field(
        default=None, description="Return subgraph connected to this node ID."
    )
    limit: int = Field(default=50, description="Max nodes to return.")


class DagAppendArgs(BaseModel):
    nodes: list[dict] | None = Field(
        default=None, description="Nodes to add (type+text required; id auto-gen)."
    )
    edges: list[dict] | None = Field(
        default=None, description="Edges to add (from_id, to_id, relation required)."
    )


class DagAnnotateArgs(BaseModel):
    node_id: str = Field(description="ID of the node to annotate.")
    support_status: str | None = Field(default=None, description="New support status.")
    evidence_tag: str | None = Field(default=None, description="Evidence reference.")
    metadata_update: dict | None = Field(default=None, description="Metadata keys to merge.")


class DagPathArgs(BaseModel):
    target_node_id: str = Field(description="Target node ID.")
    from_node_id: str | None = Field(default=None, description="Start node (default: root).")


@mcp.tool()
def mos_dag_query(args: DagQueryArgs) -> dict:
    """Query the Exploration DAG. Returns matching nodes and their edges."""
    _require_tool_allowed("mos_dag_query")
    return _dag.mos_dag_query(
        node_type=args.node_type,
        support_status=args.support_status,
        author_role=args.author_role,
        text_contains=args.text_contains,
        related_to=args.related_to,
        limit=args.limit,
    )


@mcp.tool()
def mos_dag_append(args: DagAppendArgs) -> dict:
    """Add nodes and/or edges to the Exploration DAG. IDs auto-generated if omitted."""
    _require_tool_allowed("mos_dag_append")
    return _dag.mos_dag_append(nodes=args.nodes, edges=args.edges)


@mcp.tool()
def mos_dag_annotate(args: DagAnnotateArgs) -> dict:
    """Update a node's support_status, evidence_tag, or metadata."""
    _require_tool_allowed("mos_dag_annotate")
    return _dag.mos_dag_annotate(
        node_id=args.node_id,
        support_status=args.support_status,
        evidence_tag=args.evidence_tag,
        metadata_update=args.metadata_update,
    )


@mcp.tool()
def mos_dag_path(args: DagPathArgs) -> dict:
    """Extract the path from root (or from_node_id) to target_node_id."""
    _require_tool_allowed("mos_dag_path")
    return _dag.mos_dag_path(target_node_id=args.target_node_id, from_node_id=args.from_node_id)


@mcp.tool()
def mos_dag_summary() -> dict:
    """Return a high-level DAG summary: node counts, active hypotheses, blocked paths."""
    _require_tool_allowed("mos_dag_summary")
    return _dag.mos_dag_summary()


# ── mos_reset_context ──────────────────────────────────────────────────────────


class MosResetArgs(BaseModel):
    reason: str = Field(
        default="",
        description="Why the reset is happening (e.g. task direction change).",
    )


@mcp.tool()
def mos_reset_context(args: MosResetArgs) -> dict:
    """Clear conversation context and continue with fresh state.

    Call AFTER persisting all discoveries to the DAG. After reset,
    call mos_dag_summary() to re-orient, then mos_await_events().
    """
    _require_tool_allowed("mos_reset_context")
    return _reset.mos_reset_context(reason=args.reason)


# ── Resident-Role tmux helpers ─────────────────────────────────────────


class RoleSessionArgs(BaseModel):
    project_port: int = Field(description="Project port.")
    role_name: str = Field(description="Role name.")


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
def mos_kill_role(args: RoleSessionArgs) -> dict:
    """Kill the tmux session for a Role without dismissing it from the registry.

    Use this when a Role process is wedged and you want the watchdog to
    relaunch it on the next tick. To permanently retire a role use
    ``mos_dismiss_role`` instead.
    """
    _require_tool_allowed("mos_kill_role")
    from minions.lifecycle.role_launcher import kill_session

    killed = kill_session(args.project_port, args.role_name)
    return {
        "project_port": args.project_port,
        "role_name": args.role_name,
        "killed": killed,
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


def main() -> None:
    """Run the MCP server over stdio."""
    configure_mcp_tool_profile()
    mcp.run()


if __name__ == "__main__":
    main()


# Silence a pyflakes warning about the unused BaseModel / Any imports when
# the file is partially loaded in isolation.
_ = (BaseModel, Any)
