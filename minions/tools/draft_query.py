"""Draft query and traversal operations.

Extracted from draft.py to isolate graph query logic.
"""

from __future__ import annotations

import heapq
import random
from collections import defaultdict, deque
from typing import Any

from minions.errors import DraftError
from minions.tools.draft_helpers import env_port, load_draft
from minions.tools.draft_nodes import DraftNodeType, DraftSupportStatus
from minions.tools._returns import DictLikeBaseModel
from pydantic import Field, model_serializer


class DraftQueryResult(DictLikeBaseModel):
    """Result shape for mos_draft_query.

    Surfaces matching nodes plus the edges that connect them.
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
        data = handler(self)
        if data.get("truncated") is None:
            data.pop("truncated", None)
        return data


def mos_draft_query(
    node_type: DraftNodeType | None = None,
    support_status: DraftSupportStatus | None = None,
    author_role: str | None = None,
    text_contains: str | None = None,
    related_to: str | None = None,
    limit: int = 50,
    max_tokens: int = 2000,
) -> DraftQueryResult:
    """Query the Draft. Returns matching nodes and their immediate edges."""
    port = env_port()
    draft = load_draft(port)
    nodes: list[dict] = draft["nodes"]
    edges: list[dict] = draft["edges"]

    # If related_to is specified, return subgraph connected to that node
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
        # Apply filters
        if node_type:
            nodes = [n for n in nodes if n.get("type") == node_type]
        if support_status:
            nodes = [n for n in nodes if n.get("support_status") == support_status]
        if author_role:
            nodes = [n for n in nodes if n.get("author_role") == author_role]
        if text_contains:
            lc = text_contains.lower()
            nodes = [n for n in nodes if lc in n.get("text", "").lower()]

        # Filter edges to only those connecting matched nodes
        matched_ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["from_id"] in matched_ids or e["to_id"] in matched_ids]

    nodes = nodes[:limit]
    # Token budget estimation: ~50 tokens/node, ~30 tokens/edge
    est_tokens = len(nodes) * 50 + len(edges) * 30
    truncated = False
    if est_tokens > max_tokens:
        # Reduce nodes to fit budget (edges scale with nodes)
        max_nodes = max(1, (max_tokens - len(edges) * 30) // 50)
        nodes = nodes[:max_nodes]
        truncated = True
    return DraftQueryResult(
        nodes=nodes,
        edges=edges,
        total_matched=len(nodes),
        truncated=True if truncated else None,
    )


def mos_draft_path(
    target_node_id: str,
    from_node_id: str | None = None,
) -> dict[str, Any]:
    """Weighted shortest path (Dijkstra) preferring high-strength edges."""
    port = env_port()
    draft = load_draft(port)
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in draft["nodes"]}
    edges = draft["edges"]

    if target_node_id not in nodes_by_id:
        raise DraftError(f"Target node not found: {target_node_id}")

    # Build adjacency (undirected). Weight = 1.0 - strength (high strength = low cost)
    adj: dict[str, list[tuple[float, str, dict]]] = defaultdict(list)
    for edge in edges:
        w = 1.0 - edge.get("strength", 1.0)
        adj[edge["from_id"]].append((w, edge["to_id"], edge))
        adj[edge["to_id"]].append((w, edge["from_id"], edge))

    # Determine start node
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

    # Dijkstra
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

    # Reconstruct path
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


def mos_draft_relevant(context_text: str, max_nodes: int = 10) -> dict[str, Any]:
    """Find Draft nodes relevant to a given context (event text, task description).

    This is the PUSH mechanism: keyword overlap between context_text and node text.
    """
    port = env_port()
    dag_data = load_draft(port)
    nodes = dag_data["nodes"]
    edges = dag_data["edges"]

    if not nodes or not context_text:
        return {"relevant_nodes": [], "relevant_edges": []}

    # Build searchable text per node
    context_lower = context_text.lower()
    context_words = {w for w in context_lower.split() if len(w) > 3}

    scored: list[tuple[float, dict]] = []
    for node in nodes:
        parts = [
            node.get("text", ""),
            node.get("type", ""),
            node.get("id", ""),
        ]
        meta = node.get("metadata", {})
        if isinstance(meta, dict):
            parts.extend(str(v) for v in meta.values())
        node_searchable = " ".join(parts).lower()
        node_words = {w for w in node_searchable.split() if len(w) > 3}

        # Score: keyword overlap + substring containment
        overlap = len(context_words & node_words)
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


def mos_draft_communities() -> dict[str, Any]:
    """Detect communities using connected components + label propagation."""
    port = env_port()
    dag_data = load_draft(port)
    nodes = dag_data["nodes"]
    edges = dag_data["edges"]

    if not nodes:
        return {"communities": [], "total_communities": 0, "cross_community_edges": []}

    node_ids = {n["id"] for n in nodes}
    nodes_by_id = {n["id"]: n for n in nodes}

    # Build undirected adjacency
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["from_id"] in node_ids and edge["to_id"] in node_ids:
            adj[edge["from_id"]].append(edge["to_id"])
            adj[edge["to_id"]].append(edge["from_id"])

    # Phase 1: Connected components via BFS
    visited: set[str] = set()
    components: list[set[str]] = []
    for nid in node_ids:
        if nid in visited:
            continue
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

    # Phase 2: For large components, sub-divide with label propagation
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

    # Sort by size descending, assign IDs
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

    # Cross-community edges
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
    """Identify hub nodes with highest connectivity (degree centrality)."""
    port = env_port()
    draft = load_draft(port)
    nodes = draft["nodes"]
    edges = draft["edges"]

    if not nodes:
        return {"god_nodes": []}

    nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    type_of: dict[str, str] = {n["id"]: n.get("type", "unknown") for n in nodes}

    # Degree and cross-type connections
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

    # Score = degree * (1 + 0.2 * cross_type_count)
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


def mos_draft_topic_index() -> dict[str, Any]:
    """Return a topic-level index of the Draft."""
    port = env_port()
    dag_data = load_draft(port)
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
