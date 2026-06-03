"""Draft (L1) — project-level shared process graph for autonomous discovery.

Records hypotheses, experiments, results, dead ends, decisions, and their
relationships.  All roles read/write through these functions; the MCP
registration layer in ``mcp_server.py`` wraps them as tools.

Environment:
    MINIONS_PROJECT_PORT — identifies the project.

Storage:
    project_{port}/branches/main/draft/draft.json — canonical graph state.
    project_{port}/branches/main/draft/journal.jsonl   — append-only mutation log.

The Draft and journal live inside the cross-role shared worktree
(``branches/main/`` on branch ``minionsos/project-{port}-shared``) so
Draft history is auditable in git. ``mos_draft_append`` and
``mos_draft_annotate`` write to the working tree only; commits happen
on a cron through ``mos_draft_commit_shared``, which is owned by Ethics
(the memory curator) and flushes the buffered Draft state via
``mos_publish_to_shared`` (single commit per cron tick, message
"ethics: draft flush <ts>").
"""

from __future__ import annotations

import heapq
import json
import logging
import math
import os
import random
import tempfile
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast, get_args

from pydantic import Field, model_serializer

from minions.errors import DraftError
from minions.paths import project_shared_draft_json, project_shared_subdir
from minions.tools._returns import DictLikeBaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical node types. ``mos_draft_append`` still accepts free-form strings
# in dict inputs for backward compatibility (logs an info-level note when an
# unknown value is seen), but the Literal narrows the typed surfaces in
# ``mos_draft_query`` and the Pydantic MCP args.
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

# Canonical support statuses.
DraftSupportStatus = Literal[
    "unverified",
    "tentative",
    "verified",
    "refuted",
    "blocked",
    "out_of_scope",
]
SUPPORT_STATUSES: tuple[str, ...] = get_args(DraftSupportStatus)

# Canonical provenance labels.
DraftProvenance = Literal[
    "extracted",
    "inferred",
    "speculative",
]
PROVENANCES: tuple[str, ...] = get_args(DraftProvenance)
# extracted: from a cited source/artifact
# inferred: derived from prior nodes (low-medium confidence)
# speculative: agent's working hypothesis, not yet evidenced

# Confidence decay half-lives in days, by node type. effective_confidence is a
# computed field — it never overwrites the stored confidence and never persists
# to draft.json. Ethics computes a sidecar at decay.json on each periodic
# wake; this constant is the read-side reference.
#
# Picked deliberately: decisions and dead_ends should fade slowly (they
# represent commitments that other nodes depend on); hypotheses fade fast
# (an unverified hypothesis untouched for 30d is probably stale). See
# project_minionsos_internal_structure_first_principles for the rationale.
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
    "bootstrap": 9999.0,  # bootstrap is the project root; effectively never decays
}
DECAY_HALF_LIFE_DEFAULT = 60.0
# Floor — a stale node never decays below 5% of its stored confidence.
DECAY_FLOOR = 0.05

# Motif kinds for Ethics-authored integration claims.
# "none" means the node is NOT a motif claim (prefer mos_draft_annotate instead).
MOTIF_KINDS = ("triangle", "star", "cycle", "close", "none")

# Node types for which Ethics must supply motif_kind (soft enforcement).
_CURATOR_MOTIF_REQUIRED_TYPES = frozenset({"result", "decision", "hypothesis", "insight"})

BOOK_STATUS_HOOK_STATUSES = frozenset({"verified", "refuted", "dead_end"})
_BOOK_STATUS_EVENT_TARGET: ContextVar[dict[str, Any] | None] = ContextVar(
    "_BOOK_STATUS_EVENT_TARGET",
    default=None,
)

# Suggested edge relations. Agents may use any string.
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

# ---------------------------------------------------------------------------
# Typed return shapes
# ---------------------------------------------------------------------------


class DraftQueryResult(DictLikeBaseModel):
    """Result shape for ``mos_draft_query``.

    Surfaces matching nodes plus the edges that connect them. ``total_matched``
    is the count of matching nodes (after filters, before the ``limit`` slice
    or token-budget truncation). ``truncated`` is set to ``True`` only when
    the token budget forced node-list truncation; the field is omitted from
    the serialized wire payload when not truncated to preserve the original
    pre-typing dict shape.

    Field population:

    - ``related_to`` mode returns the connected subgraph for the given node id
      (filters are ignored).
    - Filter mode applies ``node_type`` / ``support_status`` / ``author_role``
      / ``text_contains`` and returns the matched nodes plus their incident
      edges.
    """

    nodes: list[dict[str, Any]] = Field(description="Matching Draft nodes.")
    edges: list[dict[str, Any]] = Field(description="Edges incident to matching nodes.")
    total_matched: int = Field(description="Count of matching nodes after limit slice.")
    truncated: bool | None = Field(
        default=None,
        description="True if token-budget truncation reduced the node count; omitted otherwise.",
    )

    @model_serializer(mode="wrap")
    def _serialize(self, handler):  # type: ignore[no-untyped-def]
        # Preserve the pre-typing wire shape: omit ``truncated`` when None so
        # callers do not see a new ``truncated: null`` key for non-truncated
        # results. ``total_matched`` and the lists always serialize.
        data = handler(self)
        if data.get("truncated") is None:
            data.pop("truncated", None)
        return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _draft_dir(port: int) -> Path:
    return project_shared_subdir(port, "draft")


def _draft_path(port: int) -> Path:
    return project_shared_draft_json(port)


def _journal_path(port: int) -> Path:
    return _draft_dir(port) / "journal.jsonl"


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise DraftError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _env_role() -> str:
    """Return the current role name from env, or empty string."""
    return os.environ.get("MINIONS_ROLE_NAME", "")


def _env_reel_context() -> str | None:
    """Return the current reel context as '<role>/<session_id>' or None.

    The reel context identifies the role's current session so that Draft
    nodes can carry a ``reel_ref`` pointer back to the raw transcripts that
    led to the node's creation. The full reel_ref includes a task_id, but
    that's set per-tool-call by the PostToolUse hook — at Draft-append time
    we only know role and session.

    Returns None if either MINIONS_ROLE_NAME or MINIONS_SESSION_ID is unset.
    """
    role = os.environ.get("MINIONS_ROLE_NAME", "").strip()
    session = os.environ.get("MINIONS_SESSION_ID", "").strip()
    if not role or not session:
        return None
    return f"{role}/{session}"


def _is_motif_authorized(node: dict[str, Any]) -> bool:
    """Return True if a curator node is authorized to exist as a first-class claim.

    A curator node is authorized when:
    - Ethics has ratified it (metadata.ratified_by == "ethics"), OR
    - It is explicitly NOT a motif claim (motif_kind == "none" means prefer annotate,
      but the node is still allowed — soft enforcement only).

    This is used by Stream 3's mos_book_ratify gate. Nodes without ratification
    are still written to Draft; this helper signals whether Book promotion is allowed.
    """
    meta = node.get("metadata") or {}
    if meta.get("ratified_by") == "ethics":
        return True
    motif_kind = meta.get("motif_kind", "none")
    # Any non-"none" motif kind is a legitimate integration claim (pending Ethics ratification)
    return motif_kind != "none"


def _load_draft(port: int) -> dict[str, Any]:
    path = _draft_path(port)
    if not path.exists():
        return {"project_port": port, "root_question": "", "nodes": [], "edges": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Corrupt draft.json would otherwise crash every Role op. Surface a
        # warning and fall back to an empty stub so the Role can keep operating;
        # the next _save_draft will rewrite the file with valid JSON.
        logger.warning(
            "draft.json corrupt for port %s (%s); falling back to empty stub",
            port,
            exc,
        )
        return {"project_port": port, "root_question": "", "nodes": [], "edges": []}


def _save_draft(port: int, draft: dict[str, Any]) -> None:
    path = _draft_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _append_journal(port: int, entry: dict[str, Any]) -> None:
    path = _journal_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _next_id(draft: dict[str, Any], node_type: str) -> str:
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


def _validate_confidence(confidence: Any) -> float:
    try:
        value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise DraftError(f"Node confidence must be a number, got {confidence!r}") from exc
    if not (0.0 <= value <= 1.0):
        raise DraftError(f"Node confidence must be 0.0-1.0, got {value}")
    return value


def _decay_path(port: int) -> Path:
    """Sidecar with effective_confidence per node, computed by Ethics."""
    return _draft_dir(port) / "decay.json"


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _support_balance(node_id: str, edges: list[dict]) -> tuple[int, int]:
    """Count literal supports / contradicts edges incident to node_id.

    Kept for the decay sidecar's human-facing ``supports``/``contradicts``
    display fields and the pinned-count tests. The *confidence math* uses the
    broader :func:`_relation_weights` (see P4 below).
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


# P4 (2026-05-29 audit): a live project's Draft carried 41 distinct edge
# relations, 61% used exactly once, yet decay only ever read ``supports`` and
# ``contradicts`` — the other ~40 relations were dead weight invisible to every
# algorithm. This closed-set map folds the open relation vocabulary onto two
# decay signals so every meaningful edge participates:
#   reinforce > 0 : an incident edge that should roll the decay clock back
#                   (corroboration, verification, completion, ratification).
#   accelerate > 0: an incident edge that should age the node faster
#                   (contradiction; or being superseded/absorbed/deprecated).
# Structural / navigational relations (refines, depends_on, cites, …) map to a
# small reinforce weight: a connected node is fresher than an orphan, but a
# bare link is weaker evidence than an explicit "supports". Unknown relations
# fall through to a tiny reinforce floor (presence of an edge ≠ zero signal).
_REINFORCE = "reinforce"
_ACCELERATE = "accelerate"
RELATION_DECAY_WEIGHT: dict[str, tuple[str, float]] = {
    # Strong corroboration — full reinforcement (parity with legacy supports=1).
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
    # Lifecycle progress — the node is being acted on / carried forward.
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
    # Structural / navigational — mild freshness from being connected.
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
    # Negative / deprecating — age the node faster (parity with contradicts=1).
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


def _relation_weights(node_id: str, edges: list[dict]) -> tuple[float, float]:
    """Sum reinforce / accelerate weights over ALL edges incident to node_id.

    A directed relation that deprecates its *target* (``supersedes``,
    ``absorbs``) accelerates decay only on the ``to_id`` endpoint — the
    superseding ``from_id`` node is not itself aged by it. Symmetric relations
    (``supports``, ``contradicts``, ``related_to``, …) apply to both endpoints,
    preserving the legacy behaviour exactly.
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
            # Directed deprecation ages only the deprecated (to_id) endpoint.
            if rel in _TARGET_ONLY_ACCELERATORS and not is_to:
                continue
            accelerate += weight
        else:
            reinforce += weight
    return reinforce, accelerate


def _effective_confidence(
    stored: float,
    node_type: str,
    age_days: float,
    supports: float,
    contradicts: float,
) -> float:
    """Compute effective_confidence from stored confidence, age, and topology.

    Pure function — no IO, no LLM. ``supports`` is the summed reinforcement
    weight (each unit resets ~half a half-life of elapsed age); ``contradicts``
    is the summed acceleration weight (each unit ages the node by ~half a
    half-life). Ebbinghaus pattern: decay is exponential with half-life by
    type, reinforcement effectively rolls back the clock. The parameters are
    floats since P4 — literal ``supports``/``contradicts`` edges still weigh
    1.0 each, so legacy integer-count behaviour is preserved exactly.
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
    counts, and effective_confidence. **Does not mutate any node** — Ethics is
    forbidden from making claims, so decay is reported, never enforced.

    The confidence math uses the full relation vocabulary via
    :func:`_relation_weights` (P4): every meaningful edge reinforces or
    accelerates, not just literal ``supports``/``contradicts``. The sidecar
    still reports the literal integer ``supports``/``contradicts`` counts for
    display, plus the summed ``reinforce``/``accelerate`` weights actually fed
    to the decay function.

    Whitelisted to Ethics and Gru. Other roles read decay through
    ``mos_draft_summary()`` (which joins the sidecar when present).
    Returns a dict with totals + the path of the written sidecar.
    """
    port = _env_port()
    draft = _load_draft(port)
    nodes = draft["nodes"]
    edges = draft["edges"]
    now = datetime.now(UTC)
    out: dict[str, Any] = {}
    for node in nodes:
        node_id = node.get("id", "")
        if not node_id:
            continue
        created = _parse_iso(node.get("created_at", ""))
        age_days = 0.0 if created is None else max(0.0, (now - created).total_seconds() / 86400.0)
        supports, contradicts = _support_balance(node_id, edges)
        reinforce, accelerate = _relation_weights(node_id, edges)
        eff = _effective_confidence(
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
    path = _decay_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = {"computed_at": _now_iso(), "nodes": out}
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return {
        "computed_at": payload["computed_at"],
        "node_count": len(out),
        "path": str(path),
    }


def _load_decay(port: int) -> dict[str, Any]:
    path = _decay_path(port)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    nodes = payload.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _emit_book_status_event(
    port: int,
    node_id: str,
    new_status: str,
    annotator: str,
) -> None:
    target = _BOOK_STATUS_EVENT_TARGET.get()
    if target is None or target.get("id") != node_id:
        draft = _load_draft(port)
        target = next(
            (node for node in draft["nodes"] if node.get("id") == node_id),
            {},
        )
    node_text = str(target.get("text", ""))
    node_type = str(target.get("type", ""))
    date_updated = _now_iso()
    blob = "\n".join(
        [
            "---",
            "type: hypothesis_status",
            f"draft_node_id: {node_id}",
            f"new_status: {new_status}",
            f"annotator_role: {annotator}",
            f"date_updated: {date_updated}",
            "page_kind: status_update",
            "---",
            f"# Hypothesis status update: {node_id}",
            "",
            f"**Node**: {node_id} ({node_type})",
            f"**New status**: {new_status}",
            f"**Text**: {node_text[:300]}",
            f"**Annotator**: {annotator}",
            f"**When**: {date_updated}",
            "",
            "Auto-generated by Phase 7 Draft↔Book hook.",
            "",
        ]
    )
    temp_path: Path | None = None
    try:
        temp_dir = project_shared_subdir(port, "ethics") / ".draft-status-events"
        temp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=temp_dir,
            prefix="draft-status-",
            suffix=".md",
        ) as temp_file:
            temp_file.write(blob)
            temp_path = Path(temp_file.name)

        from minions.tools.book import mos_book_ingest

        mos_book_ingest(
            src_path=str(temp_path),
            source_role="ethics",
            source_slug=(f"draft-status-{node_id.replace('-', '').lower()[:30]}-{new_status}"),
            title=f"Status update: {node_id} → {new_status}",
            port=port,
        )
    except Exception as exc:
        logger.warning(
            "book status event emission failed for node %s status %s: %s",
            node_id,
            new_status,
            exc,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("failed to remove book status temp file %s: %s", temp_path, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mos_draft_query(
    node_type: DraftNodeType | None = None,
    support_status: DraftSupportStatus | None = None,
    author_role: str | None = None,
    text_contains: str | None = None,
    related_to: str | None = None,
    limit: int = 50,
    max_tokens: int = 2000,
) -> DraftQueryResult:
    """Query the Draft. Returns matching nodes and their immediate edges.

    Returns a :class:`DraftQueryResult` (dict-like) carrying ``nodes``,
    ``edges``, ``total_matched``, and an optional ``truncated`` flag.
    """
    port = _env_port()
    draft = _load_draft(port)
    nodes: list[dict] = draft["nodes"]
    edges: list[dict] = draft["edges"]

    # If related_to is specified, return subgraph connected to that node.
    if related_to:
        connected_ids = {related_to}
        for edge in edges:
            if edge["from_id"] == related_to:
                connected_ids.add(edge["to_id"])
            elif edge["to_id"] == related_to:
                connected_ids.add(edge["from_id"])
        nodes = [n for n in nodes if n["id"] in connected_ids]
        edges = [e for e in edges if e["from_id"] in connected_ids or e["to_id"] in connected_ids]
    else:
        # Apply filters.
        if node_type:
            nodes = [n for n in nodes if n.get("type") == node_type]
        if support_status:
            nodes = [n for n in nodes if n.get("support_status") == support_status]
        if author_role:
            nodes = [n for n in nodes if n.get("author_role") == author_role]
        if text_contains:
            lc = text_contains.lower()
            nodes = [n for n in nodes if lc in n.get("text", "").lower()]

        # Filter edges to only those connecting matched nodes.
        matched_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["from_id"] in matched_ids or e["to_id"] in matched_ids]

    nodes = nodes[:limit]
    # Token budget estimation: ~50 tokens/node, ~30 tokens/edge.
    est_tokens = len(nodes) * 50 + len(edges) * 30
    truncated = False
    if est_tokens > max_tokens:
        # Reduce nodes to fit budget (edges scale with nodes).
        max_nodes = max(1, (max_tokens - len(edges) * 30) // 50)
        nodes = nodes[:max_nodes]
        truncated = True
    return DraftQueryResult(
        nodes=nodes,
        edges=edges,
        total_matched=len(nodes),
        truncated=True if truncated else None,
    )


# Claim-bearing node types: only these "should" eventually carry an
# evidence_tag. Plans / questions / context legitimately have none, so
# excluding them keeps the unmarked-ratio signal from firing on node types
# that are not assertions. Reuses the curator-motif claim set.
_CLAIM_NODE_TYPES = _CURATOR_MOTIF_REQUIRED_TYPES  # {result, decision, hypothesis, insight}


def _role_unmarked_ratio(
    nodes: list[dict[str, Any]], author_role: str, *, min_nodes: int = 3
) -> float | None:
    """Fraction of a role's claim-bearing Draft nodes whose ``evidence_tag`` is empty.

    Pure (no I/O), so it is trivially unit-testable. Returns ``None`` when the
    role has fewer than ``min_nodes`` claim nodes (too little signal to report).

    This measures evidence-tag coverage where tags actually live — the Draft
    node ``evidence_tag`` field — unlike :func:`minions.tools.book._source_role_unmarked_ratio`,
    which scans Book *prose* pages that almost never carry inline markers and so
    returns ~1.0 for every role. A higher value here means *worse* coverage.
    """
    claims = [
        n
        for n in nodes
        if (n.get("author_role") or "").strip() == author_role
        and n.get("type") in _CLAIM_NODE_TYPES
    ]
    if len(claims) < min_nodes:
        return None
    unmarked = sum(1 for n in claims if not str(n.get("evidence_tag") or "").strip())
    return round(unmarked / len(claims), 3)


def mos_draft_unmarked_audit(threshold: float = 0.2) -> dict[str, Any]:
    """Per-role unmarked-claim ratio over Draft nodes; an Ethics-facing signal.

    Computes, for each authoring role, the fraction of its claim-bearing nodes
    (types ``result`` / ``decision`` / ``hypothesis`` / ``insight``) that carry
    no ``evidence_tag``, and flags roles whose ratio exceeds ``threshold``
    (default ``0.2``). Roles with too few claim nodes report ``None`` and are
    never flagged.

    **Advisory only.** This does not auto-trigger re-tagging or retraction and
    does not mutate the Draft — it surfaces a descriptive coverage signal for
    Ethics to adjudicate, consistent with the "evidence convention is cultural,
    not mechanical" contract in ``minions/roles/SYSTEM.md``. Whitelisted to
    Ethics + Gru.
    """
    port = _env_port()
    nodes = _load_draft(port)["nodes"]
    roles = sorted(
        {
            (n.get("author_role") or "").strip()
            for n in nodes
            if (n.get("author_role") or "").strip()
        }
    )
    per_role = {role: _role_unmarked_ratio(nodes, role) for role in roles}
    flagged = sorted(r for r, v in per_role.items() if v is not None and v > threshold)
    return {
        "threshold": threshold,
        "per_role_unmarked": per_role,
        "flagged_roles": flagged,
    }


def mos_draft_append(
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    resolves_pending: list[str] | None = None,
) -> dict[str, Any]:
    """Add new nodes and/or edges. Auto-generates IDs if not provided.

    ``resolves_pending`` is the list of pending-plan node ids this append
    *replaces*. A plan node is a temporary placeholder for intended work
    (carries ``metadata.pending_plan == true``); once you execute the plan
    and land the real ``result`` / ``decision`` node, the plan node has done
    its job and must disappear — the Draft records what *happened*, not what
    was *intended*. Pass the plan id(s) here and they are removed in the SAME
    atomic write that lands the result, so the graph never accumulates zombie
    "verified question" nodes. Safety: only nodes whose
    ``metadata.pending_plan`` is true are eligible for removal; any other id
    is ignored (logged), so this can never delete a real landed imprint.
    """
    port = _env_port()
    draft = _load_draft(port)
    ts = _now_iso()
    created_node_ids: list[str] = []
    created_edge_count = 0

    for node in nodes or []:
        ntype = node.get("type", "hypothesis")
        if ntype not in NODE_TYPES:
            logger.info("Custom node type: %s (not in suggested types)", ntype)
        provenance = node.get("provenance", "extracted")
        if provenance not in PROVENANCES:
            logger.info("Custom provenance: %s (not in suggested provenances)", provenance)
        confidence = _validate_confidence(node.get("confidence", 1.0))
        node_id = node.get("id") or _next_id(draft, ntype)

        # Auto-inject reel_ref into metadata if available and not already set.
        # This links the Draft node to the raw session transcripts that
        # produced it, enabling drill-down audit via mos_reel_get / window.
        node_metadata = dict(node.get("metadata", {}))
        if "reel_ref" not in node_metadata:
            reel_ctx = _env_reel_context()
            if reel_ctx:
                node_metadata["reel_ref"] = reel_ctx

        # Motif contract enforcement for curator (Ethics) nodes (soft — warnings only, no reject).
        # Existing nodes without motif_kind are treated as motif_kind="none" for read purposes.
        author_role = node.get("author_role", "") or _env_role()
        if author_role == "ethics" and ntype in _CURATOR_MOTIF_REQUIRED_TYPES:
            motif_kind = node_metadata.get("motif_kind")
            if not motif_kind:
                logger.warning(
                    "ethics appending %s node '%s' without motif_kind — "
                    "prefer mos_draft_annotate to update existing nodes instead",
                    ntype,
                    node.get("id", "<new>"),
                )
                # Warning-code key kept byte-stable for the pinned test in
                # tests/unit/test_draft.py; the human-text log above is updated.
                node_metadata["warning"] = "noter_node_without_motif_kind"
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
            "author_role": node.get("author_role", "") or _env_role(),
            "created_at": node.get("created_at", ts),
            "evidence_tag": node.get("evidence_tag", ""),
            "provenance": provenance,
            "confidence": confidence,
            "metadata": node_metadata,
        }
        draft["nodes"].append(new_node)
        created_node_ids.append(node_id)
        _append_journal(
            port,
            {
                "op": "add_node",
                "node": new_node,
                "timestamp": ts,
                "author_role": new_node["author_role"],
            },
        )

    # Infer batch author from nodes (fallback for edges without explicit author)
    batch_author = _env_role()
    if not batch_author:
        for node in nodes or []:
            if node.get("author_role"):
                batch_author = node["author_role"]
                break

    for edge in edges or []:
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
            "created_at": edge.get("created_at", ts),
            "author_role": edge.get("author_role", "") or batch_author,
        }
        draft["edges"].append(new_edge)
        created_edge_count += 1
        _append_journal(
            port,
            {
                "op": "add_edge",
                "edge": new_edge,
                "timestamp": ts,
                "author_role": new_edge["author_role"],
            },
        )

    # Resolve pending plans: a plan node is a temporary placeholder; once the
    # work lands as a real node above, the plan must disappear (Draft = what
    # happened, not what was intended). Remove only nodes that are genuinely
    # pending plans — never a landed imprint. Edges touching a removed plan are
    # dropped too, so no dangling references survive.
    resolved_plan_ids: list[str] = []
    if resolves_pending:
        nodes_by_id = {n["id"]: n for n in draft["nodes"]}
        removable: set[str] = set()
        for pid in resolves_pending:
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
                _append_journal(
                    port,
                    {
                        "op": "resolve_pending",
                        "node_id": pid,
                        "replaced_by": created_node_ids,
                        "timestamp": ts,
                        "author_role": _env_role(),
                    },
                )

    _save_draft(port, draft)
    # Soft-audit: increment the per-role append counter so mos_await_events
    # can detect cycles where a role handled real EACN events but wrote no
    # Draft nodes (Draft-discipline reminder, see minions.tools.draft_audit).
    # Failure here is logged at debug and swallowed — the audit is
    # observability, not correctness.
    if created_node_ids:
        try:
            from minions.tools import draft_audit as _draft_audit

            agent_id = os.environ.get("MINIONS_AGENT_ID", "") or _env_role()
            if agent_id:
                _draft_audit.record_append(port, agent_id, count=len(created_node_ids))
        except Exception as exc:
            logger.debug("draft_audit.record_append failed: %s", exc)
    return {
        "created_node_ids": created_node_ids,
        "created_edge_count": created_edge_count,
        "resolved_plan_ids": resolved_plan_ids,
    }


def mos_draft_annotate(
    node_id: str,
    support_status: DraftSupportStatus | None = None,
    evidence_tag: str | None = None,
    provenance: DraftProvenance | None = None,
    confidence: float | None = None,
    metadata_update: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update an existing node's mutable fields. Type and text are immutable."""
    port = _env_port()
    draft = _load_draft(port)
    ts = _now_iso()

    target = None
    for node in draft["nodes"]:
        if node["id"] == node_id:
            target = node
            break
    if target is None:
        raise DraftError(f"Node not found: {node_id}")

    annotator = _env_role() or target.get("author_role", "")
    changes: dict[str, Any] = {}

    if support_status is not None:
        if support_status not in SUPPORT_STATUSES:
            logger.info("Custom support_status: %s", support_status)
        old = target.get("support_status", "")
        target["support_status"] = support_status
        changes["support_status"] = {"old": old, "new": support_status}
        _append_journal(
            port,
            {
                "op": "annotate",
                "node_id": node_id,
                "field": "support_status",
                "old_value": old,
                "new_value": support_status,
                "evidence_tag": evidence_tag or "",
                "timestamp": ts,
                "author_role": annotator,
            },
        )

    if evidence_tag is not None:
        old = target.get("evidence_tag", "")
        target["evidence_tag"] = evidence_tag
        changes["evidence_tag"] = {"old": old, "new": evidence_tag}
        _append_journal(
            port,
            {
                "op": "annotate",
                "node_id": node_id,
                "field": "evidence_tag",
                "old_value": old,
                "new_value": evidence_tag,
                "timestamp": ts,
                "author_role": annotator,
            },
        )

    if provenance is not None:
        if provenance not in PROVENANCES:
            logger.info("Custom provenance: %s (not in suggested provenances)", provenance)
        old = target.get("provenance")
        target["provenance"] = provenance
        changes["provenance"] = {"old": old, "new": provenance}
        _append_journal(
            port,
            {
                "op": "annotate",
                "node_id": node_id,
                "field": "provenance",
                "old_value": old,
                "new_value": provenance,
                "timestamp": ts,
                "author_role": annotator,
            },
        )

    if confidence is not None:
        new_confidence = _validate_confidence(confidence)
        old = target.get("confidence")
        target["confidence"] = new_confidence
        changes["confidence"] = {"old": old, "new": new_confidence}
        _append_journal(
            port,
            {
                "op": "annotate",
                "node_id": node_id,
                "field": "confidence",
                "old_value": old,
                "new_value": new_confidence,
                "timestamp": ts,
                "author_role": annotator,
            },
        )

    if metadata_update:
        old_meta = dict(target.get("metadata", {}))
        target.setdefault("metadata", {}).update(metadata_update)
        changes["metadata"] = {"added_keys": list(metadata_update.keys())}
        _append_journal(
            port,
            {
                "op": "annotate",
                "node_id": node_id,
                "field": "metadata",
                "old_value": old_meta,
                "new_value": target["metadata"],
                "timestamp": ts,
                "author_role": annotator,
            },
        )

    _save_draft(port, draft)
    if support_status is not None and support_status in BOOK_STATUS_HOOK_STATUSES:
        token = _BOOK_STATUS_EVENT_TARGET.set(target)
        try:
            _emit_book_status_event(port, target["id"], support_status, annotator)
        except Exception as exc:
            logger.warning(
                "book status hook failed for node %s status %s: %s",
                target["id"],
                support_status,
                exc,
            )
        finally:
            _BOOK_STATUS_EVENT_TARGET.reset(token)
    return {"node_id": node_id, "changes": changes}


def mos_draft_path(
    target_node_id: str,
    from_node_id: str | None = None,
) -> dict[str, Any]:
    """Weighted shortest path (Dijkstra) preferring high-strength edges."""
    port = _env_port()
    draft = _load_draft(port)
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in draft["nodes"]}
    edges = draft["edges"]

    if target_node_id not in nodes_by_id:
        raise DraftError(f"Target node not found: {target_node_id}")

    # Build adjacency (undirected). Weight = 1.0 - strength (high strength = low cost).
    adj: dict[str, list[tuple[float, str, dict]]] = defaultdict(list)
    for edge in edges:
        w = 1.0 - edge.get("strength", 1.0)
        adj[edge["from_id"]].append((w, edge["to_id"], edge))
        adj[edge["to_id"]].append((w, edge["from_id"], edge))

    # Determine start node.
    if from_node_id:
        start = from_node_id
    else:
        if not draft["nodes"]:
            raise DraftError("Draft is empty")
        start = draft["nodes"][0]["id"]

    if start not in nodes_by_id:
        raise DraftError(f"Start node not found: {start}")

    if start == target_node_id:
        return {"path_nodes": [nodes_by_id[start]], "path_edges": []}

    # Dijkstra.
    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, dict]] = {}
    heap: list[tuple[float, str]] = [(0.0, start)]

    while heap:
        d, current = heapq.heappop(heap)
        if current == target_node_id:
            break
        if d > dist.get(current, float("inf")):
            continue
        for w, neighbor, edge in adj[current]:
            nd = d + w
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = (current, edge)
                heapq.heappush(heap, (nd, neighbor))

    if target_node_id not in prev:
        return {
            "error": f"No path from {start} to {target_node_id}",
            "path_nodes": [],
            "path_edges": [],
        }

    # Reconstruct path.
    path_ids: list[str] = []
    path_edges: list[dict] = []
    cur = target_node_id
    while cur != start:
        path_ids.append(cur)
        parent, edge = prev[cur]
        path_edges.append(edge)
        cur = parent
    path_ids.append(start)
    path_ids.reverse()
    path_edges.reverse()

    return {
        "path_nodes": [nodes_by_id[nid] for nid in path_ids if nid in nodes_by_id],
        "path_edges": path_edges,
    }


def mos_draft_summary() -> dict[str, Any]:
    """High-level Draft summary for role wakeup injection. Kept under 800 tokens.

    Surfaces pending plans (nodes with metadata.pending_plan == true) at the
    top so a freshly respawned post-reset agent can see what its previous
    self had planned but not yet executed, and pick up without losing work.
    """
    port = _env_port()
    draft = _load_draft(port)
    nodes = draft["nodes"]
    edges = draft["edges"]

    # Counts by type.
    by_type: dict[str, int] = defaultdict(int)
    for n in nodes:
        by_type[n.get("type", "unknown")] += 1

    # Counts by status.
    by_status: dict[str, int] = defaultdict(int)
    for n in nodes:
        by_status[n.get("support_status", "unknown")] += 1

    # Counts by provenance, including legacy nodes missing the field.
    by_provenance: dict[str, int] = defaultdict(int)
    by_provenance_role: defaultdict[str, defaultdict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for n in nodes:
        provenance = str(n.get("provenance") or "unknown")
        role = str(n.get("author_role") or "unknown")
        by_provenance[provenance] += 1
        by_provenance_role[role][provenance] += 1

    # Pending plans — checkpointed-but-not-executed work. Newest first so a
    # post-reset agent picks up the most recent intent.
    pending = [
        n
        for n in nodes
        if (n.get("metadata") or {}).get("pending_plan") is True
        and n.get("support_status") in ("unverified", "tentative")
    ]
    pending.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    pending_view = [
        {
            "id": p["id"],
            "type": p.get("type", ""),
            "text": p.get("text", ""),
            "author_role": p.get("author_role", ""),
            "created_at": p.get("created_at", ""),
        }
        for p in pending[:10]
    ]

    # Active hypotheses (tentative or unverified).
    active_hyps = [
        n
        for n in nodes
        if n.get("type") == "hypothesis" and n.get("support_status") in ("tentative", "unverified")
    ]

    # Recent decisions (last 5).
    decisions = [n for n in nodes if n.get("type") == "decision"]
    recent_decisions = sorted(decisions, key=lambda n: n.get("created_at", ""), reverse=True)[:5]

    # Blocked paths.
    blocked = [n for n in nodes if n.get("support_status") == "blocked"]

    # Dead ends.
    dead_ends = [n for n in nodes if n.get("type") == "dead_end"]

    # Decay sidecar (computed by Ethics via mos_draft_decay_compute).
    # Surfaces the most-decayed and most-reinforced nodes so a waking role
    # sees which prior knowledge has weakened or strengthened. Absent until
    # Ethics runs once — degrades cleanly to {} otherwise.
    decay_map = _load_decay(port)
    decay_view: dict[str, Any] = {}
    if decay_map:
        ranked = [
            (nid, entry)
            for nid, entry in decay_map.items()
            if isinstance(entry, dict) and "effective_confidence" in entry
        ]
        ranked.sort(key=lambda item: float(item[1].get("effective_confidence", 0.0)))
        most_decayed = [
            {
                "id": nid,
                "effective_confidence": entry.get("effective_confidence"),
                "stored_confidence": entry.get("stored_confidence"),
                "age_days": entry.get("age_days"),
                "supports": entry.get("supports"),
                "contradicts": entry.get("contradicts"),
            }
            for nid, entry in ranked[:5]
        ]
        ranked.sort(
            key=lambda item: float(item[1].get("effective_confidence", 0.0)),
            reverse=True,
        )
        most_reinforced = [
            {
                "id": nid,
                "effective_confidence": entry.get("effective_confidence"),
                "stored_confidence": entry.get("stored_confidence"),
                "supports": entry.get("supports"),
            }
            for nid, entry in ranked[:5]
            if int(entry.get("supports", 0) or 0) > 0
        ]
        decay_view = {
            "node_count": len(decay_map),
            "most_decayed": most_decayed,
            "most_reinforced": most_reinforced,
        }

    return {
        "project_port": port,
        "root_question": draft.get("root_question", ""),
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "pending_plans": pending_view,
        "pending_plans_total": len(pending),
        "nodes_by_type": dict(by_type),
        "nodes_by_status": dict(by_status),
        "nodes_by_provenance": dict(by_provenance),
        "nodes_by_provenance_role": {
            role: dict(counts) for role, counts in by_provenance_role.items()
        },
        "active_hypotheses": [{"id": h["id"], "text": h["text"]} for h in active_hyps[:10]],
        "recent_decisions": [{"id": d["id"], "text": d["text"]} for d in recent_decisions],
        "blocked_count": len(blocked),
        "dead_end_count": len(dead_ends),
        "decay": decay_view,
    }


def mos_draft_view(
    query: str | None = None,
    by_role: str | None = None,
    by_status: DraftSupportStatus | None = None,
    by_type: DraftNodeType | None = None,
    related_to: str | None = None,
    sort: str = "time",
    limit: int = 20,
) -> dict[str, Any]:
    """The single unified read over the Draft graph for role agents.

    One tool, orthogonal dimensions. It always returns a compact orientation
    header (totals, pending_plans, counts) so a waking role gets its bearings
    in one call, plus the requested slice of nodes and their incident edges.

    Dimensions (combine freely; all optional):
      - query: free-text relevance push (keyword overlap + type weighting).
      - by_role / by_status / by_type: exact-match filters.
      - related_to: 1-hop neighbour subgraph of a node id (ignores filters).
      - sort: "time" (newest landed first — the default a waking role wants),
        "relevance" (only meaningful with query), or "confidence".
      - limit: max nodes in the slice.

    This subsumes the older summary / query / relevant / topic_index reads:
    call with no args for the orientation header + newest nodes (cold-start
    orient); pass query for relevance; pass related_to for a neighbourhood.
    """
    port = _env_port()
    header = mos_draft_summary()  # orientation: totals, pending_plans, counts, decay

    # Slice selection.
    if related_to:
        sub = mos_draft_query(related_to=related_to, limit=limit)
        nodes = list(sub["nodes"])
        edges = list(sub["edges"])
    elif query:
        rel = mos_draft_relevant(query, max_nodes=limit)
        nodes = list(rel["relevant_nodes"])
        edges = list(rel["relevant_edges"])
    else:
        sub = mos_draft_query(
            node_type=by_type,
            support_status=by_status,
            author_role=by_role,
            limit=max(limit * 4, limit),  # over-fetch; re-sort + trim below
        )
        nodes = list(sub["nodes"])
        edges = list(sub["edges"])

    # Apply remaining filters that the chosen slice did not already enforce
    # (query/related_to paths ignore the exact-match filters, so honour them here).
    if by_role:
        nodes = [n for n in nodes if (n.get("author_role") or "") == by_role]
    if by_status:
        nodes = [n for n in nodes if n.get("support_status") == by_status]
    if by_type:
        nodes = [n for n in nodes if n.get("type") == by_type]

    # Sort. "relevance" keeps mos_draft_relevant's order; time/confidence re-sort.
    if sort == "time":
        nodes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    elif sort == "confidence":
        nodes.sort(key=lambda n: float(n.get("confidence", 0.0) or 0.0), reverse=True)

    nodes = nodes[:limit]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from_id"] in node_ids or e["to_id"] in node_ids]

    return {
        "project_port": port,
        "root_question": header.get("root_question", ""),
        "totals": {
            "nodes": header.get("total_nodes", 0),
            "edges": header.get("total_edges", 0),
        },
        "pending_plans": header.get("pending_plans", []),
        "pending_plans_total": header.get("pending_plans_total", 0),
        "nodes_by_type": header.get("nodes_by_type", {}),
        "nodes_by_status": header.get("nodes_by_status", {}),
        "filter": {
            "query": query,
            "by_role": by_role,
            "by_status": by_status,
            "by_type": by_type,
            "related_to": related_to,
            "sort": sort,
        },
        "nodes": nodes,
        "edges": edges,
        "returned": len(nodes),
    }


def mos_draft_commit_shared(message: str | None = None) -> dict[str, Any]:
    """Flush the buffered Draft to a single commit on the shared branch.

    Owned by Ethics. The Draft file at
    ``branches/main/draft/draft.json`` is updated freely by every
    role through ``mos_draft_append`` / ``mos_draft_annotate`` (working tree
    only, no commit). This tool performs one auditable commit per call by
    publishing the current Draft state through ``mos_publish_to_shared``.

    Intended use: Ethics cron tick (default every 5 minutes — configurable
    in ``gru.yaml``). Other roles must not call this themselves; the
    whitelist binds it to Ethics and Gru only.

    Returns the publish result dict (``commit_sha``, ``branch``, etc.).
    Raises if the Draft file does not exist or the publish fails.
    """
    from minions.tools.publish import mos_publish_to_shared

    port = _env_port()
    draft_path = _draft_path(port)
    if not draft_path.exists():
        return {
            "port": port,
            "role": _env_role() or "ethics",
            "dst_path": "draft/draft.json",
            "commit_sha": None,
            "pushed": False,
            "push_branch": None,
            "branch": None,
            "skipped": "draft.json does not exist yet",
        }
    msg = message or f"ethics: draft flush {_now_iso()}"
    # mos_publish_to_shared returns a PublishToSharedResult (DictLikeBaseModel)
    # which is read-compatible with dict[str, Any] via __getitem__/get. Cast
    # preserves the existing tool contract while keeping the typed return
    # at the publish layer.
    return cast(
        "dict[str, Any]",
        mos_publish_to_shared(
            role=_env_role() or "ethics",
            src_path=str(draft_path),
            dst_subpath="draft/draft.json",
            commit_message=msg,
            port=port,
        ),
    )


def mos_draft_relevant(context_text: str, max_nodes: int = 10) -> dict[str, Any]:
    """Find Draft nodes relevant to a given context (event text, task description).

    This is the PUSH mechanism: instead of the agent deciding what to query,
    the system finds relevant prior knowledge based on what the agent is
    currently looking at.

    Uses keyword overlap between context_text and node text/metadata.
    No vector embeddings needed — simple but effective for structured nodes.
    """
    port = _env_port()
    dag_data = _load_draft(port)
    nodes = dag_data["nodes"]
    edges = dag_data["edges"]

    if not nodes or not context_text:
        return {"relevant_nodes": [], "relevant_edges": []}

    # Build searchable text per node (text + type + metadata values)
    context_lower = context_text.lower()
    context_words = {w for w in context_lower.split() if len(w) > 3}

    scored: list[tuple[float, dict]] = []
    for node in nodes:
        # Combine all searchable fields
        parts = [
            node.get("text", ""),
            node.get("type", ""),
            node.get("id", ""),
        ]
        # Include metadata values (topic, reason, etc.)
        meta = node.get("metadata", {})
        if isinstance(meta, dict):
            parts.extend(str(v) for v in meta.values())
        node_searchable = " ".join(parts).lower()
        node_words = {w for w in node_searchable.split() if len(w) > 3}

        # Score: keyword overlap + substring containment
        overlap = len(context_words & node_words)
        # Also check if any context word is a substring of node text
        for cw in context_words:
            if cw in node_searchable and cw not in node_words:
                overlap += 0.5

        if overlap > 0:
            boost = 1.0
            if node.get("type") == "dead_end":
                boost = 2.0
            elif node.get("type") == "decision":
                boost = 1.5
            elif node.get("support_status") == "verified":
                boost = 1.3
            scored.append((overlap * boost, node))

    # Sort by relevance, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    relevant_nodes = [node for _, node in scored[:max_nodes]]

    # Get edges connecting relevant nodes
    relevant_ids = {n["id"] for n in relevant_nodes}
    relevant_edges = [
        e for e in edges if e["from_id"] in relevant_ids or e["to_id"] in relevant_ids
    ]

    # Fallback: if no keyword matches, return top-level nodes as orientation
    if not scored:
        # Return hypotheses, decisions, insights as general orientation
        fallback = [
            n for n in nodes if n.get("type") in ("hypothesis", "decision", "insight", "result")
        ]
        fallback.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        relevant_nodes = fallback[:max_nodes]
        relevant_ids = {n["id"] for n in relevant_nodes}
        relevant_edges = [
            e for e in edges if e["from_id"] in relevant_ids or e["to_id"] in relevant_ids
        ]
        return {
            "relevant_nodes": relevant_nodes,
            "relevant_edges": relevant_edges,
            "match_count": len(fallback),
            "fallback": True,
        }

    return {
        "relevant_nodes": relevant_nodes,
        "relevant_edges": relevant_edges,
        "match_count": len(scored),
    }


def mos_draft_topic_index() -> dict[str, Any]:
    """Return a topic-level index of the Draft.

    Groups nodes by their metadata 'topic' field (if present) or by
    community membership. Provides a one-line orientation per topic
    so agents know what prior work exists without querying each topic.
    """
    port = _env_port()
    dag_data = _load_draft(port)
    nodes = dag_data["nodes"]

    # Group by topic metadata
    topics: dict[str, list[dict]] = {}
    for node in nodes:
        topic = node.get("metadata", {}).get("topic", "")
        if not topic:
            # Infer topic from first significant word in text
            words = node.get("text", "").lower().split()
            topic = next((w for w in words if len(w) > 4), "general")
        topics.setdefault(topic, []).append(node)

    # Build index
    index = []
    for topic, topic_nodes in sorted(topics.items(), key=lambda x: -len(x[1])):
        statuses = {}
        for n in topic_nodes:
            s = n.get("support_status", "unverified")
            statuses[s] = statuses.get(s, 0) + 1
        dead_ends = sum(1 for n in topic_nodes if n.get("type") == "dead_end")
        latest = max(topic_nodes, key=lambda n: n.get("created_at", ""))
        index.append(
            {
                "topic": topic,
                "node_count": len(topic_nodes),
                "latest_node": latest["id"],
                "status_summary": statuses,
                "dead_ends": dead_ends,
            }
        )

    return {"topics": index, "total_topics": len(index)}


def mos_draft_communities() -> dict[str, Any]:
    """Detect communities using connected components + label propagation.

    Phase 1: Find connected components (handles disconnected subgraphs).
    Phase 2: Within large components (>10 nodes), use label propagation
             to find sub-communities.

    Returns clusters of related nodes that form coherent research threads.
    """
    port = _env_port()
    dag_data = _load_draft(port)
    nodes = dag_data["nodes"]
    edges = dag_data["edges"]

    if not nodes:
        return {"communities": [], "total_communities": 0, "cross_community_edges": []}

    node_ids = {n["id"] for n in nodes}
    nodes_by_id = {n["id"]: n for n in nodes}

    # Build undirected adjacency.
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["from_id"] in node_ids and edge["to_id"] in node_ids:
            adj[edge["from_id"]].append(edge["to_id"])
            adj[edge["to_id"]].append(edge["from_id"])

    # Phase 1: Connected components via BFS.
    visited: set[str] = set()
    components: list[set[str]] = []
    for nid in node_ids:
        if nid in visited:
            continue
        # BFS from this node
        component: set[str] = set()
        queue = deque([nid])
        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)
            component.add(curr)
            for nb in adj.get(curr, []):
                if nb not in visited and nb in node_ids:
                    queue.append(nb)
        components.append(component)

    # Phase 2: For large components, sub-divide with label propagation.
    final_groups: list[list[str]] = []
    for comp in components:
        if len(comp) <= 10:
            final_groups.append(list(comp))
            continue
        # Label propagation within this component
        labels = {nid: nid for nid in comp}
        for _ in range(50):
            changed = False
            order = list(comp)
            random.shuffle(order)
            for nid in order:
                neighbors = [nb for nb in adj.get(nid, []) if nb in comp]
                if not neighbors:
                    continue
                counts: dict[str, int] = defaultdict(int)
                for nb in neighbors:
                    counts[labels[nb]] += 1
                if not counts:
                    continue
                max_count = max(counts.values())
                candidates = [lbl for lbl, c in counts.items() if c == max_count]
                best = min(candidates)
                if labels[nid] != best:
                    labels[nid] = best
                    changed = True
            if not changed:
                break
        # Group by label within component
        sub_groups: dict[str, list[str]] = defaultdict(list)
        for nid, lbl in labels.items():
            sub_groups[lbl].append(nid)
        final_groups.extend(sub_groups.values())

    # Sort by size descending, assign IDs.
    final_groups.sort(key=len, reverse=True)
    node_to_community: dict[str, int] = {}
    communities_out = []
    for idx, group in enumerate(final_groups):
        for nid in group:
            node_to_community[nid] = idx
        # Determine dominant type
        type_counts: dict[str, int] = defaultdict(int)
        for nid in group:
            if nid in nodes_by_id:
                type_counts[nodes_by_id[nid].get("type", "unknown")] += 1
        dominant = max(type_counts, key=lambda k: type_counts[k]) if type_counts else "unknown"
        communities_out.append(
            {
                "id": idx,
                "size": len(group),
                "nodes": group,
                "dominant_type": dominant,
            }
        )

    # Cross-community edges.
    cross = []
    for edge in edges:
        f, t = edge["from_id"], edge["to_id"]
        if f in node_to_community and t in node_to_community:
            cf, ct = node_to_community[f], node_to_community[t]
            if cf != ct:
                cross.append(
                    {
                        "from": f,
                        "to": t,
                        "relation": edge.get("relation", ""),
                        "communities": [cf, ct],
                    }
                )

    return {
        "communities": communities_out,
        "total_communities": len(communities_out),
        "cross_community_edges": cross,
    }


def mos_draft_god_nodes(top_n: int = 5) -> dict[str, Any]:
    """Identify hub nodes with highest connectivity (degree centrality).

    These are foundational assumptions or key results that many other
    nodes depend on. Changing a god node affects the whole graph.
    """
    port = _env_port()
    draft = _load_draft(port)
    nodes = draft["nodes"]
    edges = draft["edges"]

    if not nodes:
        return {"god_nodes": []}

    nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    type_of: dict[str, str] = {n["id"]: n.get("type", "unknown") for n in nodes}

    # Degree and cross-type connections.
    degree: dict[str, int] = defaultdict(int)
    connected_ids: dict[str, set[str]] = defaultdict(set)
    connected_types: dict[str, set[str]] = defaultdict(set)

    for edge in edges:
        fid, tid = edge["from_id"], edge["to_id"]
        degree[fid] += 1
        degree[tid] += 1
        connected_ids[fid].add(tid)
        connected_ids[tid].add(fid)
        connected_types[fid].add(type_of.get(tid, "unknown"))
        connected_types[tid].add(type_of.get(fid, "unknown"))

    # Score = degree * (1 + 0.2 * cross_type_count).
    scored: list[tuple[float, str]] = []
    for nid in nodes_by_id:
        d = degree.get(nid, 0)
        ct = len(connected_types.get(nid, set()))
        score = d * (1.0 + 0.2 * ct)
        scored.append((score, nid))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[:top_n]

    god_nodes = []
    for score, nid in top:
        node = nodes_by_id[nid]
        god_nodes.append(
            {
                "id": nid,
                "text": node.get("text", ""),
                "score": round(score, 2),
                "degree": degree.get(nid, 0),
                "cross_type_connections": len(connected_types.get(nid, set())),
                "connected_to": sorted(connected_ids.get(nid, set())),
            }
        )

    return {"god_nodes": god_nodes}
