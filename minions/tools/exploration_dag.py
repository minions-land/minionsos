"""Exploration DAG — project-level shared knowledge graph for autonomous discovery.

Records hypotheses, experiments, results, dead ends, decisions, and their
relationships.  All roles read/write through these functions; the MCP
registration layer in ``mcp_server.py`` wraps them as tools.

Environment:
    MINIONS_PROJECT_PORT — identifies the project.

Storage:
    project_{port}/branches/shared/exploration/dag.json     — canonical graph state.
    project_{port}/branches/shared/exploration/journal.jsonl — append-only mutation log.

The DAG and journal live inside the cross-role shared worktree
(``branches/shared/`` on branch ``minionsos/project-{port}-shared``) so
DAG history is auditable in git. ``mos_dag_append`` and
``mos_dag_annotate`` write to the working tree only; commits happen on a
cron through ``mos_dag_commit_shared``, which is owned by Noter and
flushes the buffered DAG state via ``mos_publish_to_shared`` (single
commit per cron tick, message "noter: dag flush <ts>").
"""

from __future__ import annotations

import heapq
import json
import logging
import os
import random
import tempfile
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.paths import project_shared_dag_json, project_shared_subdir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Suggested node types. Agents may use any string — these are recommendations.
NODE_TYPES = (
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
)

# Suggested support statuses. Agents may use any string.
SUPPORT_STATUSES = (
    "unverified",
    "tentative",
    "verified",
    "refuted",
    "blocked",
    "out_of_scope",
)

# Suggested provenance labels. Agents may use any string.
PROVENANCES = (
    "extracted",
    "inferred",
    "speculative",
)
# extracted: from a cited source/artifact
# inferred: derived from prior nodes (low-medium confidence)
# speculative: agent's working hypothesis, not yet evidenced

WIKI_STATUS_HOOK_STATUSES = frozenset({"verified", "refuted", "dead_end"})
_WIKI_STATUS_EVENT_TARGET: ContextVar[dict[str, Any] | None] = ContextVar(
    "_WIKI_STATUS_EVENT_TARGET",
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
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _exploration_dir(port: int) -> Path:
    return project_shared_subdir(port, "exploration")


def _dag_path(port: int) -> Path:
    return project_shared_dag_json(port)


def _journal_path(port: int) -> Path:
    return _exploration_dir(port) / "journal.jsonl"


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _env_role() -> str:
    """Return the current role name from env, or empty string."""
    return os.environ.get("MINIONS_ROLE_NAME", "")


def _load_dag(port: int) -> dict[str, Any]:
    path = _dag_path(port)
    if not path.exists():
        return {"project_port": port, "root_question": "", "nodes": [], "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_dag(port: int, dag: dict[str, Any]) -> None:
    path = _dag_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dag, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _append_journal(port: int, entry: dict[str, Any]) -> None:
    path = _journal_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _next_id(dag: dict[str, Any], node_type: str) -> str:
    prefix = TYPE_PREFIX.get(node_type, node_type[:3].upper())
    existing_nums: list[int] = []
    for node in dag["nodes"]:
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
        raise ValueError(f"Node confidence must be a number, got {confidence!r}") from exc
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"Node confidence must be 0.0-1.0, got {value}")
    return value


def _emit_wiki_status_event(
    port: int,
    node_id: str,
    new_status: str,
    annotator: str,
) -> None:
    """Emit a best-effort Wiki ingest event for terminal hypothesis statuses."""
    target = _WIKI_STATUS_EVENT_TARGET.get()
    if target is None or target.get("id") != node_id:
        dag = _load_dag(port)
        target = next((node for node in dag["nodes"] if node.get("id") == node_id), {})
    node_text = str(target.get("text", ""))
    node_type = str(target.get("type", ""))
    date_updated = _now_iso()
    blob = "\n".join(
        [
            "---",
            "type: hypothesis_status",
            f"dag_node_id: {node_id}",
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
            "Auto-generated by Phase 7 DAG↔Wiki hook.",
            "",
        ]
    )
    temp_path: Path | None = None
    try:
        temp_dir = project_shared_subdir(port, "noter") / ".dag-status-events"
        temp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=temp_dir,
            prefix="dag-status-",
            suffix=".md",
        ) as temp_file:
            temp_file.write(blob)
            temp_path = Path(temp_file.name)

        from minions.tools.wiki import mos_wiki_ingest

        mos_wiki_ingest(
            src_path=str(temp_path),
            source_role="noter",
            source_slug=f"dag-status-{node_id.replace('-', '').lower()[:30]}-{new_status}",
            title=f"Status update: {node_id} → {new_status}",
            port=port,
        )
    except Exception as exc:
        logger.warning(
            "wiki status event emission failed for node %s status %s: %s",
            node_id,
            new_status,
            exc,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("failed to remove wiki status temp file %s: %s", temp_path, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mos_dag_query(
    node_type: str | None = None,
    support_status: str | None = None,
    author_role: str | None = None,
    text_contains: str | None = None,
    related_to: str | None = None,
    limit: int = 50,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Query the DAG. Returns matching nodes and their immediate edges."""
    port = _env_port()
    dag = _load_dag(port)
    nodes: list[dict] = dag["nodes"]
    edges: list[dict] = dag["edges"]

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
    result: dict[str, Any] = {"nodes": nodes, "edges": edges, "total_matched": len(nodes)}
    if truncated:
        result["truncated"] = True
    return result


def mos_dag_append(
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add new nodes and/or edges. Auto-generates IDs if not provided."""
    port = _env_port()
    dag = _load_dag(port)
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
        node_id = node.get("id") or _next_id(dag, ntype)
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
            "metadata": node.get("metadata", {}),
        }
        dag["nodes"].append(new_node)
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
            raise ValueError(f"Edge strength must be 0.0-1.0, got {strength}")
        new_edge = {
            "from_id": edge["from_id"],
            "to_id": edge["to_id"],
            "relation": relation,
            "strength": strength,
            "created_at": edge.get("created_at", ts),
            "author_role": edge.get("author_role", "") or batch_author,
        }
        dag["edges"].append(new_edge)
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

    _save_dag(port, dag)
    return {"created_node_ids": created_node_ids, "created_edge_count": created_edge_count}


def mos_dag_annotate(
    node_id: str,
    support_status: str | None = None,
    evidence_tag: str | None = None,
    provenance: str | None = None,
    confidence: float | None = None,
    metadata_update: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update an existing node's mutable fields. Type and text are immutable."""
    port = _env_port()
    dag = _load_dag(port)
    ts = _now_iso()

    target = None
    for node in dag["nodes"]:
        if node["id"] == node_id:
            target = node
            break
    if target is None:
        raise ValueError(f"Node not found: {node_id}")

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

    _save_dag(port, dag)
    if support_status is not None and support_status in WIKI_STATUS_HOOK_STATUSES:
        token = _WIKI_STATUS_EVENT_TARGET.set(target)
        try:
            _emit_wiki_status_event(port, target["id"], support_status, annotator)
        except Exception as exc:
            logger.warning(
                "wiki status hook failed for node %s status %s: %s",
                target["id"],
                support_status,
                exc,
            )
        finally:
            _WIKI_STATUS_EVENT_TARGET.reset(token)
    return {"node_id": node_id, "changes": changes}


def mos_dag_path(
    target_node_id: str,
    from_node_id: str | None = None,
) -> dict[str, Any]:
    """Weighted shortest path (Dijkstra) preferring high-strength edges."""
    port = _env_port()
    dag = _load_dag(port)
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in dag["nodes"]}
    edges = dag["edges"]

    if target_node_id not in nodes_by_id:
        raise ValueError(f"Target node not found: {target_node_id}")

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
        if not dag["nodes"]:
            raise ValueError("DAG is empty")
        start = dag["nodes"][0]["id"]

    if start not in nodes_by_id:
        raise ValueError(f"Start node not found: {start}")

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


def mos_dag_summary() -> dict[str, Any]:
    """High-level DAG summary for role wakeup injection. Kept under 800 tokens.

    Surfaces pending plans (nodes with metadata.pending_plan == true) at the
    top so a freshly respawned post-reset agent can see what its previous
    self had planned but not yet executed, and pick up without losing work.
    """
    port = _env_port()
    dag = _load_dag(port)
    nodes = dag["nodes"]
    edges = dag["edges"]

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

    return {
        "project_port": port,
        "root_question": dag.get("root_question", ""),
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
    }


def mos_dag_commit_shared(message: str | None = None) -> dict[str, Any]:
    """Flush the buffered DAG to a single commit on the shared branch.

    Owned by Noter. The DAG file at
    ``branches/shared/exploration/dag.json`` is updated freely by every
    role through ``mos_dag_append`` / ``mos_dag_annotate`` (working tree
    only, no commit). This tool performs one auditable commit per call by
    publishing the current DAG state through ``mos_publish_to_shared``.

    Intended use: Noter cron tick (default every 5 minutes — configurable
    in ``gru.yaml``). Other roles must not call this themselves; the
    whitelist binds it to Noter and Gru only.

    Returns the publish result dict (``commit_sha``, ``branch``, etc.).
    Raises if the DAG file does not exist or the publish fails.
    """
    from minions.tools.publish import mos_publish_to_shared

    port = _env_port()
    dag_path = _dag_path(port)
    if not dag_path.exists():
        return {
            "port": port,
            "role": _env_role() or "noter",
            "dst_path": "exploration/dag.json",
            "commit_sha": None,
            "pushed": False,
            "push_branch": None,
            "branch": None,
            "skipped": "dag.json does not exist yet",
        }
    msg = message or f"noter: dag flush {_now_iso()}"
    return mos_publish_to_shared(
        role=_env_role() or "noter",
        src_path=str(dag_path),
        dst_subpath="exploration/dag.json",
        commit_message=msg,
        port=port,
    )


def mos_dag_relevant(context_text: str, max_nodes: int = 10) -> dict[str, Any]:
    """Find DAG nodes relevant to a given context (event text, task description).

    This is the PUSH mechanism: instead of the agent deciding what to query,
    the system finds relevant prior knowledge based on what the agent is
    currently looking at.

    Uses keyword overlap between context_text and node text/metadata.
    No vector embeddings needed — simple but effective for structured nodes.
    """
    port = _env_port()
    dag_data = _load_dag(port)
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


def mos_dag_topic_index() -> dict[str, Any]:
    """Return a topic-level index of the DAG.

    Groups nodes by their metadata 'topic' field (if present) or by
    community membership. Provides a one-line orientation per topic
    so agents know what prior work exists without querying each topic.
    """
    port = _env_port()
    dag_data = _load_dag(port)
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


def mos_dag_communities() -> dict[str, Any]:
    """Detect communities using connected components + label propagation.

    Phase 1: Find connected components (handles disconnected subgraphs).
    Phase 2: Within large components (>10 nodes), use label propagation
             to find sub-communities.

    Returns clusters of related nodes that form coherent research threads.
    """
    port = _env_port()
    dag_data = _load_dag(port)
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
        dominant = max(type_counts, key=type_counts.get) if type_counts else "unknown"
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


def mos_dag_god_nodes(top_n: int = 5) -> dict[str, Any]:
    """Identify hub nodes with highest connectivity (degree centrality).

    These are foundational assumptions or key results that many other
    nodes depend on. Changing a god node affects the whole graph.
    """
    port = _env_port()
    dag = _load_dag(port)
    nodes = dag["nodes"]
    edges = dag["edges"]

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
