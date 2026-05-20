"""Unit tests for the Phase 2 Library Layer 2 surface."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from minions.errors import ProjectError
from minions.paths import project_shared_branch_name, project_shared_workspace, project_state_dir
from minions.tools import publish, library


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    port = 41234
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    shared = project_shared_workspace(port)
    (shared / "coder").mkdir(parents=True)
    (shared / "library" / "sources").mkdir(parents=True)
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
        assert role == "noter"
        assert commit_message.startswith("noter: ingest ")
        resolved_port = port or library._env_port()
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

    monkeypatch.setattr(library, "mos_publish_to_shared", fake_publish_to_shared)
    return publish_results


def test_wiki_ingest_creates_page_index_and_log(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_results = _mock_publish(monkeypatch)
    source = project["shared"] / "coder" / "artifact.md"
    source.write_text("\n".join(f"line {idx}" for idx in range(1, 205)) + "\n", encoding="utf-8")

    result = library.mos_library_ingest(
        src_path=str(source),
        source_role="coder",
        source_slug="transformer-run",
        title="Transformer Result",
        port=project["port"],
    )

    page = project["shared"] / "library" / "sources" / "coder-transformer-run.md"
    assert page.exists()
    page_lines = page.read_text(encoding="utf-8").splitlines()
    assert page_lines[:10] == [
        "---",
        "type: source",
        'title: "Transformer Result"',
        'slug: "coder-transformer-run"',
        'source_file: "shared/coder/artifact.md"',
        'source_role: "coder"',
        page_lines[6],
        "page_kind: source",
        "confidence: high",
        "---",
    ]
    assert page_lines[6].startswith('date_ingested: "')
    assert "line 200" in page_lines
    assert "line 201" not in page_lines

    index = (project["shared"] / "library" / "index.md").read_text(encoding="utf-8")
    assert "## Transformer Result" in index
    assert "slug: coder-transformer-run" in index
    assert "library_path: library/sources/coder-transformer-run.md" in index

    log_path = project["shared"] / "library" / "log.md"
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["op"] == "ingest"
    assert rows[0]["slug"] == "coder-transformer-run"
    assert rows[0]["source_file"] == "shared/coder/artifact.md"

    assert result["slug"] == "coder-transformer-run"
    assert result["library_path"] == "library/sources/coder-transformer-run.md"
    assert result["indexed"] is True
    assert result["logged"] is True
    assert len(result["publish_results"]) == 3
    assert len(publish_results) == 3


def test_wiki_ingest_is_idempotent_for_index_entries(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_results = _mock_publish(monkeypatch)
    source = project["shared"] / "coder" / "artifact.md"
    source.write_text("first version\n", encoding="utf-8")

    library.mos_library_ingest(str(source), "coder", "same-slug", title="First", port=project["port"])
    source.write_text("second version\n", encoding="utf-8")
    result = library.mos_library_ingest(
        str(source),
        "coder",
        "same-slug",
        title="Second",
        port=project["port"],
    )

    index = (project["shared"] / "library" / "index.md").read_text(encoding="utf-8")
    assert index.count("slug: coder-same-slug") == 1
    assert "## Second" in index
    assert len(result["publish_results"]) == 3
    assert len(publish_results) == 6


def test_wiki_ingest_missing_source_raises(project: dict[str, Any]) -> None:
    missing = project["shared"] / "coder" / "missing.md"
    with pytest.raises(library.LibraryError, match="src_path does not exist"):
        library.mos_library_ingest(str(missing), "coder", "missing", port=project["port"])


def test_wiki_query_returns_matching_index_entry(project: dict[str, Any]) -> None:
    index = project["shared"] / "library" / "index.md"
    index.write_text(
        "\n".join(
            [
                "# Library Index",
                "",
                "## Transformer Architecture",
                "slug: coder-transformer",
                "type: source",
                "page_kind: source",
                "library_path: library/sources/coder-transformer.md",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = library.mos_library_query("transformer", port=project["port"])
    assert result["total"] == 1
    assert result["matches"] == [
        {
            "slug": "coder-transformer",
            "title": "Transformer Architecture",
            "page_kind": "source",
            "library_path": "library/sources/coder-transformer.md",
            "score": 1,
        }
    ]


def test_wiki_query_returns_empty_when_no_entries_match(project: dict[str, Any]) -> None:
    index = project["shared"] / "library" / "index.md"
    index.write_text(
        "\n".join(
            [
                "# Wiki Index",
                "",
                "## Transformer Architecture",
                "slug: coder-transformer",
                "type: source",
                "page_kind: source",
                "wiki_path: wiki/sources/coder-transformer.md",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = library.mos_library_query("optimizer", port=project["port"])
    assert result == {"matches": [], "total": 0, "queried": "optimizer"}


def test_wiki_hot_get_absent(project: dict[str, Any]) -> None:
    assert library.mos_library_hot_get(port=project["port"]) == {
        "content": "",
        "exists": False,
        "bytes": 0,
    }


def test_wiki_hot_get_reads_existing_file(project: dict[str, Any]) -> None:
    hot = project["shared"] / "library" / "hot.md"
    content = "Current focus: transformer ablation.\n"
    hot.write_text(content, encoding="utf-8")

    assert library.mos_library_hot_get(port=project["port"]) == {
        "content": content,
        "exists": True,
        "bytes": len(content.encode("utf-8")),
    }


def test_publish_policy_rejects_ethics_library() -> None:
    with pytest.raises(ProjectError, match="may not publish under branches/shared"):
        publish._validate_dst("ethics", "library/audit.md")


def test_publish_policy_allows_noter_library() -> None:
    assert publish._validate_dst("noter", "library/sources/source.md") == Path(
        "library/sources/source.md"
    )
