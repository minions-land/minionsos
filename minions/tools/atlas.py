"""Gru-only cross-project global atlas.

MinionsOS projects each own a local atlas under their shared branch.
This module aggregates those per-project graphs into a single Gru-readable
index at ``~/.minionsos/atlas-global.json``.

The boundary rules are strict: only Gru can query across projects; project
internal Roles never see cross-project data; Gru can relay digested results
back through ``mos_project_bridge``.

Registration is project-local and performed by Noter after atlas
rebuilds. Nodes are prefixed with ``p{port}_`` before merging so local graph
IDs cannot collide across projects.
"""

from __future__ import annotations

import json
import logging
import os
import re
from math import ceil
from pathlib import Path
from typing import Any

from minions.paths import project_shared_subdir

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _atlas_path() -> Path:
    """Return the canonical global Atlas path."""
    return Path.home() / ".minionsos" / "atlas-global.json"


def _empty_atlas() -> dict[str, object]:
    return {"projects": {}, "nodes": [], "links": []}


def _normalise_atlas(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        return _empty_atlas()
    projects = data.get("projects")
    nodes = data.get("nodes")
    links = data.get("links")
    return {
        "projects": projects if isinstance(projects, dict) else {},
        "nodes": nodes if isinstance(nodes, list) else [],
        "links": links if isinstance(links, list) else [],
    }


def _load_atlas() -> dict:
    """Load the global Atlas, returning an empty structure when absent."""
    path = _atlas_path()
    if not path.exists() or path.stat().st_size == 0:
        return _empty_atlas()
    try:
        return _normalise_atlas(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to load global Atlas %s: %s", path, exc)
        return _empty_atlas()


def _save_atlas(data: dict) -> None:
    """Atomically save the global Atlas."""
    path = _atlas_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 3}


def _token_overlap_score(text_a: str, text_b: str) -> float:
    """Return the Library-style token overlap score for two strings."""
    tokens_a = _tokens(text_a)
    tokens_b = _tokens(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return float(len(tokens_a & tokens_b))


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _node_id(node: dict[str, Any]) -> str:
    raw = node.get("id")
    return "" if raw is None else str(raw)


def _node_label(node: dict[str, Any]) -> str:
    for key in ("label", "name", "title", "text", "id"):
        value = node.get(key)
        if value is not None:
            return str(value)
    return ""


def _node_project_port(node: dict[str, Any]) -> int | None:
    value = node.get("project_port")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _endpoint_id(value: object) -> str | None:
    raw = value.get("id") if isinstance(value, dict) else value
    if raw is None:
        return None
    endpoint = str(raw)
    return endpoint or None


def _link_touches_prefix(link: dict[str, Any], prefix: str) -> bool:
    source = _endpoint_id(link.get("source"))
    target = _endpoint_id(link.get("target"))
    return bool(
        (source is not None and source.startswith(prefix))
        or (target is not None and target.startswith(prefix))
    )


def _project_graph_path(port: int) -> Path:
    return project_shared_subdir(port, "atlas") / "atlas.json"


def _load_project_graph(port: int) -> dict[str, object] | None:
    path = _project_graph_path(port)
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to load project atlas %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _registered_project_ports(data: dict[str, object]) -> set[int]:
    ports: set[int] = set()
    projects = data.get("projects")
    if isinstance(projects, dict):
        for key in projects:
            try:
                ports.add(int(key))
            except (TypeError, ValueError):
                continue
    for node in _dict_items(data.get("nodes")):
        port = _node_project_port(node)
        if port is not None:
            ports.add(port)
    return ports


def _node_degrees(data: dict[str, object]) -> dict[str, int]:
    nodes = _dict_items(data.get("nodes"))
    degrees = {_node_id(node): 0 for node in nodes if _node_id(node)}
    for link in _dict_items(data.get("links")):
        source = _endpoint_id(link.get("source"))
        target = _endpoint_id(link.get("target"))
        if source in degrees:
            degrees[source] += 1
        if target in degrees and target != source:
            degrees[target] += 1
    return degrees


def _god_node_ids(data: dict[str, object]) -> set[str]:
    degrees = _node_degrees(data)
    positive_degrees = sorted((degree for degree in degrees.values() if degree > 0), reverse=True)
    if not positive_degrees:
        return set()
    top_count = max(1, ceil(len(degrees) * 0.05))
    threshold = positive_degrees[min(top_count, len(positive_degrees)) - 1]
    return {node_id for node_id, degree in degrees.items() if degree >= threshold and degree > 0}


def mos_atlas_register(port: int) -> dict[str, object]:
    """Register a project's atlas.json into the global Atlas.

    Called by Noter after each atlas rebuild (wired into noter_wait.py
    alongside _maybe_rebuild_atlas). Reads the project's
    atlas.json, prefixes all node IDs with `p{port}_` to avoid
    collisions, and merges into ~/.minionsos/atlas-global.json.

    Idempotent: re-registering the same port replaces its nodes/edges.
    """
    resolved_port = int(port)
    project_graph = _load_project_graph(resolved_port)
    if project_graph is None:
        return {"registered": False, "reason": "no graph"}

    source_nodes = _dict_items(project_graph.get("nodes"))
    source_links = _dict_items(project_graph.get("links", project_graph.get("edges")))
    if not source_nodes:
        return {"registered": False, "reason": "no graph"}

    prefix = f"p{resolved_port}_"
    id_map: dict[str, str] = {}
    new_nodes: list[dict[str, Any]] = []
    for node in source_nodes:
        old_id = _node_id(node)
        if not old_id:
            continue
        new_id = f"{prefix}{old_id}"
        id_map[old_id] = new_id
        new_node = dict(node)
        new_node["id"] = new_id
        new_node["project_port"] = resolved_port
        new_nodes.append(new_node)

    if not new_nodes:
        return {"registered": False, "reason": "no graph"}

    new_links: list[dict[str, Any]] = []
    for link in source_links:
        source = _endpoint_id(link.get("source"))
        target = _endpoint_id(link.get("target"))
        if source is None or target is None:
            continue
        new_link = dict(link)
        new_link["source"] = id_map.get(source, f"{prefix}{source}")
        new_link["target"] = id_map.get(target, f"{prefix}{target}")
        new_link["project_port"] = resolved_port
        new_links.append(new_link)

    data = _load_atlas()
    projects = dict(data.get("projects") if isinstance(data.get("projects"), dict) else {})
    nodes = _dict_items(data.get("nodes"))
    links = _dict_items(data.get("links"))

    projects.pop(str(resolved_port), None)
    projects[str(resolved_port)] = {
        "port": resolved_port,
        "nodes": len(new_nodes),
        "links": len(new_links),
    }
    data = {
        "projects": projects,
        "nodes": [node for node in nodes if not _node_id(node).startswith(prefix)] + new_nodes,
        "links": [link for link in links if not _link_touches_prefix(link, prefix)] + new_links,
    }
    _save_atlas(data)
    return {
        "registered": True,
        "port": resolved_port,
        "nodes_added": len(new_nodes),
        "edges_added": len(new_links),
    }


def mos_atlas_query(text: str, max_results: int = 10) -> dict[str, object]:
    """Query the global Atlas for cross-project concept overlap.

    Gru-only. Searches all registered projects' nodes by keyword overlap
    (same algorithm as mos_library_query: split text into at least 3-char tokens,
    score by overlap, return top-N). Results include the project_port so
    Gru knows which project each node belongs to.

    Returns: {"matches": [{"node_id", "label", "project_port", "community",
                 "score", "is_god_node": bool}], "total": N, "projects_searched": M}.
    """
    data = _load_atlas()
    god_nodes = _god_node_ids(data)
    matches: list[dict[str, object]] = []
    for node in _dict_items(data.get("nodes")):
        label = _node_label(node)
        score = _token_overlap_score(text, label)
        if score <= 0:
            continue
        node_id = _node_id(node)
        matches.append(
            {
                "node_id": node_id,
                "label": label,
                "project_port": _node_project_port(node),
                "community": node.get("community"),
                "score": score,
                "is_god_node": node_id in god_nodes,
            }
        )

    matches.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["label"]),
            str(item["node_id"]),
        )
    )
    limit = max(0, int(max_results))
    return {
        "matches": matches[:limit],
        "total": len(matches),
        "projects_searched": len(_registered_project_ports(data)),
    }


def mos_atlas_shared_concepts(
    port_a: int,
    port_b: int,
    min_score: float = 0.5,
) -> dict[str, object]:
    """Find concepts shared between two projects.

    Gru-only. Compares node labels between project A and project B using
    token overlap. Returns pairs where overlap score is at least min_score.

    Returns: {"shared": [{"label_a", "label_b", "score", "port_a", "port_b",
                 "node_a", "node_b"}], "count": N}.
    """
    resolved_a = int(port_a)
    resolved_b = int(port_b)
    nodes = _dict_items(_load_atlas().get("nodes"))
    nodes_a = [node for node in nodes if _node_project_port(node) == resolved_a]
    nodes_b = [node for node in nodes if _node_project_port(node) == resolved_b]

    shared: list[dict[str, object]] = []
    for node_a in nodes_a:
        label_a = _node_label(node_a)
        best_node: dict[str, Any] | None = None
        best_label = ""
        best_score = 0.0
        for node_b in nodes_b:
            label_b = _node_label(node_b)
            score = _token_overlap_score(label_a, label_b)
            if score > best_score:
                best_node = node_b
                best_label = label_b
                best_score = score
        if best_node is None or best_score < float(min_score):
            continue
        shared.append(
            {
                "label_a": label_a,
                "label_b": best_label,
                "score": best_score,
                "port_a": resolved_a,
                "port_b": resolved_b,
                "node_a": _node_id(node_a),
                "node_b": _node_id(best_node),
            }
        )

    shared.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["label_a"]),
            str(item["label_b"]),
        )
    )
    capped = shared[:20]
    return {"shared": capped, "count": len(capped)}
