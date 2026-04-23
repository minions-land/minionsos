"""stdio MCP server exposing MinionsOS project and role management tools.

Each tool is a thin wrapper around ``minions/lifecycle/``.  The server is
started by the ``.mcp.json`` configuration and communicates over stdio.

Tools exposed:
- project_create / project_close / project_dormant / project_revive / project_list
- spawn_role / spawn_expert / dismiss_role / list_roles
- gru_relay
- gru_start_monitor  (starts the Gru heartbeat loop as a background thread)
"""

from __future__ import annotations

import logging
import threading
from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from minions.lifecycle.project import (
    project_close as _project_close,
)
from minions.lifecycle.project import (
    project_create as _project_create,
)
from minions.lifecycle.project import (
    project_dormant as _project_dormant,
)
from minions.lifecycle.project import (
    project_revive as _project_revive,
)
from minions.lifecycle.relay import gru_relay as _gru_relay
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
from minions.state.store import StateStore

configure_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP("minions")

# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class ProjectCreateArgs(BaseModel):
    real_name: str = Field(description="Human-readable project name (e.g. 'Quantum-EC').")
    venue: str | None = Field(default=None, description="Target venue (e.g. 'NeurIPS 2026').")
    base_branch: str = Field(default="HEAD", description="Git base branch for the worktree.")
    upstream: str | None = Field(default=None, description="Upstream branch name.")


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


class SpawnRoleArgs(BaseModel):
    project_port: int
    role: str = Field(
        description="Role name: noter, coder, experimenter, writer, reviewer, or ethics."
    )
    init_brief: str | None = Field(
        default=None, description="Initial EACN message to the new role."
    )
    poll_interval: str | None = Field(
        default=None,
        description="Override EACN polling cadence (1m / 3m / 5m). Default: gru.yaml.",
    )


class SpawnExpertArgs(BaseModel):
    project_port: int
    domain: str = Field(description="Expert domain (e.g. 'deep learning architecture').")
    name: str | None = Field(default=None, description="Override the auto-generated role name.")
    init_brief: str | None = Field(
        default=None, description="Initial EACN message to the new expert."
    )
    poll_interval: str | None = Field(
        default=None,
        description="Override EACN polling cadence (1m / 3m / 5m). Default: gru.yaml.",
    )


class DismissRoleArgs(BaseModel):
    project_port: int
    role_name: str


class ListRolesArgs(BaseModel):
    project_port: int


class GruRelayArgs(BaseModel):
    from_port: int
    to_port: int
    content: str
    mode: Literal["auto", "quote", "paraphrase"] = "auto"
    source_note: str | None = None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@mcp.tool()
def project_create(args: ProjectCreateArgs) -> dict:
    """Create a new MinionsOS project, start its EACN3 backend, and register it."""
    entry = _project_create(
        real_name=args.real_name,
        venue=args.venue,
        base_branch=args.base_branch,
        upstream=args.upstream,
    )
    return {"port": entry.port, "path": str(entry.current_branch)}


@mcp.tool()
def project_close(args: ProjectPortArgs) -> dict:
    """Close a project permanently (stops backend, retires port)."""
    entry = _project_close(port=args.port)
    return {"port": entry.port}


@mcp.tool()
def project_dormant(args: ProjectPortArgs) -> dict:
    """Put a project into dormant state (stops backend, dismisses roles)."""
    entry = _project_dormant(port=args.port)
    return {"port": entry.port}


@mcp.tool()
def project_revive(args: ProjectReviveArgs) -> dict:
    """Revive a dormant project (restarts backend, restores roles)."""
    entry = _project_revive(
        port=args.port,
        external_feedback=args.external_feedback,
        feedback_source=args.feedback_source,
    )
    return {"port": entry.port}


@mcp.tool()
def project_list(args: ProjectListArgs) -> list[dict]:
    """List projects, optionally filtered by status."""
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
def spawn_role(args: SpawnRoleArgs) -> dict:
    """Spawn a fixed role (noter, coder, experimenter, writer, reviewer, ethics)."""
    return _spawn_role(
        project_port=args.project_port,
        role=args.role,
        init_brief=args.init_brief,
        poll_interval=args.poll_interval,
    )


@mcp.tool()
def spawn_expert(args: SpawnExpertArgs) -> dict:
    """Spawn a domain expert role."""
    return _spawn_expert(
        project_port=args.project_port,
        domain=args.domain,
        name=args.name,
        init_brief=args.init_brief,
        poll_interval=args.poll_interval,
    )


@mcp.tool()
def dismiss_role(args: DismissRoleArgs) -> dict:
    """Dismiss (terminate) a role subprocess."""
    return _dismiss_role(
        project_port=args.project_port,
        role_name=args.role_name,
    )


@mcp.tool()
def list_roles(args: ListRolesArgs) -> list[dict]:
    """List all roles for a project."""
    return _list_roles(project_port=args.project_port)


@mcp.tool()
def gru_relay(args: GruRelayArgs) -> dict:
    """Relay a message from one project to another via EACN broadcast."""
    return _gru_relay(
        from_port=args.from_port,
        to_port=args.to_port,
        content=args.content,
        mode=args.mode,
        source_note=args.source_note,
    )


class SchedulePollArgs(BaseModel):
    interval: str = Field(
        description="Poll cadence: one of '1m', '3m', '5m'.",
    )


@mcp.tool()
def schedule_poll(args: SchedulePollArgs) -> dict:
    """DEPRECATED no-op — Role polling is now Python-side via WakeupScheduler.

    Roles are ephemeral: they are invoked by the Python-level
    ``minions.lifecycle.wakeup.WakeupScheduler`` when EACN events arrive.
    No in-Claude polling loop is needed, and this MCP tool has been
    downgraded to a no-op recorder kept for backward compatibility.
    """
    import os as _os

    role = _os.environ.get("MINIONS_ROLE_NAME", "<unknown>")
    port = _os.environ.get("MINIONS_PROJECT_PORT", "<unknown>")
    logger.warning(
        "schedule_poll is deprecated (role=%s port=%s interval=%s); "
        "polling is handled by WakeupScheduler.",
        role,
        port,
        args.interval,
    )
    return {
        "role": role,
        "project_port": port,
        "interval": args.interval,
        "ok": True,
        "deprecated": True,
    }


@mcp.tool()
def gru_start_monitor(heartbeat_interval: int | None = None) -> dict:
    """Start the Gru heartbeat/health monitor as a background daemon thread.

    Args:
        heartbeat_interval: Override the interval in seconds (default from gru.yaml).

    Returns:
        ``{"started": True, "interval": <seconds>}``
    """
    from minions.gru.loop import GruLoop

    loop = GruLoop(heartbeat_interval=heartbeat_interval)
    t = threading.Thread(target=loop.run, daemon=True, name="gru-monitor")
    t.start()
    logger.info("Gru monitor thread started (interval=%ds).", loop.interval)
    return {"started": True, "interval": loop.interval}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
