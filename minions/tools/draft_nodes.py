"""Draft node operations — creation, updates, and ID generation.

Extracted from draft.py to isolate node-specific logic.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, get_args

from minions.tools.draft_helpers import (
    append_journal,
    env_reel_context,
    env_role,
    load_draft,
    now_iso,
    save_draft,
    validate_confidence,
)

logger = logging.getLogger(__name__)

# Canonical node types
DraftNodeType = Literal[
    "hypothesis",
    "question",
    "assumption",
    "experiment",
    "result",
    "citation",
    "decision",
    "dead_end",
    "insight",
    "method",
    "bootstrap",
]
NODE_TYPES: tuple[str, ...] = get_args(DraftNodeType)

# Canonical support statuses
DraftSupportStatus = Literal[
    "unverified",
    "tentative",
    "verified",
    "refuted",
    "blocked",
    "out_of_scope",
]
SUPPORT_STATUSES: tuple[str, ...] = get_args(DraftSupportStatus)

# Canonical provenance labels
DraftProvenance = Literal[
    "extracted",
    "inferred",
    "speculative",
]
PROVENANCES: tuple[str, ...] = get_args(DraftProvenance)

# Type prefixes for ID generation
TYPE_PREFIX: dict[str, str] = {
    "hypothesis": "H",
    "question": "Q",
    "assumption": "A",
    "experiment": "E",
    "result": "R",
    "citation": "C",
    "decision": "D",
    "dead_end": "DEAD",
    "insight": "I",
    "method": "M",
    "bootstrap": "B",
}

# Motif kinds for Ethics-authored integration claims
MOTIF_KINDS = ("triangle", "star", "cycle", "close", "none")

# Node types for which Ethics must supply motif_kind (soft enforcement)
CURATOR_MOTIF_REQUIRED_TYPES = frozenset({"result", "decision", "hypothesis", "insight"})


def next_id(draft: dict[str, Any], node_type: str) -> str:
    """Generate next available ID for a given node type."""
    prefix = TYPE_PREFIX.get(node_type, node_type[:3].upper())
    existing_nums: list[int] = []
    for node in draft["nodes"]:
        nid: str = node.get("id", "")
        if nid.startswith(prefix + "-"):
            suffix = nid[len(prefix) + 1 :]
            if suffix.isdigit():
                existing_nums.append(int(suffix))
    next_num = max(existing_nums, default=0) + 1
    return f"{prefix}-{next_num:03d}"


def create_nodes(
    port: int,
    nodes: list[dict[str, Any]],
    timestamp: str,
) -> list[str]:
    """Create new nodes and return their IDs.

    This is the core node-creation logic extracted from mos_draft_append.
    """
    draft = load_draft(port)
    created_node_ids: list[str] = []

    for node in nodes:
        ntype = node.get("type", "hypothesis")
        if ntype not in NODE_TYPES:
            logger.info("Custom node type: %s (not in suggested types)", ntype)
        provenance = node.get("provenance", "extracted")
        if provenance not in PROVENANCES:
            logger.info("Custom provenance: %s (not in suggested provenances)", provenance)
        confidence = validate_confidence(node.get("confidence", 1.0))
        node_id = node.get("id") or next_id(draft, ntype)

        # Auto-inject reel_ref into metadata if available and not already set
        node_metadata = dict(node.get("metadata", {}))
        if "reel_ref" not in node_metadata:
            reel_ctx = env_reel_context()
            if reel_ctx:
                node_metadata["reel_ref"] = reel_ctx

        # Motif contract enforcement for curator (Ethics) nodes
        author_role = node.get("author_role", "") or env_role()
        if author_role == "ethics" and ntype in CURATOR_MOTIF_REQUIRED_TYPES:
            motif_kind = node_metadata.get("motif_kind")
            if not motif_kind:
                logger.warning(
                    "ethics appending %s node '%s' without motif_kind — "
                    "prefer mos_draft_annotate to update existing nodes instead",
                    ntype,
                    node.get("id", "<new>"),
                )
                node_metadata["warning"] = "ethics_node_without_motif_kind"
            elif motif_kind == "none":
                logger.warning(
                    "ethics appending %s node with motif_kind='none' — "
                    "mos_draft_annotate would be preferred for status updates",
                    ntype,
                )

        new_node = {
            "id": node_id,
            "type": ntype,
            "text": node.get("text", ""),
            "support_status": node.get("support_status", "unverified"),
            "author_role": node.get("author_role", "") or env_role(),
            "created_at": node.get("created_at", timestamp),
            "evidence_tag": node.get("evidence_tag", ""),
            "provenance": provenance,
            "confidence": confidence,
            "metadata": node_metadata,
        }
        draft["nodes"].append(new_node)
        created_node_ids.append(node_id)
        append_journal(
            port,
            {
                "op": "add_node",
                "node": new_node,
                "timestamp": timestamp,
                "author_role": new_node["author_role"],
            },
        )

    save_draft(port, draft)
    return created_node_ids


def resolve_pending_plans(
    port: int,
    pending_ids: list[str],
    replaced_by: list[str],
    timestamp: str,
) -> list[str]:
    """Remove pending plan nodes that have been replaced by real nodes.

    Returns list of actually resolved node IDs.
    """
    draft = load_draft(port)
    nodes_by_id = {n["id"]: n for n in draft["nodes"]}
    removable: set[str] = set()

    for pid in pending_ids:
        target = nodes_by_id.get(pid)
        if target is None:
            logger.info("resolves_pending: node %s not found; skipping", pid)
            continue
        if (target.get("metadata") or {}).get("pending_plan") is not True:
            logger.warning(
                "resolves_pending: node %s is not a pending plan "
                "(no metadata.pending_plan); refusing to remove a landed imprint",
                pid,
            )
            continue
        removable.add(pid)

    if removable:
        draft["nodes"] = [n for n in draft["nodes"] if n["id"] not in removable]
        draft["edges"] = [
            e
            for e in draft["edges"]
            if e["from_id"] not in removable and e["to_id"] not in removable
        ]
        resolved_plan_ids = sorted(removable)
        for pid in resolved_plan_ids:
            append_journal(
                port,
                {
                    "op": "resolve_pending",
                    "node_id": pid,
                    "replaced_by": replaced_by,
                    "timestamp": timestamp,
                    "author_role": env_role(),
                },
            )
        save_draft(port, draft)
        return resolved_plan_ids

    return []
