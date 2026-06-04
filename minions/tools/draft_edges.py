"""Draft edge operations — creation and relation management.

Extracted from draft.py to isolate edge-specific logic.
"""

from __future__ import annotations

import logging
from typing import Any

from minions.errors import DraftError
from minions.tools.draft_helpers import (
    append_journal,
    env_role,
    load_draft,
    save_draft,
)

logger = logging.getLogger(__name__)

# Suggested edge relations
EDGE_RELATIONS = (
    "refines",
    "tests",
    "supports",
    "contradicts",
    "depends_on",
    "derived_from",
    "supersedes",
    "cites",
    "blocks",
)


def create_edges(
    port: int,
    edges: list[dict[str, Any]],
    timestamp: str,
    batch_author: str = "",
) -> int:
    """Create new edges and return count created.

    This is the core edge-creation logic extracted from mos_draft_append.
    """
    draft = load_draft(port)
    created_edge_count = 0

    for edge in edges:
        relation = edge.get("relation", "related_to")
        if relation not in EDGE_RELATIONS:
            logger.info("Custom edge relation: %s (not in suggested relations)", relation)
        strength = edge.get("strength", 1.0)
        if not (0.0 <= strength <= 1.0):
            raise DraftError(f"Edge strength must be 0.0-1.0, got {strength}")
        new_edge = {
            "from_id": edge["from_id"],
            "to_id": edge["to_id"],
            "relation": relation,
            "strength": strength,
            "created_at": edge.get("created_at", timestamp),
            "author_role": edge.get("author_role", "") or batch_author,
        }
        draft["edges"].append(new_edge)
        created_edge_count += 1
        append_journal(
            port,
            {
                "op": "add_edge",
                "edge": new_edge,
                "timestamp": timestamp,
                "author_role": new_edge["author_role"],
            },
        )

    save_draft(port, draft)
    return created_edge_count


def support_balance(node_id: str, edges: list[dict]) -> tuple[int, int]:
    """Count literal supports / contradicts edges incident to node_id.

    Kept for decay sidecar display fields and pinned-count tests.
    The confidence math uses the broader relation_weights.
    """
    supports = 0
    contradicts = 0
    for edge in edges:
        if edge.get("from_id") != node_id and edge.get("to_id") != node_id:
            continue
        rel = str(edge.get("relation", ""))
        if rel == "supports":
            supports += 1
        elif rel == "contradicts":
            contradicts += 1
    return supports, contradicts


# P4 (2026-05-29 audit): relation decay weight map
_REINFORCE = "reinforce"
_ACCELERATE = "accelerate"
RELATION_DECAY_WEIGHT: dict[str, tuple[str, float]] = {
    # Strong corroboration
    "supports": (_REINFORCE, 1.0),
    "verifies": (_REINFORCE, 1.0),
    "verified_by": (_REINFORCE, 1.0),
    "reaffirms": (_REINFORCE, 1.0),
    "ratifies": (_REINFORCE, 1.0),
    "corroborates": (_REINFORCE, 1.0),
    "concurs_with": (_REINFORCE, 0.8),
    "endorses": (_REINFORCE, 0.8),
    "strengthens": (_REINFORCE, 0.8),
    "partially_corroborates": (_REINFORCE, 0.5),
    "reviews": (_REINFORCE, 0.5),
    # Lifecycle progress
    "resolves": (_REINFORCE, 0.6),
    "resolves_open_ask": (_REINFORCE, 0.6),
    "closes_acceptance": (_REINFORCE, 0.6),
    "completes": (_REINFORCE, 0.6),
    "delivers": (_REINFORCE, 0.6),
    "delivers_phase2_followup_for": (_REINFORCE, 0.6),
    "elevates": (_REINFORCE, 0.6),
    "anchors": (_REINFORCE, 0.5),
    "preserves": (_REINFORCE, 0.5),
    "polishes": (_REINFORCE, 0.3),
    # Structural / navigational
    "refines": (_REINFORCE, 0.3),
    "tests": (_REINFORCE, 0.3),
    "implements": (_REINFORCE, 0.3),
    "instantiates": (_REINFORCE, 0.3),
    "extends": (_REINFORCE, 0.3),
    "elaborated_by": (_REINFORCE, 0.3),
    "responds_to": (_REINFORCE, 0.3),
    "reviews_for": (_REINFORCE, 0.3),
    "depends_on": (_REINFORCE, 0.2),
    "derived_from": (_REINFORCE, 0.2),
    "follows": (_REINFORCE, 0.2),
    "related_to": (_REINFORCE, 0.2),
    "references": (_REINFORCE, 0.2),
    "cites": (_REINFORCE, 0.2),
    "uses": (_REINFORCE, 0.2),
    "observes": (_REINFORCE, 0.2),
    "qualifies": (_REINFORCE, 0.2),
    # Negative / deprecating
    "contradicts": (_ACCELERATE, 1.0),
    "supersedes": (_ACCELERATE, 1.0),
    "supersedes_naming": (_ACCELERATE, 0.6),
    "supersedes_runtime": (_ACCELERATE, 1.0),
    "supersedes_action": (_ACCELERATE, 1.0),
    "absorbs": (_ACCELERATE, 0.8),
    "deferred_from": (_ACCELERATE, 0.4),
    "blocks": (_ACCELERATE, 0.4),
}
_RELATION_UNKNOWN_REINFORCE = 0.1


def relation_weights(node_id: str, edges: list[dict]) -> tuple[float, float]:
    """Sum reinforce / accelerate weights over ALL edges incident to node_id.

    Directed relations that deprecate their target (supersedes, absorbs)
    accelerate decay only on the to_id endpoint. Symmetric relations apply
    to both endpoints.
    """
    _TARGET_ONLY_ACCELERATORS = {
        "supersedes",
        "supersedes_naming",
        "supersedes_runtime",
        "supersedes_action",
        "absorbs",
        "deferred_from",
        "blocks",
    }
    reinforce = 0.0
    accelerate = 0.0
    for edge in edges:
        is_from = edge.get("from_id") == node_id
        is_to = edge.get("to_id") == node_id
        if not is_from and not is_to:
            continue
        rel = str(edge.get("relation", ""))
        mapped = RELATION_DECAY_WEIGHT.get(rel)
        if mapped is None:
            reinforce += _RELATION_UNKNOWN_REINFORCE
            continue
        kind, weight = mapped
        if kind == _ACCELERATE:
            # Directed deprecation ages only the deprecated (to_id) endpoint
            if rel in _TARGET_ONLY_ACCELERATORS and not is_to:
                continue
            accelerate += weight
        else:
            reinforce += weight
    return reinforce, accelerate
