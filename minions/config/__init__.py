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
from typing import Literal, cast

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

_CODEX_BRIDGE_TOOLS = [
    "codex",
]

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
# ``mos_draft_commit_shared`` is reserved for Noter/Gru — committing the
# Draft is a curator action, not a per-role one.
_DRAFT_RW_TOOLS = [
    "mos_draft_annotate",
    "mos_draft_append",
    "mos_draft_path",
    "mos_draft_query",
    "mos_draft_summary",
]

_BOOK_READ_TOOLS = [
    "mos_book_query",
    "mos_book_hot_get",
]

# Book synthesis-write tool: any role can save its own question→answer
# synthesis as a compounding Book page (Wiki V2 W7). Mechanical write —
# the role brings the synthesis, this tool only persists it.
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

# Visual format-check tools. Format-agnostic detectors over rendered PDF page
# images (column voids, edge overflow, trailing whitespace, column imbalance,
# float clustering, short lines). Whitelisted to every EACN-visible main role
# so Writer can verify paper PDFs, Coder can inspect generated figures/plots,
# Ethics can audit figure-quality claims, and Experts can spot-check visuals.
# Noter is excluded — it is human-facing and does not run detectors.
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

# Read-only graphify MCP tools — Atlas (L3) primitives over branches/shared/.
# ``graphify`` is the underlying third-party Python library that backs the Atlas
# layer; the package keyword and tool prefix stay ``graphify`` deliberately to
# preserve the upstream import path. Built by Noter periodic, served by
# mcp-servers/graphify/launcher.sh. Whitelisted universally because every read
# is non-destructive; Noter is the only writer.
_GRAPHIFY_READ_TOOLS = [
    "mcp__graphify__query_graph",
    "mcp__graphify__get_node",
    "mcp__graphify__get_neighbors",
    "mcp__graphify__get_community",
    "mcp__graphify__god_nodes",
    "mcp__graphify__graph_stats",
    "mcp__graphify__shortest_path",
]

_SHELF_GRU_TOOLS = [
    "mos_shelf_query",
    "mos_shelf_shared_concepts",
]

_SHELF_REGISTER_TOOLS = [
    "mos_shelf_register",
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
# Noter is excluded from unification because it runs on a different model
# (Sonnet) and therefore occupies a separate cache namespace anyway.

_EACN_ROLE_MAIN_TOOLS: list[str] = [
    *_KEEPALIVE_TOOLS,
    *_ISSUE_REPORT_TOOLS,
    # EACN communication (all EACN roles)
    "eacn3_*",
    "mos_await_events",
    "mos_get_events",
    "mos_unread_summary",
    # Draft (full access including commit for Gru/Noter)
    "mos_draft_*",
    # Book
    *_BOOK_READ_TOOLS,
    "mos_book_ingest",
    "mos_book_ingest_batch",
    "mos_book_lint",
    "mos_book_hot_update",
    "mos_book_promote_verified",
    "mos_book_crystallize_session",
    # Book synthesis-write (compounding queries; any role can save its
    # own synthesis as a Book page).
    *_BOOK_SYNTHESIS_WRITE_TOOLS,
    # Book audit tools (Ethics/Gru-only at server side; appear in CLI
    # whitelist for KV cache parity).
    *_BOOK_AUDIT_TOOLS,
    # Graphify read (Atlas primitives)
    *_GRAPHIFY_READ_TOOLS,
    # Atlas (Gru queries only; register is Noter-only)
    *_SHELF_GRU_TOOLS,
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
    "mos_start_monitor",
    # Experiment tools (Coder-only at server side)
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
    *_CODEX_BRIDGE_TOOLS,
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
    ("noter", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "mos_noter_wait",
        "mos_draft_*",
        "mos_book_ingest",
        "mos_book_ingest_batch",
        "mos_book_lint",
        "mos_book_hot_update",
        "mos_book_promote_verified",
        "mos_book_crystallize_session",
        *_BOOK_READ_TOOLS,
        *_GRAPHIFY_READ_TOOLS,
        *_SHELF_REGISTER_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        "WebSearch",
        "WebFetch",
        "Read",
    ],
    ("noter", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    ],
    ("coder", "main"): _EACN_ROLE_MAIN_TOOLS,
    ("coder", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_CODEX_BRIDGE_TOOLS,
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
    ("writer", "main"): _EACN_ROLE_MAIN_TOOLS,
    ("writer", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_CODEX_BRIDGE_TOOLS,
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
        *_CODEX_BRIDGE_TOOLS,
        *_PAPER_SEARCH_TOOLS,
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
        *_CODEX_BRIDGE_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    ],
}


def resolve_whitelist(role: str, agent_type: Literal["main", "subagent"] = "main") -> list[str]:
    """Return the allowed-tools list for *role* and *agent_type*.

    This is the **CLI-visible** whitelist used for ``--allowed-tools``. All
    EACN roles share the same unified list so their tool-definition blocks
    are byte-identical for cross-role KV cache sharing. Server-side authz
    (the real enforcement boundary) uses :func:`resolve_server_authz`.

    Expert roles are stored as ``expert-<slug>``; this function normalises
    them to ``expert`` before lookup. Removed roles (e.g. ``experimenter``)
    are resolved through ``_REMOVED_ROLE_ALIASES`` so old env vars degrade
    gracefully.

    Args:
        role: Role name, e.g. ``"noter"``, ``"expert-dl-arch"``.
        agent_type: ``"main"`` or ``"subagent"``.

    Returns:
        List of tool name patterns (may contain ``*`` wildcards).
    """
    normalised = "expert" if role == "expert" or role.startswith("expert-") else role
    normalised = _REMOVED_ROLE_ALIASES.get(normalised, normalised)
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
        "eacn3_*",
        "mos_get_events",
        "mos_unread_summary",
        "mos_draft_*",
        *_BOOK_READ_TOOLS,
        *_BOOK_SYNTHESIS_WRITE_TOOLS,  # Gru can materialize syntheses
        *_BOOK_AUDIT_TOOLS,  # Gru is the only role besides Ethics that audits
        *_GRAPHIFY_READ_TOOLS,
        *_SHELF_GRU_TOOLS,
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
        "mos_start_monitor",
        *_CODEX_BRIDGE_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Gru can read any role's reel
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
    ("noter", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "mos_noter_wait",
        "mos_draft_*",
        "mos_book_ingest",
        "mos_book_lint",
        "mos_book_ingest_batch",
        "mos_book_hot_update",
        "mos_book_promote_verified",
        "mos_book_crystallize_session",
        *_BOOK_SYNTHESIS_WRITE_TOOLS,  # Noter materializes role-supplied syntheses
        *_BOOK_READ_TOOLS,
        *_GRAPHIFY_READ_TOOLS,
        *_SHELF_REGISTER_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        "WebSearch",
        "WebFetch",
        "Read",
    ],
    ("noter", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Read",
        "Write",
        "Edit",
    ],
    ("coder", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "eacn3_*",
        "mos_await_events",
        *_DRAFT_RW_TOOLS,
        *_BOOK_READ_TOOLS,
        *_GRAPHIFY_READ_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        "mos_project_checkpoint_workspace",
        *_CODEX_BRIDGE_TOOLS,
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
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Coder can read own reel
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("coder", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_CODEX_BRIDGE_TOOLS,
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
    ("writer", "main"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        "eacn3_*",
        "mos_await_events",
        *_DRAFT_RW_TOOLS,
        *_BOOK_READ_TOOLS,
        *_GRAPHIFY_READ_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_reset_context",
        "mos_compact_context",
        *_PAPER_SEARCH_TOOLS,
        "Task",
        "mos_project_checkpoint_workspace",
        *_CODEX_BRIDGE_TOOLS,
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Writer can read own reel
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("writer", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_CODEX_BRIDGE_TOOLS,
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
        *_GRAPHIFY_READ_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        "mos_project_checkpoint_workspace",
        *_CODEX_BRIDGE_TOOLS,
        *_PAPER_SEARCH_TOOLS,
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Expert can read own reel
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
        *_CODEX_BRIDGE_TOOLS,
        *_PAPER_SEARCH_TOOLS,
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
        *_DRAFT_RW_TOOLS,
        *_BOOK_READ_TOOLS,
        *_BOOK_AUDIT_TOOLS,  # Ethics is the primary auditor
        "mos_book_lint",
        *_GRAPHIFY_READ_TOOLS,
        "mos_publish_to_shared",
        "mos_signboard_read",
        "mos_signboard_set",
        "mos_reset_context",
        "mos_compact_context",
        "Task",
        *_CODEX_BRIDGE_TOOLS,
        *_VISUAL_CHECK_TOOLS,
        *_REEL_TOOLS,  # Ethics can read own reel
        "WebSearch",
        "WebFetch",
        "Read",
    ],
    ("ethics", "subagent"): [
        *_KEEPALIVE_TOOLS,
        *_ISSUE_REPORT_TOOLS,
        *_CODEX_BRIDGE_TOOLS,
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
        role: Role name, e.g. ``"noter"``, ``"expert-dl-arch"``.
        agent_type: ``"main"`` or ``"subagent"``.

    Returns:
        List of tool name patterns (may contain ``*`` wildcards).
    """
    normalised = "expert" if role == "expert" or role.startswith("expert-") else role
    normalised = _REMOVED_ROLE_ALIASES.get(normalised, normalised)
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
    "noter": RoleType.human_side,
    "coder": RoleType.eacn_visible,
    "writer": RoleType.eacn_visible,
    "ethics": RoleType.eacn_visible,
    "expert": RoleType.eacn_visible,
}

# Legacy alias kept for backward-compat in tests/tools that still reference
# the removed Experimenter role by name.  Resolves to "coder" in whitelist
# lookups so old MINIONS_ROLE_NAME=experimenter env vars degrade gracefully.
_REMOVED_ROLE_ALIASES: dict[str, str] = {
    "experimenter": "coder",
}

ROLE_WRITE_BOUNDARIES: dict[str, list[str]] = {
    "gru": [
        "branches/main/",
        "branches/shared/<any>/ (via mos_publish_to_shared)",
    ],
    "noter": [
        "branches/noter/ (drafts)",
        "branches/shared/notes/ (via mos_publish_to_shared)",
        "branches/shared/handoffs/ (via mos_publish_to_shared)",
        "branches/shared/book/ (via mos_book_ingest + mos_book_hot_update)",
        "branches/shared/draft/draft.json (via mos_draft_commit_shared)",
    ],
    "coder": [
        "branches/coder/",
        "branches/shared/exp/ (via mos_publish_to_shared)",
        "branches/shared/handoffs/ (via mos_publish_to_shared)",
        "branches/shared/governance/signboard.json (via mos_signboard_set)",
    ],
    "writer": [
        "branches/writer/",
        "branches/shared/handoffs/ (via mos_publish_to_shared)",
        "branches/shared/governance/signboard.json (via mos_signboard_set)",
    ],
    "ethics": [
        "branches/ethics/",
        "branches/shared/ethics/ (via mos_publish_to_shared)",
        "branches/shared/handoffs/ (via mos_publish_to_shared)",
        "branches/shared/governance/signboard.json (via mos_signboard_set)",
    ],
    "expert": [
        "branches/<expert>/",
        "branches/shared/handoffs/ (via mos_publish_to_shared)",
        "branches/shared/governance/signboard.json (via mos_signboard_set)",
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
        description="Python-side Experimenter queue reconcile cadence in seconds.",
    )
    role_evolution_interval_seconds: int = Field(
        default=900,
        description=(
            "How often Gru evaluates whether any role should split or merge. "
            "Recommendations are always logged to "
            "branches/shared/governance/role_evolution.jsonl; whether they are "
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
    cache_keepalive_seconds: int = Field(
        default=240,
        description=(
            "Wall-clock seconds of silence after which mos_await_events returns "
            "a stable synthetic keepalive event so the Role's long-lived "
            "claude process re-touches its prompt cache before the TTL cliff. "
            "Empirical measurement on tok.fan gateway: cache reliably expires "
            "around 280s of silence (270s gap + processing delay). Default "
            "240s (4min) leaves a 60s safety margin before the 5-min cliff. "
            "Each keepalive costs ~$0.006 (cache_read of system prompt); "
            "missing the cliff costs ~$0.098 (cache_create of full prefix), "
            "a 16x penalty. Set to 0 to disable for backends with longer TTL "
            "(e.g. direct Anthropic API with ENABLE_PROMPT_CACHING_1H=1)."
        ),
    )
    noter_periodic_interval: str = Field(
        default="3m",
        description=(
            "Cadence at which Noter wakes to flush the buffered Exploration "
            "DAG to a single commit on the shared branch and to take stock "
            "of the team. Reports are published on a slower internal cadence "
            "(see noter_report_interval); DAG flushes happen on every "
            "periodic wake."
        ),
    )
    noter_report_interval: str = Field(
        default="30m",
        description=(
            "Target cadence for Noter staged report publishes. Noter compares "
            "the time since the last published report against this value on "
            "each periodic wake (see noter_periodic_interval) and only "
            "publishes a new report when the interval has elapsed."
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
            "to project-local Gru and Noter queues. Structured health events are "
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
        default="claude-sonnet-4-6",
        description="Claude model name passed to the claude CLI (e.g. claude-sonnet-4-6).",
    )
    noter_model: str = Field(
        default="sonnet",
        description=(
            "Model for the Noter role. Noter does summarization and DAG "
            "maintenance — Sonnet is sufficient and much cheaper than Opus."
        ),
    )
    agent_host: Literal["claude", "codex"] = Field(
        default="claude",
        description="Default agent host for Gru and role wakeups: claude or codex.",
    )
    codex_model: str | None = Field(
        default=None,
        description="Optional Codex model name. When unset, Codex CLI config/default is used.",
    )
    codex_sandbox: Literal["read-only", "workspace-write", "danger-full-access"] = Field(
        default="danger-full-access",
        description=(
            "Codex sandbox mode for role wakeups when bypass is disabled. "
            "Default is danger-full-access so non-interactive local automation "
            "does not depend on platform sandbox support."
        ),
    )
    codex_approval_policy: Literal["untrusted", "on-request", "never"] = Field(
        default="never",
        description="Codex approval policy for non-interactive role wakeups.",
    )
    codex_reasoning_effort: Literal["low", "medium", "high", "xhigh"] = Field(
        default="xhigh",
        description="Codex reasoning effort for Gru and role wakeups.",
    )
    codex_bypass_approvals_and_sandbox: bool = Field(
        default=True,
        description=(
            "Use Codex --dangerously-bypass-approvals-and-sandbox for role wakeups. "
            "Enabled by default for unattended MinionsOS role automation; disable only "
            "when the local Codex sandbox is known to work reliably."
        ),
    )

    _KNOWN_MODELS: frozenset[str] = frozenset(
        {
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        }
    )

    def model_registry_valid(self) -> tuple[bool, str]:
        """Return (ok, detail) for the configured model registry.

        Claude keeps the historical strict registry when explicitly selected.
        Codex model names are intentionally not hardcoded here; Codex CLI can
        use its own profile/config defaults when ``codex_model`` is unset.
        """
        if self.effective_agent_host() == "codex":
            model = self.codex_model or "<codex CLI default>"
            return True, f"codex host selected; model={model}; effort={self.codex_reasoning_effort}"
        if self.claude_model in self._KNOWN_MODELS:
            return True, f"{self.claude_model} is a known model"
        known = ", ".join(sorted(self._KNOWN_MODELS))
        return False, f"{self.claude_model!r} not in known models ({known})"

    def effective_agent_host(self) -> Literal["claude", "codex"]:
        """Return the configured host, allowing a process-local env override."""
        host = os.environ.get("MINIONS_AGENT_HOST", "").strip().lower() or self.agent_host
        if host not in {"claude", "codex"}:
            logger.warning(
                "Unknown MINIONS_AGENT_HOST=%r; falling back to configured agent_host=%s.",
                host,
                self.agent_host,
            )
            return self.agent_host
        return cast(Literal["claude", "codex"], host)

    # --- Context-window size thresholds (as fractions of the model context window) ---
    # Rationale: Context Rot / NoLiMa research shows effective context degrades
    # long before the nominal window is full, so we budget the agent's transcript
    # as a percentage of the window rather than as an absolute token count. This
    # lets thresholds auto-scale with the underlying model.
    #
    # NOTE: These are unrelated to the L1 Draft on disk
    # (``branches/shared/draft/draft.json``). The ``context_*_pct``
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

    @field_validator("agent_host", mode="before")
    @classmethod
    def _valid_agent_host(cls, v: object) -> object:
        if isinstance(v, str):
            value = v.strip().lower()
            if value in {"claude", "codex"}:
                return value
        raise ValueError(f"agent_host must be 'claude' or 'codex', got {v!r}")

    @field_validator(
        "heartbeat_report_interval",
        "noter_report_interval",
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


def pin_effective_agent_host(config_dir: Path | None = None) -> Literal["claude", "codex"]:
    """Resolve the current host once and pin it in the process environment.

    Gru, the monitor sidecar, MCP servers, and role wakeups all inherit process
    environment. Pinning prevents a long-running process from drifting between
    Claude and Codex because a config file changed after startup.
    """
    host = load_gru_config(config_dir).effective_agent_host()
    os.environ["MINIONS_AGENT_HOST"] = host
    return host


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
