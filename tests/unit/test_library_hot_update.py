"""Unit tests for the Library hot-cache update surface."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from minions.paths import project_shared_workspace, project_state_dir
from minions.tools import library


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    port = 44567
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    shared = project_shared_workspace(port)
    (shared / "library").mkdir(parents=True)
    project_state_dir(port).mkdir(parents=True)
    _mock_publish_file(monkeypatch)
    return {"port": port, "shared": shared, "library": shared / "library"}


def _mock_publish_file(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    publish_results: list[dict[str, object]] = []

    def fake_publish_file(
        port: int,
        abs_src: Path,
        rel_dst_under_library: str,
        message: str,
    ) -> dict[str, object]:
        assert message == "noter: library hot update"
        dst = project_shared_workspace(port) / "library" / rel_dst_under_library
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_src, dst)
        result: dict[str, object] = {
            "port": port,
            "dst_path": f"library/{rel_dst_under_library}",
            "commit_sha": f"fake-{len(publish_results) + 1}",
        }
        publish_results.append(result)
        return result

    monkeypatch.setattr(library, "_publish_file", fake_publish_file)
    return publish_results


def test_wiki_hot_update_writes_expected_sections(project: dict[str, Any]) -> None:
    result = library.mos_library_hot_update(
        recent_ingests=[
            {
                "title": "Transformer Run",
                "role": "coder",
                "one-line": "Adapter baseline improved exact match.",
            },
            {
                "title": "Ethics Note",
                "source_role": "ethics",
                "takeaway": "Dataset provenance needs one citation.",
            },
        ],
        active_hypotheses=4,
        recently_verified=["adapter sweep improved exact match"],
        recently_refuted=["full fine-tune fits within GPU budget"],
        unresolved_contradictions=2,
        port=project["port"],
    )

    hot = project["library"] / "hot.md"
    content = hot.read_text(encoding="utf-8")
    assert result == {
        "updated": True,
        "bytes": len(content.encode("utf-8")),
        "sections": [
            "Recent activity",
            "Research state",
            "Open contradictions",
            "Library Lint",
        ],
    }
    assert "## Recent activity" in content
    assert "- **Transformer Run** (coder): Adapter baseline improved exact match." in content
    assert "- **Ethics Note** (ethics): Dataset provenance needs one citation." in content
    assert "## Research state" in content
    assert "Active hypotheses: 4" in content
    assert "Verified this cycle: 1" in content
    assert "- adapter sweep improved exact match" in content
    assert "Refuted this cycle: 1" in content
    assert "- full fine-tune fits within GPU budget" in content
    assert "## Open contradictions" in content
    assert "2 unresolved - Ethics reviewing." in content
    assert "<!-- lint-summary-start -->" in content
    assert "<!-- lint-summary-end -->" in content


def test_wiki_hot_update_preserves_existing_lint_block(project: dict[str, Any]) -> None:
    existing = "\n".join(
        [
            "old preface",
            "",
            "<!-- lint-summary-start -->",
            "## Wiki Lint",
            "lint_count: 3",
            "dead_links: 1",
            "<!-- lint-summary-end -->",
            "",
        ]
    )
    (project["library"] / "hot.md").write_text(existing, encoding="utf-8")

    library.mos_library_hot_update(
        recent_ingests=[{"title": "New Source", "role": "coder", "summary": "Fresh result."}],
        active_hypotheses=1,
        unresolved_contradictions=0,
        port=project["port"],
    )

    content = (project["library"] / "hot.md").read_text(encoding="utf-8")
    assert "old preface" not in content
    assert "lint_count: 3" in content
    assert "dead_links: 1" in content
    assert content.count("<!-- lint-summary-start -->") == 1
    assert content.count("<!-- lint-summary-end -->") == 1


def test_wiki_hot_update_caps_hot_cache_at_4kb(project: dict[str, Any]) -> None:
    ingests = [
        {
            "title": f"Source {idx}",
            "role": "coder",
            "one-line": "x" * 1600,
        }
        for idx in range(20)
    ]

    result = library.mos_library_hot_update(recent_ingests=ingests, port=project["port"])

    content = (project["library"] / "hot.md").read_text(encoding="utf-8")
    assert result["bytes"] == len(content.encode("utf-8"))
    assert len(content.encode("utf-8")) <= 4096
    assert "## Recent activity" in content
    assert "## Research state" in content
    assert "## Open contradictions" in content
    assert "<!-- lint-summary-start -->" in content
    assert "Source 0" not in content


def test_wiki_hot_update_empty_inputs_write_minimal_hot_cache(project: dict[str, Any]) -> None:
    result = library.mos_library_hot_update(port=project["port"])

    content = (project["library"] / "hot.md").read_text(encoding="utf-8")
    assert result["updated"] is True
    assert "## Recent activity" in content
    assert "No ingests recorded this cycle." in content
    assert "Active hypotheses: 0" in content
    assert "Verified this cycle: 0" in content
    assert "Refuted this cycle: 0" in content
    assert "0 unresolved - Ethics reviewing." in content
    assert "<!-- lint-summary-start -->" in content
