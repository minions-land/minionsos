"""Shared helpers + auth/identity guards + arg models for MCP tools.

Nothing here registers tools; submodules import what they need and the
package-level :data:`minions.tools.mcp.mcp` instance is the registry.
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from fnmatch import fnmatchcase
from typing import Literal, cast

from pydantic import BaseModel, Field

from minions.config import resolve_server_authz
from minions.paths import STATE_DIR
from minions.tools.mcp._registry import mcp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool surface registry — kept in sync with @mcp.tool() decorators
# ---------------------------------------------------------------------------

_MINIONS_MCP_TOOL_NAMES = {
    "mos_compact_context",
    "mos_reset_context",
    "mos_draft_annotate",
    "mos_draft_append",
    "mos_draft_commit_shared",
    "mos_draft_decay_compute",
    "mos_draft_path",
    "mos_draft_view",
    "mos_draft_unmarked_audit",
    "mos_issue_report",
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
    "mos_list_workflow_plugins",
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
    "mos_publish_to_shared",
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
    "mos_role_evolve_evaluate",
    "mos_role_split",
    "mos_role_merge",
    "mos_role_evolve_dismiss",
    "mos_signboard_read",
    "mos_signboard_set",
    "mos_signboard_evaluate",
    "mos_signboard_consume",
    "mos_signboard_reopen",
    "mos_spawn_role",
    "mos_book_ingest",
    "mos_book_ingest_batch",
    "mos_book_lint",
    "mos_book_promote_verified",
    "mos_book_crystallize_session",
    "mos_book_query",
    "mos_book_save_synthesis",
    "mos_book_audit_walk",
    "mos_book_resolve_contradiction",
    "mos_book_dead_end",
    "mos_book_open_question",
    "mos_book_ratify",
    "mos_search_arxiv",
    "mos_search_biorxiv",
    "mos_search_google_scholar",
    "mos_search_medrxiv",
    "mos_search_pubmed",
    "mos_search_papers_federated",
    "mos_search_semantic",
    "mos_resolve_arxiv_ids",
    "mos_visual_render",
    "mos_visual_inspect",
    "mos_visual_check",
    "mos_reel_get",
    "mos_reel_window",
    "mos_submit",
    "mos_evaluate",
    "mos_promote_to_book",
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

    patterns = resolve_server_authz(role, cast(Literal["main", "subagent"], agent_type))
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


def running_sidecar_monitor() -> dict[str, object] | None:
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
    allowed = resolve_server_authz(role, cast(Literal["main", "subagent"], agent_type))
    if any(fnmatchcase(tool_name, pattern) for pattern in allowed):
        return
    raise PermissionError(f"Tool {tool_name!r} is not allowed for role {role!r} ({agent_type}).")


def _normalise_role_name(role: str) -> str:
    """Collapse expert-<slug>, <slug>-expert, and bare 'expert' to 'expert'."""
    from minions.config import normalise_role_name

    return normalise_role_name(role)


def _enforce_caller_identity(claimed_role: str) -> None:
    """Reject MCP calls where the supplied role disagrees with the process role.

    Defends against role-identity spoofing in tools that take a free-form
    ``role`` argument (e.g. ``mos_publish_to_shared``). Without this check
    an Expert process could call ``mos_publish_to_shared(role="gru", ...)``
    and inherit Gru's broader publish policy.
    """
    if os.environ.get("MINIONS_DISABLE_MCP_AUTHZ", "").strip() == "1":
        return
    actual = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    if not actual:
        return
    if _normalise_role_name(claimed_role) != _normalise_role_name(actual):
        raise PermissionError(
            f"role identity mismatch: claimed {claimed_role!r}, "
            f"actual {actual!r}. Pass your own role name."
        )


def _enforce_caller_project(claimed_port: int | None) -> None:
    """Reject cross-project port arguments.

    Without this check a role in project A could pass ``port=<B>`` to
    ``mos_publish_to_shared`` and write commits onto project B's shared
    branch. We trust the MCP server's environment as ground truth — it
    is set per-Role at process spawn and roles cannot mutate it.
    """
    if claimed_port is None:
        return
    if os.environ.get("MINIONS_DISABLE_MCP_AUTHZ", "").strip() == "1":
        return
    raw = os.environ.get("MINIONS_PROJECT_PORT", "").strip()
    if not raw:
        return
    try:
        actual = int(raw)
    except ValueError:
        return
    if int(claimed_port) != actual:
        raise PermissionError(
            f"cross-project publish blocked: claimed port {claimed_port}, "
            f"role process belongs to port {actual}."
        )


# ---------------------------------------------------------------------------
# Argument models shared by multiple tool submodules
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
    profile: str | None = Field(
        default=None,
        description=(
            "Mission profile name (e.g. 'scientific-paper'). "
            "Defaults to 'scientific-paper'. See minions/profiles/ for available options. "
            "Profile selects which roles spawn, deliverable schema, and evaluator."
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


class PublishToSharedArgs(BaseModel):
    role: str = Field(
        description=(
            "Calling role name (gru, ethics, expert, or expert-<slug>). "
            "Used for the per-role subdir policy."
        )
    )
    src_path: str = Field(
        description=(
            "Absolute path to the source file in the role's own branch "
            "worktree (or any readable location)."
        )
    )
    dst_subpath: str = Field(
        description=(
            "Destination relative path under branches/main/, e.g. "
            "'notes/2026-05-17-discussion.md', 'ethics/report-leakage-claim.md', "
            "'exp/exp-42/report.md', or 'handoffs/expert-result.json'. The "
            "first path component must be one of the role's allowed shared "
            "subdirs (reviews/ is reserved for mos_review_run)."
        )
    )
    commit_message: str = Field(
        description="Git commit message for this publish (one line preferred)."
    )
    port: int | None = Field(
        default=None,
        description=(
            "Project port. Defaults to MINIONS_PROJECT_PORT (auto-set in "
            "role processes); pass explicitly when calling from outside."
        ),
    )


class SpawnRoleArgs(BaseModel):
    project_port: int
    role: str = Field(description="Role name: ethics (the one fixed non-Gru role).")
    init_brief: str | None = Field(
        default=None, description="Initial EACN message to the new role."
    )
    time_trigger_interval: str | None = Field(
        default=None,
        description="Optional periodic wakeup cadence (timer-based wake).",
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
    workflow_plugin: str | None = Field(
        default=None,
        description=(
            "Slug of a workflow plugin under workflow-plugins/ to attach. "
            "Injects the plugin's MCP server, domain pack, and skills into this expert."
        ),
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


class PaperFederatedArgs(BaseModel):
    query: str = Field(description="Academic paper search query.")
    sources: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of source keys to query. Defaults to "
            "['arxiv', 'semantic']. Valid keys: 'arxiv', 'pubmed', "
            "'biorxiv', 'medrxiv', 'semantic', 'crossref', 'openalex', 'europepmc'. "
            "Crossref / OpenAlex are valid but pollute results for very recent "
            "arXiv-only preprints — pass them explicitly when querying for "
            "established / DOI-bearing literature."
        ),
    )
    max_results: int = Field(default=5, ge=1, le=50, description="Per-source result count.")


class ArxivIdsArgs(BaseModel):
    ids: list[str] = Field(
        description=(
            "List of arXiv ids to resolve to canonical paper dicts. Bypasses "
            "keyword search via arXiv's id_list= API parameter. Typical use: "
            "extract ids from WebSearch URLs (regex on 'arxiv.org/abs/<id>') "
            "and batch-resolve here for structured citation metadata."
        ),
    )


class RoleEvolveEvaluateArgs(BaseModel):
    project_port: int


class _RoleSpec(BaseModel):
    name: str = Field(description="New role name slug.")
    charter: str = Field(description="One-line description of what the role handles.")
    pitfalls: str = Field(
        default="", description="Observed failure modes the role's prompt should guard against."
    )


class RoleSplitArgs(BaseModel):
    project_port: int
    source_role: str = Field(description="Currently active role to be split.")
    into_specs: list[_RoleSpec] = Field(
        description="At least 2 specialist specs to spawn in place of source_role.",
        min_length=2,
    )
    evidence_refs: list[str] = Field(
        description=(
            "Required. Paths under branches/main/ (or full URLs) pointing at "
            "the failure artifacts that justify this split. An empty list will "
            "be rejected."
        ),
        min_length=1,
    )
    reason: str = Field(default="", description="Free-text rationale for the audit log.")
    dry_run: bool = Field(
        default=False,
        description="If true, log the decision but do not actually spawn or dismiss.",
    )


class RoleMergeArgs(BaseModel):
    project_port: int
    source_roles: list[str] = Field(
        description="One or more currently active roles to merge.",
        min_length=1,
    )
    into_spec: _RoleSpec = Field(description="Spec for the unified role.")
    evidence_refs: list[str] = Field(
        description="Required. Paths to artifacts justifying the merge.",
        min_length=1,
    )
    reason: str = Field(default="", description="Free-text rationale for the audit log.")
    dry_run: bool = Field(default=False)


class RoleDismissEvolveArgs(BaseModel):
    project_port: int
    role_name: str = Field(description="Active role to dismiss.")
    evidence_refs: list[str] = Field(
        description=(
            "Required. Reference(s) to the artifact(s) that justify the dismiss "
            "(typically 'auto:starvation:<role>' from the periodic Gru "
            "evaluator, or a governance-log line ref from a manual review)."
        ),
        min_length=1,
    )
    reason: str = Field(default="", description="Free-text rationale for the audit log.")
    dry_run: bool = Field(default=False)
