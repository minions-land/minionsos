"""Draft confidence decay calculations.

Extracted from draft.py to isolate decay logic.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import UTC, datetime
from typing import Any

from minions.tools.draft_edges import relation_weights, support_balance
from minions.tools.draft_helpers import (
    decay_path,
    env_port,
    load_draft,
    now_iso,
    parse_iso,
)

logger = logging.getLogger(__name__)

# Confidence decay half-lives in days, by node type
DECAY_HALF_LIFE_DAYS: dict[str, float] = {
    "hypothesis": 30.0,
    "question": 30.0,
    "assumption": 60.0,
    "experiment": 60.0,
    "result": 90.0,
    "citation": 365.0,
    "decision": 180.0,
    "dead_end": 365.0,
    "insight": 120.0,
    "method": 180.0,
    "bootstrap": 9999.0,
}
DECAY_HALF_LIFE_DEFAULT = 60.0
DECAY_FLOOR = 0.05


def effective_confidence(
    stored: float,
    node_type: str,
    age_days: float,
    supports: float,
    contradicts: float,
) -> float:
    """Compute effective_confidence from stored confidence, age, and topology.

    Pure function — no IO, no LLM. supports is the summed reinforcement
    weight; contradicts is the summed acceleration weight. Ebbinghaus pattern:
    decay is exponential with half-life by type, reinforcement rolls back
    the clock.
    """
    half_life = DECAY_HALF_LIFE_DAYS.get(node_type, DECAY_HALF_LIFE_DEFAULT)
    reinforced_age = max(0.0, age_days - 0.5 * half_life * supports)
    accelerated_age = reinforced_age + 0.5 * half_life * contradicts
    decay_factor = math.pow(0.5, accelerated_age / half_life)
    raw = float(stored) * decay_factor
    return max(DECAY_FLOOR * float(stored), raw)


def mos_draft_decay_compute() -> dict[str, Any]:
    """Compute decay sidecar at draft/decay.json.

    Pure observation: walks every node, records age, support/contradicts edge
    counts, and effective_confidence. Does not mutate any node.

    Whitelisted to Ethics and Gru. Other roles read decay through
    mos_draft_summary (which joins the sidecar when present).
    Returns a dict with totals + the path of the written sidecar.
    """
    port = env_port()
    draft = load_draft(port)
    nodes = draft["nodes"]
    edges = draft["edges"]
    now = datetime.now(UTC)
    out: dict[str, Any] = {}
    for node in nodes:
        node_id = node.get("id", "")
        if not node_id:
            continue
        created = parse_iso(node.get("created_at", ""))
        age_days = 0.0 if created is None else max(0.0, (now - created).total_seconds() / 86400.0)
        supports, contradicts = support_balance(node_id, edges)
        reinforce, accelerate = relation_weights(node_id, edges)
        eff = effective_confidence(
            stored=float(node.get("confidence", 1.0) or 0.0),
            node_type=str(node.get("type", "")),
            age_days=age_days,
            supports=reinforce,
            contradicts=accelerate,
        )
        out[node_id] = {
            "age_days": round(age_days, 2),
            "supports": supports,
            "contradicts": contradicts,
            "reinforce": round(reinforce, 3),
            "accelerate": round(accelerate, 3),
            "stored_confidence": float(node.get("confidence", 1.0) or 0.0),
            "effective_confidence": round(eff, 3),
        }
    path = decay_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = {"computed_at": now_iso(), "nodes": out}
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return {
        "computed_at": payload["computed_at"],
        "node_count": len(out),
        "path": str(path),
    }
