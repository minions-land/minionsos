"""Unit tests for the Gru-only cross-project global graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minions.tools import shelf


@pytest.fixture
def graph_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    projects_root = tmp_path / "projects"
    global_path = tmp_path / ".minionsos" / "shelf.json"
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))
    monkeypatch.setattr(shelf, "_shelf_path", lambda: global_path)
    return projects_root, global_path


def _write_shelf(
    projects_root: Path,
    port: int,
    *,
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]] | None = None,
) -> Path:
    graph_path = (
        projects_root
        / f"project_{port}"
        / "branches"
        / "shared"
        / "atlas"
        / "atlas.json"
    )
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps({"nodes": nodes, "links": links or []}, indent=2) + "\n",
        encoding="utf-8",
    )
    return graph_path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_register_creates_shelf_with_prefixed_node_ids(
    graph_env: tuple[Path, Path],
) -> None:
    projects_root, global_path = graph_env
    _write_shelf(
        projects_root,
        41001,
        nodes=[
            {"id": "n1", "label": "Transformer Architecture", "community": 1},
            {"id": "n2", "label": "Attention Routing", "community": 1},
        ],
        links=[{"source": "n1", "target": "n2"}],
    )

    result = shelf.mos_shelf_register(41001)

    assert result == {"registered": True, "port": 41001, "nodes_added": 2, "edges_added": 1}
    data = _load_json(global_path)
    assert {node["id"] for node in data["nodes"]} == {"p41001_n1", "p41001_n2"}
    assert {node["project_port"] for node in data["nodes"]} == {41001}
    assert data["links"] == [{"project_port": 41001, "source": "p41001_n1", "target": "p41001_n2"}]


def test_reregister_same_port_replaces_nodes(
    graph_env: tuple[Path, Path],
) -> None:
    projects_root, global_path = graph_env
    _write_shelf(
        projects_root,
        41002,
        nodes=[{"id": "old", "label": "Old Concept"}],
    )
    shelf.mos_shelf_register(41002)
    _write_shelf(
        projects_root,
        41002,
        nodes=[{"id": "new", "label": "New Concept"}],
    )

    result = shelf.mos_shelf_register(41002)

    assert result["nodes_added"] == 1
    data = _load_json(global_path)
    assert [node["id"] for node in data["nodes"]] == ["p41002_new"]


def test_query_returns_matching_nodes_with_project_port(
    graph_env: tuple[Path, Path],
) -> None:
    projects_root, _global_path = graph_env
    _write_shelf(
        projects_root,
        41003,
        nodes=[{"id": "n1", "label": "Transformer Attention"}],
    )
    _write_shelf(
        projects_root,
        41004,
        nodes=[{"id": "n2", "label": "Optimizer Schedule"}],
    )
    shelf.mos_shelf_register(41003)
    shelf.mos_shelf_register(41004)

    result = shelf.mos_shelf_query("attention transformer")

    assert result["total"] == 1
    assert result["projects_searched"] == 2
    assert result["matches"] == [
        {
            "node_id": "p41003_n1",
            "label": "Transformer Attention",
            "project_port": 41003,
            "community": None,
            "score": 2.0,
            "is_god_node": False,
            "via": "direct",
        }
    ]


def test_query_returns_empty_when_no_match(
    graph_env: tuple[Path, Path],
) -> None:
    projects_root, _global_path = graph_env
    _write_shelf(
        projects_root,
        41005,
        nodes=[{"id": "n1", "label": "Transformer Architecture"}],
    )
    shelf.mos_shelf_register(41005)

    result = shelf.mos_shelf_query("optimizer")

    assert result == {"matches": [], "total": 0, "projects_searched": 1}


def test_shared_concepts_finds_overlapping_labels(
    graph_env: tuple[Path, Path],
) -> None:
    projects_root, _global_path = graph_env
    _write_shelf(
        projects_root,
        41006,
        nodes=[{"id": "a", "label": "Transformer Attention Routing"}],
    )
    _write_shelf(
        projects_root,
        41007,
        nodes=[{"id": "b", "label": "Attention Routing Probe"}],
    )
    shelf.mos_shelf_register(41006)
    shelf.mos_shelf_register(41007)

    result = shelf.mos_shelf_shared_concepts(41006, 41007)

    assert result["count"] == 1
    assert result["shared"] == [
        {
            "label_a": "Transformer Attention Routing",
            "label_b": "Attention Routing Probe",
            "score": 2.0,
            "port_a": 41006,
            "port_b": 41007,
            "node_a": "p41006_a",
            "node_b": "p41007_b",
        }
    ]


def test_shared_concepts_returns_empty_without_overlap(
    graph_env: tuple[Path, Path],
) -> None:
    projects_root, _global_path = graph_env
    _write_shelf(
        projects_root,
        41008,
        nodes=[{"id": "a", "label": "Transformer Architecture"}],
    )
    _write_shelf(
        projects_root,
        41009,
        nodes=[{"id": "b", "label": "Optimizer Schedule"}],
    )
    shelf.mos_shelf_register(41008)
    shelf.mos_shelf_register(41009)

    result = shelf.mos_shelf_shared_concepts(41008, 41009)

    assert result == {"shared": [], "count": 0}


def test_atlas_query_whitelisted_only_for_gru_main() -> None:
    from minions.config import resolve_server_authz

    assert "mos_shelf_query" in resolve_server_authz("gru", "main")
    assert "mos_shelf_query" not in resolve_server_authz("coder", "main")
    assert "mos_shelf_query" not in resolve_server_authz("ethics", "main")


def test_atlas_register_whitelisted_only_for_noter_main() -> None:
    from minions.config import resolve_server_authz

    assert "mos_shelf_register" in resolve_server_authz("noter", "main")
    assert "mos_shelf_register" not in resolve_server_authz("gru", "main")
    assert "mos_shelf_register" not in resolve_server_authz("coder", "main")
