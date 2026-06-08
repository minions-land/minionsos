"""Configuration models and loaders for MinionsOS.

Two config files are supported:

* ``minions/config/gru.yaml``  — global Gru settings.
* ``minions/config/experiment_targets.yaml``  — SSH / local execution targets.

Both files are gitignored; only ``*.yaml.example`` files are committed.
Loaders return sensible defaults when the file is absent.
"""

from __future__ import annotations

import enum
import logging
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from minions.errors import ConfigError
from minions.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slug utility
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd]?)\s*$", re.IGNORECASE)
_DURATION_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
_PAPER_SEARCH_TOOLS = [
    "mos_search_arxiv",
    "mos_search_pubmed",
    "mos_search_biorxiv",
    "mos_search_medrxiv",
    "mos_search_google_scholar",
    "mos_search_semantic",
    "mos_search_papers_federated",
    "mos_resolve_arxiv_ids",
    "mos_download_arxiv",
    "mos_download_pubmed",
    "mos_download_biorxiv",
    "mos_download_medrxiv",
    "mos_read_arxiv_paper",
    "mos_read_pubmed_paper",
    "mos_read_biorxiv_paper",
    "mos_read_medrxiv_paper",
]


def parse_duration(value: str | int) -> int:
    """Parse a duration string like ``"2h"``, ``"30m"``, ``"45s"``, ``"1d"`` or a
    bare integer to seconds. ``"0"``/``0`` disables (returns 0).

    Raises :class:`ConfigError` on malformed input.
    """
    if isinstance(value, int):
        if value < 0:
            raise ConfigError(f"Negative duration not allowed: {value!r}")
        return value
    if not isinstance(value, str):
        raise ConfigError(f"Unsupported duration type: {type(value).__name__}")
    m = _DURATION_RE.match(value)
    if not m:
        raise ConfigError(f"Invalid duration: {value!r} (expected '<N>[s|m|h|d]')")
    n, unit = m.group(1), m.group(2).lower()
    return int(n) * _DURATION_UNITS[unit]


def slugify(text: str) -> str:
    """Convert *text* to a lowercase hyphen-separated slug.

    Examples::

        >>> slugify("Deep Learning Architecture")
        'deep-learning-architecture'
        >>> slugify("NLP / Text Generation")
        'nlp-text-generation'
    """
    return _SLUG_RE.sub("-", text.lower().strip()).strip("-")


# ---------------------------------------------------------------------------
# Whitelist resolver
# ---------------------------------------------------------------------------

# Cache-keepalive MCP tools. Available to every Role and every subagent so
# the wait_bg / keepalive_now loop (driven by the bg_keepalive_nudge hook)
# can run anywhere. The MCP server is registered globally in `.mcp.json`.
_KEEPALIVE_TOOLS = [
    "wait_bg",
    "keepalive_now",
]

# Issue-tracker tool. Universally available to every Role and every
# subagent — when something feels wrong with the scaffolding (broken
# tool, contradictory SYSTEM, missing skill, tool-surface gap), the
# caller drops a structured report into project_{port}/issues/. No
# coordination, no EACN traffic; the human triages later.
_ISSUE_REPORT_TOOLS = [
    "mos_issue_report",
]

# Draft (L1) tools every role uses to inspect/extend the buffered graph.
# They are explicitly listed (not via the ``mos_draft_*`` glob) because
# ``mos_draft_commit_shared`` is reserved for Ethics (the memory curator)
# and Gru — committing the Draft is a curator action, not a per-role one.
_DRAFT_RW_TOOLS = [
    "mos_draft_annotate",
    "mos_draft_append",
    "mos_draft_path",
    "mos_draft_view",
]

_BOOK_READ_TOOLS = [
    "mos_book_query",
]

# Book synthesis-write tool: persists a question→answer synthesis as a
# compounding Book page. Whitelisted to Ethics and Gru only —
# Ethics (the memory curator) materializes role-supplied syntheses verbatim.
# The synthesis content itself can come from any role's reasoning (delivered
# via EACN message), but the persist call goes through Ethics to honor the
# Book ownership invariant in publish.py: only Ethics publishes to book/.
_BOOK_SYNTHESIS_WRITE_TOOLS = [
    "mos_book_save_synthesis",
]

# Book audit tools: Ethics primary entry points for the dynamic-walk
# audit workflow. ``mos_book_audit_walk`` lists unresolved contradictions
# with their reel_refs surfaced; ``mos_book_resolve_contradiction``
# writes the verdict back. Whitelisted to Ethics + Gru only.
_BOOK_AUDIT_TOOLS = [
    "mos_book_audit_walk",
    "mos_book_resolve_contradiction",
]

# Draft audit tools: Ethics-facing descriptive signal over Draft nodes (where
# evidence_tag actually lives). ``mos_draft_unmarked_audit`` reports per-role
# unmarked-claim ratios and flags roles above a threshold — advisory only, no
# mutation, no auto-trigger. Whitelisted to Ethics + Gru, mirroring the Book
# audit surface.
_DRAFT_AUDIT_TOOLS = [
    "mos_draft_unmarked_audit",
]

# Book ratification — Ethics-only. Promotes a verified Book page from the
# proposed pool into the ratified set. Ethics owns the Book curation/audit
# write surface; ratify is the final audit gate that stamps a page as durable
# knowledge.
_BOOK_RATIFY_TOOLS = [
    "mos_book_ratify",
]

# Book question/dead-end tools. ``mos_book_open_question`` is wide-open
# (any EACN-visible role can flag a pending question); ``mos_book_dead_end``
# is curator-owned at server side so the registry stays evidence-audited.
_BOOK_OPEN_QUESTION_TOOLS = [
    "mos_book_open_question",
]
_BOOK_DEAD_END_TOOLS = [
    "mos_book_dead_end",
]

# Visual format-check tools. Format-agnostic detectors over rendered PDF page
# images (column voids, edge overflow, trailing whitespace, column imbalance,
# float clustering, short lines). Whitelisted to every EACN-visible main role
# so Experts can verify paper PDFs, generated figures, and plots while Ethics
# can audit figure-quality claims.
_VISUAL_CHECK_TOOLS = [
    "mos_visual_render",
    "mos_visual_inspect",
    "mos_visual_check",
]

# Reel (L0) tools. Raw session-level execution traces for drill-down audit.
# Whitelisted to every EACN-visible main role so any role can inspect its own
# reel and Gru can read cross-role reels. Server-side authz enforces the
# role-private boundary (non-Gru roles can only read their own reels).
_REEL_TOOLS = [
    "mos_reel_get",
    "mos_reel_window",
]

# Gru's EACN surface is intentionally narrower than the wildcard ``eacn3_*``.
# Gru is the human-facing window and the cross-project bridge — it observes
# the project bus and addresses Roles via direct messages, but it does NOT
# bid on or post tasks: that's the Roles' contract. Allowing the wildcard
# here let a Gru that mis-read its own boundary call ``eacn3_create_task``
# / ``eacn3_submit_bid`` / ``eacn3_submit_result`` and contaminate the bus
# with phantom load. Roles still see the wildcard via the unified CLI
# whitelist (KV cache parity); the boundary lives in the server-authz row.
_GRU_EACN_TOOLS = [
    # Direct messages out (only outgoing channel Gru should use).
    "eacn3_send_message",
    # Read / observe — Gru audits the bus but never writes tasks/results.
    "eacn3_get_messages",
    "eacn3_get_events",
    "eacn3_await_events",
    "eacn3_next",
    "eacn3_list_tasks",
    "eacn3_list_open_tasks",
    "eacn3_get_task",
    "eacn3_get_task_status",
    "eacn3_get_task_results",
    "eacn3_list_agents",
    "eacn3_list_my_agents",
    "eacn3_get_agent",
    "eacn3_discover_agents",
    "eacn3_list_sessions",
    "eacn3_get_reputation",
    # Lifecycle / registry — Gru is the registrar.
    "eacn3_register_agent",
    "eacn3_unregister_agent",
    "eacn3_update_agent",
    "eacn3_connect",
    "eacn3_disconnect",
    "eacn3_heartbeat",
    "eacn3_health",
    "eacn3_server_info",
    "eacn3_report_event",
    # Cluster / federation reads — observability only.
    "eacn3_cluster_status",
    "eacn3_reverse_control_status",
]

# Maps (role_name, agent_type) → list of allowed tool prefixes / names.
# "main" = the top-level role agent-host process; "subagent" = spawned sub-processes.
#
# Cache optimization (Tier 2): all EACN-visible roles share a single unified
# "main" whitelist so their --allowed-tools CLI arg is byte-identical. This
# makes the tool-definitions block in the system prompt identical across roles,
# enabling cross-role KV cache sharing at the API level. Server-side authz in
# _require_tool_allowed() still enforces the real per-role boundary — the
# unified CLI whitelist is the "what the model can see" surface, while the
# server-side check is the "what actually executes" boundary.
#
_EACN_ROLE_MAIN_TOOLS: list[str] = [
    *_KEEPALIVE_TOOLS,
    *_ISSUE_REPORT_TOOLS,
    # EACN communication (all EACN roles)
    "eacn3_*",
    "mos_await_events",
    "mos_get_events",
    "mos_unread_summary",
    # Draft (CLI-visible surface; server-side authz controls commit)
    "mos_draft_*",
    # Book
    *_BOOK_READ_TOOLS,
    "mos_book_ingest",
    "mos_book_ingest_batch",
    "mos_book_lint",
    "mos_book_promote_verified",
    "mos_book_crystallize_session",
    # Book synthesis-write (compounding queries; any role can save its
    # own synthesis as a Book page).
    *_BOOK_SYNTHESIS_WRITE_TOOLS,
    # Book audit tools (Ethics/Gru-only at server side; appear in CLI
    # whitelist for KV cache parity).
    *_BOOK_AUDIT_TOOLS,
    # Book ratify-promotion (Ethics-only at server side; appears in CLI
    # whitelist for KV cache parity).
    *_BOOK_RATIFY_TOOLS,
    # Open-question is wide-open (any EACN role); dead-end is curator-owned
    # at server side. Both appear in CLI whitelist for KV cache parity.
    *_BOOK_OPEN_QUESTION_TOOLS,
    *_BOOK_DEAD_END_TOOLS,
    # Shared branch publish
    "mos_publish_to_shared",
    # Signboard
    "mos_signboard_read",
    "mos_signboard_set",
    "mos_signboard_evaluate",
    "mos_signboard_consume",
    "mos_signboard_reopen",
    # Context management
    "mos_reset_context",
    "mos_compact_context",
    # Project lifecycle (Gru-only at server side)
    "mos_project_bridge",
    "mos_project_checkpoint_workspace",
    "mos_project_create",
    "mos_project_kill",
    "mos_project_close",
    "mos_project_dormant",
    "mos_project_revive",
    "mos_project_set_phase",
    "mos_project_list",
    # Role management (Gru-only at server side)
    "mos_attach_role",
    "mos_kill_role",
    "mos_spawn_role",
    "mos_spawn_expert",
    "mos_list_workflow_plugins",
    "mos_dismiss_role",
    "mos_list_roles",
    "mos_role_evolve_evaluate",
    "mos_role_split",
    "mos_role_merge",
    "mos_role_evolve_dismiss",
    "mos_review_run",
    "mos_submit",
    "mos_evaluate",
    "mos_promote_to_book",
    "mos_start_monitor",
    # Experiment tools (Expert-authorized at server side)
    "mos_exp_run",
    "mos_exp_status",
    "mos_exp_wait",
    "mos_exp_kill",
    "mos_exp_list",
    "mos_exp_put",
    "mos_exp_get",
    "mos_exp_tail",
    "mos_query_gpus",
    "mos_exp_queue_*",
    "mos_exp_gpu_pool_*",
    # Paper search
    *_PAPER_SEARCH_TOOLS,
    # Visual format-check (renders + detectors over PDF page images)
    *_VISUAL_CHECK_TOOLS,
    # Reel (L0) — raw session traces for drill-down audit
    *_REEL_TOOLS,
    # Subagent dispatch
    "Task",
    # Workflow plugin invocation (Claude Code built-in). Server-side authz
    # enforces the per-role boundary; subagents do not get Workflow to
    # preserve the anti-recursion principle.
    "Workflow",
    # General tools
    "WebSearch",
    "WebFetch",
    "Bash",
    "Read",
    "Write",
    "Edit",
]

_WHITELIST: dict[tuple[str, str], list[str]] = {
    ("gru", "main"): _EACN_ROLE_MAIN_TOOLS,
    ("gru", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("expert", "main"): _EACN_ROLE_MAIN_TOOLS,
    ("expert", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "mos_exp_run",
        "mos_exp_status",
        "mos_exp_wait",
        "mos_exp_kill",
        "mos_exp_list",
        "mos_exp_put",
        "mos_exp_get",
        "mos_exp_tail",
        "mos_query_gpus",
        "mos_exp_queue_*",
        "mos_exp_gpu_pool_*",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("ethics", "main"): _EACN_ROLE_MAIN_TOOLS,
    ("ethics", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    ],
}


def is_expert_role(role: str) -> bool:
    """Return True if *role* is an Expert in any of the accepted name shapes.

    Accepted shapes:
    - bare ``"expert"`` (the canonical authz key);
    - prefix form ``"expert-<slug>"`` (default for ``register_expert``);
    - suffix form ``"<slug>-expert"`` (used when callers want the role's
      identity to lead with its specialty — e.g. ``theory-normalization-expert``).

    Without the suffix-form arm, every collapse site fell through to the
    empty-list branch in ``resolve_whitelist`` / ``resolve_server_authz``,
    which silently zero'd out the role's tool surface and trapped its
    event loop. See GitHub Issue #1 for the failure mode.
    """
    return role == "expert" or role.startswith("expert-") or role.endswith("-expert")


def normalise_role_name(role: str) -> str:
    """Collapse any expert-shaped role name to the bare authz key ``"expert"``."""
    return "expert" if is_expert_role(role) else role


def resolve_whitelist(role: str, agent_type: Literal["main", "subagent"] = "main") -> list[str]:
    """Return the allowed-tools list for *role* and *agent_type*.

    This is the **CLI-visible** whitelist used for ``--allowed-tools``. All
    EACN roles share the same unified list so their tool-definition blocks
    are byte-identical for cross-role KV cache sharing. Server-side authz
    (the real enforcement boundary) uses :func:`resolve_server_authz`.

    Expert roles in any of the three accepted shapes (``"expert"``,
    ``"expert-<slug>"``, ``"<slug>-expert"``) collapse to the bare authz
    key ``"expert"`` before lookup.

    Args:
        role: Role name, e.g. ``"ethics"``, ``"expert-dl-arch"``,
            ``"theory-normalization-expert"``.
        agent_type: ``"main"`` or ``"subagent"``.

    Returns:
        List of tool name patterns (may contain ``*`` wildcards).
    """
    normalised = normalise_role_name(role)
    key = (normalised, agent_type)
    if key not in _WHITELIST:
        logger.warning(
            "No whitelist entry for role=%s agent_type=%s; returning empty.", role, agent_type
        )
        return []
    return list(_WHITELIST[key])


def whitelist_csv(role: str, agent_type: Literal["main", "subagent"] = "main") -> str:
    """Return the whitelist as a comma-separated string for ``--allowed-tools``."""
    return ",".join(resolve_whitelist(role, agent_type))


# ---------------------------------------------------------------------------
# Server-side authorization (real enforcement boundary)
# ---------------------------------------------------------------------------

# The per-role authz table preserves the original fine-grained boundaries.
# _require_tool_allowed() in mcp_server.py uses this to reject calls that
# the model can "see" (via the unified CLI whitelist) but is not authorized
# to execute for its role.
_SERVER_AUTHZ: dict[tuple[str, str], list[str]] = {
    ("gru", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "mos_project_bridge",
        "mos_project_checkpoint_workspace",
        "mos_project_create",
        "mos_project_kill",
        "mos_project_close",
        "mos_project_dormant",
        "mos_project_revive",
        "mos_project_set_phase",
        "mos_project_list",
        # Gru's EACN surface — read + direct-message only. NEVER includes
        # eacn3_create_task / eacn3_submit_bid / eacn3_submit_result /
        # eacn3_select_result / eacn3_close_task / eacn3_reject_task /
        # eacn3_create_subtask / eacn3_team_*. Tasks are a Role-to-Role
        # contract; Gru-as-task-issuer would duplicate Role work and
        # contaminate the bus with phantom load. See coda-epilogue
        # session note 2026-05-26 (Gru attempted HTTP-direct task post
        # after the MCP path was authz-blocked).
        *_GRU_EACN_TOOLS,
        "mos_get_events",
        "mos_unread_summary",
        "mos_draft_*",
        *_BOOK_READ_TOOLS,
        *_BOOK_SYNTHESIS_WRITE_TOOLS,  # Gru can materialize syntheses
        *_BOOK_AUDIT_TOOLS,  # Gru is the only role besides Ethics that audits
        *_DRAFT_AUDIT_TOOLS,  # Gru shares the Draft unmarked-ratio audit signal
        *_BOOK_OPEN_QUESTION_TOOLS,  # Gru can flag pending questions
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_signboard_evaluate",
        "mos_signboard_consume",
        "mos_signboard_reopen",
        "mos_reset_context",
        "mos_compact_context",
        "mos_attach_role",
        "mos_kill_role",
        "mos_spawn_role",
        "mos_spawn_expert",
        "mos_list_workflow_plugins",
        "mos_dismiss_role",
        "mos_list_roles",
        "mos_role_evolve_evaluate",
        "mos_role_split",
        "mos_role_merge",
        "mos_role_evolve_dismiss",
        "mos_review_run",
        "mos_submit",
        "mos_evaluate",
        "mos_promote_to_book",
        "mos_start_monitor",
        *_PAPER_SEARCH_TOOLS,
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Gru can read any role's reel
        "Workflow",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("gru", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("expert", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "eacn3_*",
        "mos_await_events",
        *_DRAFT_RW_TOOLS,
        *_BOOK_READ_TOOLS,
        *_BOOK_OPEN_QUESTION_TOOLS,  # any EACN role may flag a pending question
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        "mos_project_checkpoint_workspace",
        # Expert is the unified worker: science, experiments, writing, and figures.
        "mos_exp_run",
        "mos_exp_status",
        "mos_exp_wait",
        "mos_exp_kill",
        "mos_exp_list",
        "mos_exp_put",
        "mos_exp_get",
        "mos_exp_tail",
        "mos_query_gpus",
        "mos_exp_queue_*",
        "mos_exp_gpu_pool_*",
        *_PAPER_SEARCH_TOOLS,
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Expert can read own reel
        "Workflow",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("expert", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "mos_exp_run",
        "mos_exp_status",
        "mos_exp_wait",
        "mos_exp_kill",
        "mos_exp_list",
        "mos_exp_put",
        "mos_exp_get",
        "mos_exp_tail",
        "mos_query_gpus",
        "mos_exp_queue_*",
        "mos_exp_gpu_pool_*",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("ethics", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "eacn3_*",
        "mos_await_events",
        # Ethics is the memory curator + auditor + adjudicator: it owns the
        # full Draft surface (including commit) and Book curation/audit tools.
        "mos_draft_*",
        *_BOOK_READ_TOOLS,
        "mos_book_ingest",
        "mos_book_ingest_batch",
        "mos_book_lint",
        "mos_book_promote_verified",
        "mos_book_crystallize_session",
        *_BOOK_SYNTHESIS_WRITE_TOOLS,  # materializes role-supplied syntheses
        *_BOOK_AUDIT_TOOLS,  # Ethics is the primary auditor
        *_DRAFT_AUDIT_TOOLS,  # Ethics audits Draft evidence-tag coverage
        *_BOOK_RATIFY_TOOLS,  # Ethics-only: ratify-promotion is the audit gate
        *_BOOK_OPEN_QUESTION_TOOLS,  # flag pending questions
        *_BOOK_DEAD_END_TOOLS,  # sole direct writer for dead-ends
        *_PAPER_SEARCH_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Ethics can read any role's reel (cross-role audit)
        "Workflow",
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    ],
    ("ethics", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    ],
}


def resolve_server_authz(role: str, agent_type: Literal["main", "subagent"] = "main") -> list[str]:
    """Return the server-side authorization list for *role* and *agent_type*.

    This is the **real enforcement boundary** used by ``_require_tool_allowed``
    in the MCP server. It preserves the original per-role tool restrictions
    regardless of the unified CLI whitelist.

    Args:
        role: Role name, e.g. ``"ethics"``, ``"expert-dl-arch"``.
        agent_type: ``"main"`` or ``"subagent"``.

    Returns:
        List of tool name patterns (may contain ``*`` wildcards).
    """
    normalised = normalise_role_name(role)
    key = (normalised, agent_type)
    if key not in _SERVER_AUTHZ:
        logger.warning(
            "No server_authz entry for role=%s agent_type=%s; returning empty.",
            role,
            agent_type,
        )
        return []
    return list(_SERVER_AUTHZ[key])


# ---------------------------------------------------------------------------
# Role classification and boundaries
# ---------------------------------------------------------------------------


class RoleType(enum.Enum):
    """Whether a role faces the human or the EACN coordination network."""

    human_side = "human_side"
    eacn_visible = "eacn_visible"


ROLE_CLASSIFICATION: dict[str, RoleType] = {
    "gru": RoleType.human_side,
    "ethics": RoleType.eacn_visible,
    "expert": RoleType.eacn_visible,
}

ROLE_WRITE_BOUNDARIES: dict[str, list[str]] = {
    "gru": [
        "branches/main/",
        "branches/main/<any>/ (via mos_publish_to_shared)",
    ],
    "ethics": [
        "branches/ethics/ (drafts, investigation notes)",
        "branches/main/ethics/ (via mos_publish_to_shared)",
        "branches/main/notes/ (via mos_publish_to_shared)",
        "branches/main/handoffs/ (via mos_publish_to_shared)",
        "branches/main/book/ (Book curation: ingest + promote)",
        "branches/main/draft/draft.json (via mos_draft_commit_shared)",
        "branches/main/governance/signboard.json (via mos_signboard_set)",
    ],
    "expert": [
        "branches/<expert>/ (src/experiments/, exp/, paper/, notes/)",
        "branches/main/exp/ (via mos_publish_to_shared)",
        "branches/main/handoffs/ (via mos_publish_to_shared)",
        "branches/main/governance/signboard.json (via mos_signboard_set)",
    ],
}


# ---------------------------------------------------------------------------
# gru.yaml model
# ---------------------------------------------------------------------------


class GruConfig(BaseModel):
    """Settings loaded from ``minions/config/gru.yaml``."""

    heartbeat_report_interval: str = Field(
        default="3m",
        description="Heartbeat report interval (e.g. '30s', '5m', '2h'). '0' disables.",
    )

    @property
    def heartbeat_interval_seconds(self) -> int:
        """Parse ``heartbeat_report_interval`` to integer seconds."""
        return parse_duration(self.heartbeat_report_interval)

    allow_web_search: bool = Field(
        default=True,
        description="When False, web search tools are stripped from all role whitelists.",
    )
    log_level: str = Field(
        default="info",
        description="Logging level (debug, info, warning, error).",
    )
    base_branch: str = Field(
        default="HEAD",
        description="Default git base branch for new project worktrees.",
    )
    author_repo: str | None = Field(
        default=None,
        description=(
            "Optional path to the author's source git repo, used as the "
            "*seed* for per-project bare repos at project_create time. "
            "When unset, MinionsOS uses MINIONS_ROOT.parent (the directory "
            "MinionsOS was placed inside). After seeding, project branches "
            "live entirely inside project_{port}/parent_repo.git/ and the "
            "author repo is never touched again."
        ),
    )
    projects_root: str | None = Field(
        default=None,
        description=(
            "Optional directory that contains project_<port>/ runtime trees. "
            "When unset, project directories live beside MINIONS_ROOT."
        ),
    )
    github_push_target: str | None = Field(
        default=None,
        description=(
            "Optional git remote URL or remote name used for durable workspace "
            "checkpoints. When unset, MinionsOS keeps commits local and skips git push."
        ),
    )
    github_push_branch_prefix: str = Field(
        default="minionsos",
        description="Branch prefix used when pushing durable checkpoints to github_push_target.",
    )
    github_issues_repo: str | None = Field(
        default=None,
        description=(
            "Optional `owner/repo` target for `mos_issue_report` GitHub uploads. "
            "When set (or via env MINIONS_GITHUB_ISSUES_REPO), each issue filed "
            "is also posted via `gh issue create`. Local JSONL is always written "
            "first regardless of upload outcome."
        ),
    )
    backend_crash_threshold: int = Field(
        default=3,
        description="Max backend crashes within crash_window_seconds before auto-restart stops.",
    )
    role_crash_threshold: int = Field(
        default=3,
        description="Max role crashes within crash_window_seconds before role is dismissed.",
    )
    crash_window_seconds: int = Field(
        default=3600,
        description="Rolling window (seconds) for crash counting (default 1 h).",
    )
    role_cooldown_seconds: int = Field(
        default=30,
        description="Minimum seconds between dispatches for the same role (any wakeup class).",
    )
    experiment_reconcile_interval_seconds: int = Field(
        default=30,
        description="Python-side experiment queue reconcile cadence in seconds.",
    )
    role_evolution_interval_seconds: int = Field(
        default=900,
        description=(
            "How often Gru evaluates whether any role should split or merge. "
            "Recommendations are always logged to "
            "branches/main/governance/role_evolution.jsonl; whether they are "
            "auto-applied is gated on role_evolution_auto_apply. Default 15 min."
        ),
    )
    role_evolution_auto_apply: bool = Field(
        default=False,
        description=(
            "When True, Gru automatically calls mos_role_split / mos_role_merge "
            "for every recommendation produced by the periodic evaluation. "
            "Default False: the operator inspects the JSONL log and applies "
            "the decision manually. Set True only after the evidence-gated "
            "recommendation stream has been validated on a real workload."
        ),
    )
    gru_drive_enabled: bool = Field(
        default=False,
        description=(
            "When True, Gru periodically scans active projects and sends an "
            "EACN advisory message to the most-stale Role asking it to "
            "report status or progress. This is the 'Gru actively drives "
            "the project' loop — the user-visible counterpart to the "
            "watchdog (which only respawns dead processes). Default False "
            "to avoid surprising existing setups; turn on after observing "
            "the recommendation cadence on a real run."
        ),
    )
    gru_drive_interval_seconds: int = Field(
        default=600,
        description=(
            "How often the Gru drive loop ticks. At each tick, the loop reads "
            "the per-project Draft + role activity stats and, if any active "
            "Role has been silent for longer than gru_drive_stale_minutes, "
            "sends a single advisory EACN message asking for a status check. "
            "Cheap (no LLM tokens spent on Gru's side; the Role decides what "
            "to do). Default 600 (10 min)."
        ),
    )
    gru_drive_stale_minutes: int = Field(
        default=15,
        description=(
            "A Role is considered stale by the Gru drive loop when no "
            "EACN message from it has been seen in this many minutes. "
            "Default 15."
        ),
    )
    wedge_watchdog_enabled: bool = Field(
        default=True,
        description=(
            "When True, Gru periodically scans each active Role's tmux "
            "pane log for the `[upstream returned no content]` + bare `ack` "
            "loop signature (GitHub Issue #15). If detected, the watchdog "
            "kills the tmux session so the main respawn path cold-starts "
            "the Role from its Draft. Heartbeats lie for this failure mode "
            "(the PreToolUse hook refreshes on every empty turn), so the "
            "only reliable detector is log-tail pattern matching."
        ),
    )
    gru_digest_enabled: bool = Field(
        default=True,
        description=(
            "When True, Gru runs a periodic digest cron that snapshots each "
            "active project's per-role event flow + Draft growth, persists "
            "the report under branches/main/governance/gru-digest/, and "
            "emits a `draft_lag` health event when a role received real "
            "events in the window but produced zero Draft nodes (the "
            "Draft-discipline observation that motivated v15.16). Cheap — "
            "no LLM tokens, just disk reads + one markdown write per tick."
        ),
    )
    gru_digest_interval_seconds: int = Field(
        default=270,
        description=(
            "How often the Gru digest cron ticks. Default 270 (4 min 30 s) "
            "deliberately mismatches the wedge watchdog cadence so the two "
            "background threads don't collide on the same tick boundary, "
            "and aligns just under the cache-keepalive cliff (240 s) so the "
            "digest's tiny stat reads don't sit on top of a keepalive turn."
        ),
    )
    gru_digest_anomaly_min_events: int = Field(
        default=3,
        description=(
            "Minimum real-event count in a digest window before a "
            "zero-Draft-growth row is reported as an anomaly. Below this "
            "threshold the absence of Draft writes is consistent with "
            "trivial events (acks, status pings) that don't warrant a "
            "Draft node."
        ),
    )
    stagnation_vote_enabled: bool = Field(
        default=True,
        description=(
            "Enable Gru's stall-breaker: when a project is silent on every "
            "productive axis (no Draft growth, no main-branch shared-surface commits, no "
            "experiment runs) for stagnation_vote_window_seconds, Gru "
            "broadcasts a milestone-vote request to every eligible signer. "
            "See minions/gru/milestone_vote.py."
        ),
    )
    stagnation_vote_window_seconds: int = Field(
        default=1200,
        description=(
            "How long the project must be silent on Draft, main-branch shared-surface "
            "commits, and experiment runs before the stall breaker fires. "
            "Default 1200 s (20 min) — long enough that a deep run or "
            "review pass can finish without interruption, short enough to "
            "break the wait-for-each-other loops we observed in production."
        ),
    )
    stagnation_vote_cooldown_seconds: int = Field(
        default=1800,
        description=(
            "Minimum interval between two consecutive milestone-vote "
            "openings on the same project. Roles need at least one full "
            "wake cycle to read the request and respond before another "
            "vote arrives. Default 1800 s (30 min)."
        ),
    )
    parked_prompt_watchdog_enabled: bool = Field(
        default=True,
        description=(
            "Issue #29: Gru-side safety net that detects role panes parked at "
            "the input prompt (post-/compact failure mode) and sends a tmux "
            "kick. The post_compact_draft hook fires immediately; this "
            "watchdog catches the case where the hook itself fails (no tmux, "
            "race with TUI redraw, etc.). Set false to disable if your "
            "operator workflow uses /compact heavily and you trust the hook."
        ),
    )
    parked_prompt_watchdog_interval_seconds: int = Field(
        default=60,
        description=(
            "How often the parked-prompt watchdog ticks. Each tick runs "
            "tmux capture-pane on every active EACN role (cheap — bounded "
            "by 40 lines per role) and looks for the prompt-cursor signature."
        ),
    )
    parked_prompt_watchdog_min_age_seconds: int = Field(
        default=90,
        description=(
            "Minimum heartbeat staleness before a role's parked pane is "
            "considered a real wedge rather than a momentary between-turn "
            "render. Default 90 s. The post_compact_draft hook is expected "
            "to recover in ~2 s; this watchdog only fires if the hook "
            "failed for some reason."
        ),
    )
    wedge_watchdog_interval_seconds: int = Field(
        default=300,
        description=(
            "How often the wedge watchdog ticks. Each tick reads the tail "
            "of every active role's log file (cheap — bounded by "
            "wedge_watchdog_tail_bytes per role) and counts wedge markers. "
            "Default 300 (5 min)."
        ),
    )
    wedge_watchdog_threshold: int = Field(
        default=4,
        description=(
            "Minimum count of `[upstream returned no content]` OR bare `ack` "
            "lines in the recent log tail before the watchdog declares a "
            "role wedged. With the default tail of 16KB (roughly the last "
            "50-100 turn boundaries on a long-running role) and threshold 4, "
            "the watchdog needs four wedge-pattern turns AND at least one of "
            "the other pattern to act — keeping false positives on healthy "
            "cache-keepalive loops near zero."
        ),
    )
    wedge_watchdog_tail_bytes: int = Field(
        default=16384,
        description=(
            "How many bytes from the end of each role log to read per "
            "watchdog tick. The wedge signature is local to the recent "
            "turn boundaries, so a small fixed tail is sufficient and "
            "keeps the tick cheap on long-running projects."
        ),
    )
    wedge_watchdog_cooldown_seconds: int = Field(
        default=900,
        description=(
            "After the watchdog kills a role's tmux session, suppress "
            "further wedge-kills against that (port, role) for this many "
            "seconds. Gives the respawned role time to cold-start, rebuild "
            "context from the Draft, and emit non-`ack` output before the "
            "watchdog reads its log tail again. Default 900 (15 min)."
        ),
    )
    cache_keepalive_seconds: int = Field(
        default=240,
        description=(
            "Wall-clock seconds of silence after which mos_await_events returns "
            "a stable synthetic keepalive event so the Role's long-lived "
            "claude process re-touches its prompt cache before the TTL cliff. "
            "Default 240s (4 min) sits just under the 5-min cliff that every "
            "stock Claude Code binary uses; this is the safe value for production. "
            "MinionsOS sets ENABLE_PROMPT_CACHING_1H=1 in the Role env "
            "(role_launcher.py), but that flag is only honored when the "
            "Claude Code CLI binary has been patched to send ttl:'1h' + the "
            "extended-cache-ttl beta header (see ~/Tools/claude-1h-cache-patch/). "
            "Stock binaries on remote production hosts silently drop the env var "
            "and keep the 5-min cliff. Raise this to ~3000 ONLY on hosts where "
            "the patch is applied AND cache_stats confirms 1h TTL is in effect. "
            "Each keepalive costs ~$0.006 (cache_read of system prompt); missing "
            "the cliff costs ~$0.098 (cache_create), so always err on the side "
            "of *more* keepalive when cache TTL is uncertain. Set to 0 to "
            "disable entirely."
        ),
    )
    local_eacn_initial_balance: float = Field(
        default=10_000.0,
        description=(
            "Minimum local EACN credit balance ensured for Gru and registered project roles. "
            "MinionsOS still defaults project-local tasks to budget=0."
        ),
    )
    health_event_eacn_notifications: bool = Field(
        default=False,
        description=(
            "When true, Gru's health monitor also posts backend/role health events "
            "to the project-local Gru queue. Structured health events are "
            "always written to project logs regardless of this flag."
        ),
    )
    gru_eacn_agent_id: str = Field(
        default="gru",
        description=(
            "EACN agent_id used when system components (e.g. wakeup dispatcher) "
            "post messages to Gru."
        ),
    )
    claude_model: str = Field(
        default="claude-opus-4-8[1m]",
        description=(
            "Claude model name passed to the claude CLI. The `[1m]` suffix "
            "selects the 1M-context variant; without it the runtime falls back "
            "to the 200k window. Use `claude-opus-4-8` for the 200k variant."
        ),
    )
    role_ultracode: bool = Field(
        default=True,
        description=(
            "Launch every long-lived Role process with the Claude Code "
            "`ultracode` session setting (xhigh reasoning effort + standing "
            "dynamic-workflow orchestration). Wired via `--settings "
            "'{\"ultracode\": true}'' in agent_host (NOT `--effort ultracode`; "
            "the CLI rejects that value — valid --effort levels are "
            "low/medium/high/xhigh/max). Per-process override: env "
            "MINIONS_ROLE_ULTRACODE=0/1. Set false to revert roles to the "
            "model's plain default effort."
        ),
    )
    fallback_model: str | None = Field(
        default="claude-sonnet-4-6[1m]",
        description=(
            "Fallback model passed to `claude --fallback-model` for the "
            "one-shot `--print` spawn site `mos_review_run` (paper review). "
            "Claude Code 2.1.152 documents `--fallback-model` as `--print`-only; "
            "long-lived interactive Role processes ignore it and rely on the Gru "
            "watchdog instead. Set to None to disable. Per-call override: "
            "MOS_REVIEW_FALLBACK_MODEL."
        ),
    )
    review_timeout_seconds: int = Field(
        default=3600,
        description=(
            "Wall-clock cap (seconds) for one `mos_review_run` round. The "
            "Area-Chair drives the whole round inside a single `claude "
            "--print` subprocess, fanning reviewer instances out as "
            "concurrent foreground Task subagents, so this bounds the entire "
            "round (≈ slowest reviewer + consolidation). Default 3600 s "
            "(1 h). Env override: MOS_REVIEW_TIMEOUT."
        ),
    )
    review_ultracode: bool = Field(
        default=True,
        description=(
            "Launch the `mos_review_run` Area-Chair subprocess with the "
            "Claude Code `ultracode` session setting (xhigh reasoning effort + "
            "standing dynamic-orchestration posture), mirroring role_ultracode "
            'for long-lived Roles. Wired via `--settings \'{"ultracode": '
            "true}'`. The Area-Chair fans reviewers out as concurrent "
            "foreground Task subagents — the `Workflow` tool is intentionally "
            "NOT exposed, since a `--print` turn ends before a backgrounded "
            "workflow completes. Env override: MOS_REVIEW_ULTRACODE=0/1."
        ),
    )
    _KNOWN_MODELS: frozenset[str] = frozenset(
        {
            "claude-opus-4-8",
            "claude-opus-4-8[1m]",
            "claude-opus-4-7",
            "claude-opus-4-7[1m]",
            "claude-sonnet-4-6",
            "claude-sonnet-4-6[1m]",
            "claude-haiku-4-5-20251001",
        }
    )

    def model_registry_valid(self) -> tuple[bool, str]:
        """Return (ok, detail) for the configured Claude model registry.

        Claude Code is the only agent host. The model name must be in the
        known-models set.
        """
        if self.claude_model in self._KNOWN_MODELS:
            return True, f"{self.claude_model} is a known model"
        known = ", ".join(sorted(self._KNOWN_MODELS))
        return False, f"{self.claude_model!r} not in known models ({known})"

    def effective_agent_host(self) -> Literal["claude"]:
        """Return the agent host. Claude Code is the only supported host.

        Retained as a method (rather than inlining ``"claude"`` at call sites)
        so the doctor / config-dump surfaces keep a stable accessor.
        """
        return "claude"

    # --- Context-window size thresholds (as fractions of the model context window) ---
    # Rationale: Context Rot / NoLiMa research shows effective context degrades
    # long before the nominal window is full, so we budget the agent's transcript
    # as a percentage of the window rather than as an absolute token count. This
    # lets thresholds auto-scale with the underlying model.
    #
    # NOTE: These are unrelated to the L1 Draft on disk
    # (``branches/main/draft/draft.json``). The ``context_*_pct``
    # names refer to the in-process transcript / context window of the
    # agent-host model.
    model_context_window_tokens: int = Field(
        default=1_000_000,
        description="Assumed context-window size of the underlying agent-host model (tokens).",
    )
    context_soft_pct: float = Field(
        default=0.10,
        description="Soft threshold (gentle compression hint on wake-up).",
    )
    context_hard_pct: float = Field(
        default=0.15,
        description="Hard threshold (require compression before processing new events).",
    )
    context_veto_pct: float = Field(
        default=0.20,
        description=(
            "Veto threshold (block normal event handling, attempt maintenance compaction, "
            "and alert Gru)."
        ),
    )

    # --- Context-pressure advisory thresholds (cache_read tokens/turn) ---
    # These drive the compaction ADVISORY surfaced by mos_await_events
    # (minions/tools/context_pressure.py), measured as cache_read tokens per
    # turn averaged over the recent window. Distinct from context_*_pct above
    # (which are an unrelated, currently-unwired percentage-of-window scheme).
    #
    # Revised 2026-05-30: the old 70K/100K hardcoded defaults fired "medium"
    # at 77K cr/turn — far too eager on a 1M-context model. A role would
    # propose compacting (discarding a warm prefix) mid-task to save cents.
    # New default keeps the full 1M window and only advises compaction once
    # the transcript is genuinely large. Operator/TUI-settable via
    # `mos config set context_pressure_high_tokens <n>`; per-process override
    # via MINIONS_CTX_PRESSURE_{HIGH,MEDIUM}_TOKENS.
    context_pressure_high_tokens: int = Field(
        default=200_000,
        description=(
            "Context-pressure HIGH threshold (cache_read tokens/turn). At/above "
            "this the role is told to compact now. Default 200K — only fires "
            "when the transcript is genuinely large; the 1M window is preserved."
        ),
    )
    context_pressure_medium_tokens: int = Field(
        default=150_000,
        description=(
            "Context-pressure MEDIUM threshold (cache_read tokens/turn). At/above "
            "this the role gets a soft 'consider compacting after current work' "
            "hint. Must be < context_pressure_high_tokens. Default 150K."
        ),
    )

    @field_validator(
        "heartbeat_report_interval",
        mode="before",
    )
    @classmethod
    def _valid_duration(cls, v: object) -> object:
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            parse_duration(v)  # raises ConfigError on bad input
            return v
        raise ValueError(f"heartbeat_report_interval must be str or int, got {type(v).__name__}")

    @field_validator(
        "backend_crash_threshold",
        "role_crash_threshold",
        "crash_window_seconds",
        "experiment_reconcile_interval_seconds",
        mode="before",
    )
    @classmethod
    def _positive_int(cls, v: object) -> object:
        if isinstance(v, int) and v <= 0:
            raise ValueError("Must be a positive integer.")
        return v


# ---------------------------------------------------------------------------
# experiment_targets.yaml model
# ---------------------------------------------------------------------------


class LocalTarget(BaseModel):
    id: str
    type: Literal["local"]
    workdir: str = "./experiments"


class SSHTarget(BaseModel):
    id: str
    type: Literal["ssh"]
    host: str
    key: str
    workdir: str = "/data/exp"


ExperimentTarget = LocalTarget | SSHTarget


class ExperimentTargetsConfig(BaseModel):
    """Settings loaded from ``minions/config/experiment_targets.yaml``."""

    targets: list[ExperimentTarget] = Field(default_factory=list)

    def get_target(self, target_id: str) -> ExperimentTarget:
        """Return the target with *target_id*, raising ``ConfigError`` if absent."""
        for t in self.targets:
            if t.id == target_id:
                return t
        raise ConfigError(f"Unknown experiment target: {target_id!r}")

    def active_targets(self) -> list[ExperimentTarget]:
        """Return targets actually used by the scheduler and ``target_id='auto'``.

        Rule: if any SSH target is configured, only SSH targets are active and
        local targets are ignored. Otherwise local targets are active. Mixing
        local and SSH in the same fleet is not supported on purpose — when SSH
        is configured we assume the local box has no usable GPU.
        """
        ssh: list[ExperimentTarget] = [t for t in self.targets if isinstance(t, SSHTarget)]
        if ssh:
            return ssh
        local: list[ExperimentTarget] = [t for t in self.targets if isinstance(t, LocalTarget)]
        return local


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning an empty dict if the file does not exist."""
    if not path.exists():
        logger.debug("Config file not found, using defaults: %s", path)
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"Expected a YAML mapping in {path}, got {type(data).__name__}.")
        return data
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {path}: {exc}") from exc


def _config_path(config_dir: Path | None, filename: str) -> Path:
    """Resolve config path from a directory or direct YAML file path."""
    if config_dir is None:
        return CONFIG_DIR / filename
    path = Path(config_dir)
    if path.name == filename or path.suffix.lower() in {".yaml", ".yml"}:
        return path
    return path / filename


def load_gru_config(config_dir: Path | None = None) -> GruConfig:
    """Load and validate ``gru.yaml``, falling back to defaults if absent.

    Args:
        config_dir: Override the default ``minions/config/`` directory.
    """
    path = _config_path(config_dir, "gru.yaml")
    data = _load_yaml(path)
    try:
        return GruConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid gru.yaml: {exc}") from exc


def pin_effective_agent_host(config_dir: Path | None = None) -> Literal["claude"]:
    """Pin the agent host in the process environment.

    Claude Code is the only supported host. Gru, the monitor sidecar, MCP
    servers, and role wakeups all inherit ``MINIONS_AGENT_HOST=claude`` so the
    sidecar host-marker check (``_common.py``) stays stable.
    """
    del config_dir  # retained for call-site compatibility; host is constant
    os.environ["MINIONS_AGENT_HOST"] = "claude"
    return "claude"


def load_experiment_targets(config_dir: Path | None = None) -> ExperimentTargetsConfig:
    """Load and validate ``experiment_targets.yaml``, falling back to defaults.

    Args:
        config_dir: Override the default ``minions/config/`` directory.
    """
    path = _config_path(config_dir, "experiment_targets.yaml")
    data = _load_yaml(path)
    try:
        return ExperimentTargetsConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid experiment_targets.yaml: {exc}") from exc
