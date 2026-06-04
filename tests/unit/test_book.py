"""Unit tests for the Phase 2 Book Layer 2 surface."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from minions.errors import ProjectError
from minions.paths import project_shared_branch_name, project_shared_workspace, project_state_dir
from minions.tools import book, publish
from minions.tools import book_ingest  # 添加导入以支持正确的mock


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    port = 41234
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    shared = project_shared_workspace(port)
    (shared / "coder").mkdir(parents=True)
    (shared / "book" / "sources").mkdir(parents=True)
    project_state_dir(port).mkdir(parents=True)
    return {"port": port, "shared": shared}


def _mock_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    publish_results: list[dict[str, object]] = []

    def fake_publish_to_shared(
        *,
        role: str,
        src_path: str,
        dst_subpath: str,
        commit_message: str,
        port: int | None = None,
        store: object | None = None,
    ) -> dict[str, object]:
        del store
        assert role == "ethics"
        assert commit_message.startswith("ethics: ingest ")
        resolved_port = port or book._env_port()
        src = Path(src_path)
        dst = project_shared_workspace(resolved_port) / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        result: dict[str, object] = {
            "port": resolved_port,
            "role": role,
            "dst_path": dst_subpath,
            "commit_sha": f"fake-{len(publish_results) + 1}",
            "pushed": False,
            "push_branch": None,
            "branch": project_shared_branch_name(resolved_port),
        }
        publish_results.append(result)
        return result

    monkeypatch.setattr(publish, "mos_publish_to_shared", fake_publish_to_shared)

    def fake_publish_files(*, role, files, commit_message, port=None, **kwargs):
        for entry in files:
            fake_publish_to_shared(
                role=role,
                src_path=entry["src_path"],
                dst_subpath=entry["dst_subpath"],
                commit_message=commit_message,
                port=port,
            )
        return {
            "port": port,
            "role": role,
            "dst_paths": [e["dst_subpath"] for e in files],
            "commit_sha": f"fake-{len(publish_results)}",
            "pushed": False,
            "push_branch": None,
            "branch": "stub",
        }

    # Mock在book_ingest模块中的导入
    monkeypatch.setattr(book_ingest, "mos_publish_files_to_shared", fake_publish_files)
    return publish_results


def test_wiki_ingest_creates_page_index_and_log(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_results = _mock_publish(monkeypatch)
    source = project["shared"] / "coder" / "artifact.md"
    source.write_text("\n".join(f"line {idx}" for idx in range(1, 205)) + "\n", encoding="utf-8")

    result = book.mos_book_ingest(
        src_path=str(source),
        source_role="coder",
        source_slug="transformer-run",
        title="Transformer Result",
        port=project["port"],
    )

    page = project["shared"] / "book" / "sources" / "coder-transformer-run.md"
    assert page.exists()
    page_lines = page.read_text(encoding="utf-8").splitlines()
    assert page_lines[:10] == [
        "---",
        "type: source",
        'title: "Transformer Result"',
        'slug: "coder-transformer-run"',
        'source_file: "main/coder/artifact.md"',
        'source_role: "coder"',
        page_lines[6],
        "page_kind: source",
        "confidence: high",
        "---",
    ]
    assert page_lines[6].startswith('date_ingested: "')
    assert "line 200" in page_lines
    assert "line 201" not in page_lines

    index = (project["shared"] / "book" / "index.md").read_text(encoding="utf-8")
    assert "## Transformer Result" in index
    assert "slug: coder-transformer-run" in index
    assert "book_path: book/sources/coder-transformer-run.md" in index

    log_path = project["shared"] / "book" / "log.md"
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["op"] == "ingest"
    assert rows[0]["slug"] == "coder-transformer-run"
    assert rows[0]["source_file"] == "main/coder/artifact.md"

    assert result["slug"] == "coder-transformer-run"
    assert result["book_path"] == "book/sources/coder-transformer-run.md"
    assert result["indexed"] is True
    assert result["logged"] is True
    assert len(result["publish_results"]) == 1
    assert len(publish_results) == 3


def test_wiki_ingest_is_idempotent_for_index_entries(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_results = _mock_publish(monkeypatch)
    source = project["shared"] / "coder" / "artifact.md"
    source.write_text("first version\n", encoding="utf-8")

    book.mos_book_ingest(str(source), "coder", "same-slug", title="First", port=project["port"])
    source.write_text("second version\n", encoding="utf-8")
    result = book.mos_book_ingest(
        str(source),
        "coder",
        "same-slug",
        title="Second",
        port=project["port"],
    )

    index = (project["shared"] / "book" / "index.md").read_text(encoding="utf-8")
    assert index.count("slug: coder-same-slug") == 1
    assert "## Second" in index
    assert len(result["publish_results"]) == 1
    assert len(publish_results) == 6


def test_wiki_ingest_missing_source_raises(project: dict[str, Any]) -> None:
    missing = project["shared"] / "coder" / "missing.md"
    with pytest.raises(book.BookError, match="src_path does not exist"):
        book.mos_book_ingest(str(missing), "coder", "missing", port=project["port"])


def test_wiki_query_returns_matching_index_entry(project: dict[str, Any]) -> None:
    index = project["shared"] / "book" / "index.md"
    index.write_text(
        "\n".join(
            [
                "# Book Index",
                "",
                "## Transformer Architecture",
                "slug: coder-transformer",
                "type: source",
                "page_kind: source",
                "book_path: book/sources/coder-transformer.md",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = book.mos_book_query("transformer", port=project["port"])
    assert result["total"] == 1
    assert len(result["matches"]) == 1
    m = result["matches"][0]
    assert m["slug"] == "coder-transformer"
    assert m["title"] == "Transformer Architecture"
    assert m["page_kind"] == "source"
    assert m["book_path"] == "book/sources/coder-transformer.md"
    assert m["score"] == 1
    assert m["relations"] == []


def test_wiki_query_returns_empty_when_no_entries_match(project: dict[str, Any]) -> None:
    index = project["shared"] / "book" / "index.md"
    index.write_text(
        "\n".join(
            [
                "# Wiki Index",
                "",
                "## Transformer Architecture",
                "slug: coder-transformer",
                "type: source",
                "page_kind: source",
                "book_path: book/sources/coder-transformer.md",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = book.mos_book_query("optimizer", port=project["port"])
    assert result == {"matches": [], "total": 0, "queried": "optimizer"}


def test_publish_policy_allows_ethics_book() -> None:
    """Ethics is the merged memory curator now — it owns the book/ surface."""
    assert publish._validate_dst("ethics", "book/audit.md") == Path("book/audit.md")
    assert publish._validate_dst("ethics", "book/sources/source.md") == Path(
        "book/sources/source.md"
    )


def test_publish_policy_rejects_expert_book() -> None:
    """Non-curator roles (Expert) may not publish into book/."""
    with pytest.raises(ProjectError, match="may not publish under branches/shared"):
        publish._validate_dst("expert", "book/sources/source.md")


# ---------------------------------------------------------------------------
# v15.19.2 — Book index synthesizes edges from contradiction pages
# ---------------------------------------------------------------------------


def _write_contradiction_page(
    book_root: Path,
    *,
    page_slug: str,
    new_source: str,
    opposing_slug: str,
    status: str = "unresolved",
) -> None:
    p = book_root / "contradictions" / f"{page_slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        f'slug: "{page_slug}"\n'
        f'new_source: "{new_source}"\n'
        f'opposing_page: "book/sources/{opposing_slug}.md"\n'
        f'status: "{status}"\n'
        "page_kind: contradiction\n"
        "---\n"
        "\n"
        f"# Contradiction: {new_source}\n",
        encoding="utf-8",
    )


def test_scan_book_edges_synthesizes_from_contradiction_pages(
    project: dict[str, Any],
) -> None:
    """v15.19.2: every contradiction page implies a contradicts edge."""
    book_root = project["shared"] / "book"
    book_root.mkdir(exist_ok=True)
    _write_contradiction_page(
        book_root,
        page_slug="contradiction-coder-baseline",
        new_source="coder-baseline",
        opposing_slug="ethics-flag",
    )
    _write_contradiction_page(
        book_root,
        page_slug="contradiction-coder-other",
        new_source="coder-other",
        opposing_slug="expert-mathematician",
    )
    edges = book._scan_book_edges(book_root)
    assert len(edges) == 2
    pairs = {(e["from"], e["to"], e["relation"]) for e in edges}
    assert ("coder-baseline", "ethics-flag", "contradicts") in pairs
    assert ("coder-other", "expert-mathematician", "contradicts") in pairs
    # Every edge has an evidence pointer to its source contradiction page.
    for edge in edges:
        assert edge["evidence"].startswith("book/contradictions/")


def test_scan_book_edges_skips_resolved(project: dict[str, Any]) -> None:
    """Resolved contradictions are no longer live edges."""
    book_root = project["shared"] / "book"
    _write_contradiction_page(
        book_root,
        page_slug="contradiction-resolved-x",
        new_source="coder-x",
        opposing_slug="ethics-x",
        status="resolved",
    )
    _write_contradiction_page(
        book_root,
        page_slug="contradiction-live-y",
        new_source="coder-y",
        opposing_slug="ethics-y",
        status="unresolved",
    )
    edges = book._scan_book_edges(book_root)
    assert len(edges) == 1
    assert edges[0]["from"] == "coder-y"


def test_render_index_appends_relations_block(project: dict[str, Any]) -> None:
    """When ``book_root`` is given to ``_render_index``, the rendered file
    grows a ``## Relations`` section listing every live edge."""
    book_root = project["shared"] / "book"
    _write_contradiction_page(
        book_root,
        page_slug="contradiction-a-vs-b",
        new_source="coder-a",
        opposing_slug="coder-b",
    )
    entries = [
        {
            "slug": "coder-a",
            "title": "A",
            "type": "source",
            "page_kind": "source",
            "book_path": "book/sources/coder-a.md",
        },
        {
            "slug": "coder-b",
            "title": "B",
            "type": "source",
            "page_kind": "source",
            "book_path": "book/sources/coder-b.md",
        },
    ]
    rendered = book._render_index(entries, book_root=book_root)
    # Both nodes still listed.
    assert "## A" in rendered
    assert "## B" in rendered
    # Plus a Relations block with the contradicts edge.
    assert "## Relations" in rendered
    assert "`coder-a` --[contradicts]--> `coder-b`" in rendered


def test_mos_book_query_surfaces_relations(project: dict[str, Any]) -> None:
    """Query results carry a ``relations`` list of outgoing edges."""
    book_root = project["shared"] / "book"
    _write_contradiction_page(
        book_root,
        page_slug="contradiction-q1",
        new_source="coder-baseline",
        opposing_slug="ethics-flag-canonical",
    )
    index = book_root / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "\n".join(
            [
                "# Book Index",
                "",
                "## Baseline Shootout",
                "slug: coder-baseline",
                "type: source",
                "page_kind: source",
                "book_path: book/sources/coder-baseline.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = book.mos_book_query("baseline", port=project["port"])
    assert result["total"] == 1
    match = result["matches"][0]
    assert match["slug"] == "coder-baseline"
    assert match["relations"] == [
        {
            "to": "ethics-flag-canonical",
            "relation": "contradicts",
            "evidence": "book/contradictions/contradiction-q1.md",
        }
    ]


def test_parse_index_entries_stops_at_relations_section() -> None:
    """The Relations block is edge data, not page entries — must not show
    up as a fake page in the parse output."""
    text = (
        "# Book Index\n\n"
        "## Real Page\n"
        "slug: real-page\n"
        "type: source\n"
        "page_kind: source\n"
        "book_path: book/sources/real-page.md\n\n"
        "## Relations\n\n"
        "- `real-page` --[contradicts]--> `other-page`\n"
    )
    entries = book._parse_index_entries(text)
    assert len(entries) == 1
    assert entries[0]["slug"] == "real-page"
