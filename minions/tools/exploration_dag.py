"""Exploration DAG â project-level shared knowledge graph for autonomous discovery.

Records hypotheses, experiments, results, dead ends, decisions, and their
relationships.  All roles read/write through these functions; the MCP
registration layer in ``mcp_server.py`` wraps them as tools.

Environment:
    MINIONS_PROJECT_PORT â identifies the project.

Storage:
    project_{port}/exploration/dag.json   â canonical graph state.
    project_{port}/exploration/journal.jsonl â append-only mutation log.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.paths import project_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

SUPPORT_STATUSES = (
    "unverified",
    "tentative",
    "verified",
    "refuted",
    "blocked",
    "out_of_scope",
)

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
    return project_dir(port) / "exploration"


def _dag_path(port: int) -> Path:
    return _exploration_dir(port) / "dag.json"


def _journal_path(port: int) -> Path:
    return _exploration_dir(port) / "journal.jsonl"


def _env_port() -> int:
    raw = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not raw:
        raise RuntimeError("MINIONS_PROJECT_PORT not set")
    return int(raw)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
    prefix = TYPE_PREFIX[node_type]
    existing_nums: list[int] = []
    for node in dag["nodes"]:
        nid: str = node.get("id", "")
        if nid.startswith(prefix + "-"):
            suffix = nid[len(prefix) + 1 :]
            if suffix.isdigit():
                existing_nums.append(int(suffix))
    next_num = max(existing_nums, default=0) + 1
    return f"{prefix}-{next_num:03d}"


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

    return {"nodes": nodes[:limit], "edges": edges, "total_matched": len(nodes)}


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
            raise ValueError(f"Invalid node type: {ntype}")
        node_id = node.get("id") or _next_id(dag, ntype)
        new_node = {
            "id": node_id,
            "type": ntype,
            "text": node.get("text", ""),
            "support_status": node.get("support_status", "unverified"),
            "author_role": node.get("author_role", ""),
            "created_at": node.get("created_at", ts),
            "evidence_tag": node.get("evidence_tag", ""),
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

    for edge in edges or []:
        relation = edge.get("relation", "")
        if relation not in EDGE_RELATIONS:
            raise ValueError(f"Invalid edge relation: {relation}")
        new_edge = {
            "from_id": edge["from_id"],
            "to_id": edge["to_id"],
            "relation": relation,
            "created_at": edge.get("created_at", ts),
            "author_role": edge.get("author_role", ""),
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

    changes: dict[str, Any] = {}

    if support_status is not None:
        if support_status not in SUPPORT_STATUSES:
            raise ValueError(f"Invalid support_status: {support_status}")
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
                "author_role": "",
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
                "author_role": "",
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
                "author_role": "",
            },
        )

    _save_dag(port, dag)
    return {"node_id": node_id, "changes": changes}


def mos_dag_path(
    target_node_id: str,
    from_node_id: str | None = None,
) -> dict[str, Any]:
    """BFS shortest path from root (or from_node_id) to target_node_id."""
    port = _env_port()
    dag = _load_dag(port)
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in dag["nodes"]}
    edges = dag["edges"]

    if target_node_id not in nodes_by_id:
        return {"error": f"Target node not found: {target_node_id}"}

    # Build adjacency (undirected for path finding).
    adj: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for edge in edges:
        adj[edge["from_id"]].append((edge["to_id"], edge))
        adj[edge["to_id"]].append((edge["from_id"], edge))

    # Determine start node.
    if from_node_id:
        start = from_node_id
    else:
        # Use first node as root if no explicit root marker.
        if not dag["nodes"]:
            return {"error": "DAG is empty"}
        start = dag["nodes"][0]["id"]

    if start not in nodes_by_id:
        return {"error": f"Start node not found: {start}"}

    if start == target_node_id:
        return {"path_nodes": [nodes_by_id[start]], "path_edges": []}

    # BFS.
    visited: set[str] = {start}
    queue: deque[tuple[str, list[str], list[dict]]] = deque()
    queue.append((start, [start], []))

    while queue:
        current, path_ids, path_edges = queue.popleft()
        for neighbor, edge in adj[current]:
            if neighbor in visited:
                continue
            new_path = [*path_ids, neighbor]
            new_edges = [*path_edges, edge]
            if neighbor == target_node_id:
                return {
                    "path_nodes": [nodes_by_id[nid] for nid in new_path if nid in nodes_by_id],
                    "path_edges": new_edges,
                }
            visited.add(neighbor)
            queue.append((neighbor, new_path, new_edges))

    return {
        "error": f"No path from {start} to {target_node_id}",
        "path_nodes": [],
        "path_edges": [],
    }


def mos_dag_summary() -> dict[str, Any]:
    """High-level DAG summary for role wakeup injection. Kept under 800 tokens."""
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
        "nodes_by_type": dict(by_type),
        "nodes_by_status": dict(by_status),
        "active_hypotheses": [{"id": h["id"], "text": h["text"]} for h in active_hyps[:10]],
        "recent_decisions": [{"id": d["id"], "text": d["text"]} for d in recent_decisions],
        "blocked_count": len(blocked),
        "dead_end_count": len(dead_ends),
    }
