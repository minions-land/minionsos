"""Unit tests for the Phase 6 Book lint surface."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import pytest

from minions.paths import project_shared_workspace, project_state_dir
from minions.tools import book


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    port = 43456
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    shared = project_shared_workspace(port)
    shared.mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)
    _mock_publish_file(monkeypatch)
    return {"port": port, "shared": shared, "book": shared / "book"}


def _mock_publish_file(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    publish_results: list[dict[str, object]] = []

    def fake_publish_file(
        port: int,
        abs_src: Path,
        rel_dst_under_book: str,
        message: str,
    ) -> dict[str, object]:
        assert message == "ethics: book lint"
        dst = project_shared_workspace(port) / "book" / rel_dst_under_book
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_src, dst)
        result: dict[str, object] = {
            "port": port,
            "dst_path": f"book/{rel_dst_under_book}",
            "commit_sha": f"fake-{len(publish_results) + 1}",
        }
        publish_results.append(result)
        return result

    monkeypatch.setattr(book, "_publish_file", fake_publish_file)

    def fake_publish_files(
        port: int,
        files: list[tuple[Path, str]],
        message: str,
    ) -> dict[str, object]:
        for abs_src, rel in files:
            fake_publish_file(port, abs_src, rel, message)
        return {
            "port": port,
            "dst_paths": [rel for _, rel in files],
            "commit_sha": f"fake-batch-{len(publish_results)}",
        }

    monkeypatch.setattr(book, "_publish_files", fake_publish_files)

    def fake_publish_files(
        port: int,
        files: list[tuple[Path, str]],
        message: str,
    ) -> dict[str, object]:
        for abs_src, rel in files:
            fake_publish_file(port, abs_src, rel, message)
        return {
            "port": port,
            "dst_paths": [rel for _, rel in files],
            "commit_sha": f"fake-batch-{len(publish_results)}",
        }

    monkeypatch.setattr(book, "_publish_files", fake_publish_files)
    return publish_results


def _write_wiki_page(wiki_root: Path, rel_path: str, text: str) -> Path:
    path = wiki_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_source(wiki_root: Path, slug: str, body: str = "Source body.\n") -> Path:
    return _write_wiki_page(
        wiki_root,
        f"sources/{slug}.md",
        "\n".join(
            [
                "---",
                "type: source",
                f'slug: "{slug}"',
                "page_kind: source",
                "---",
                "",
                body.rstrip(),
                "",
            ]
        ),
    )


def _write_contradiction(wiki_root: Path, slug: str, status: str = "unresolved") -> Path:
    return _write_wiki_page(
        wiki_root,
        f"contradictions/contradiction-{slug}.md",
        "\n".join(
            [
                "---",
                "type: contradiction",
                f'slug: "contradiction-{slug}"',
                "page_kind: contradiction",
                f"status: {status}",
                "---",
                "",
                f"# Contradiction: {slug}",
                "",
            ]
        ),
    )


def _findings_for(result: dict[str, object], check: str) -> list[dict[str, object]]:
    findings = result["findings"]
    assert isinstance(findings, list)
    return [
        finding
        for finding in findings
        if isinstance(finding, dict) and finding.get("check") == check
    ]


def _finding_set(result: dict[str, object]) -> set[tuple[object, ...]]:
    findings = result["findings"]
    assert isinstance(findings, list)
    return {
        (
            finding.get("check"),
            finding.get("slug"),
            finding.get("detail"),
            finding.get("wiki_path"),
            finding.get("severity"),
        )
        for finding in findings
        if isinstance(finding, dict)
    }


def test_wiki_lint_no_pages_returns_zero_counts(project: dict[str, Any]) -> None:
    result = book.mos_book_lint()

    assert result["orphan_pages"] == 0
    assert result["dead_links"] == 0
    assert result["missing_concept_pages"] == 0
    assert result["stale_claims"] == 0
    assert result["lint_count"] == 0
    assert result["findings"] == []
    assert "error" not in result


def test_wiki_lint_flags_source_without_inbound_link(project: dict[str, Any]) -> None:
    _write_source(project["book"], "lonely")

    result = book.mos_book_lint()

    assert result["orphan_pages"] == 1
    assert _findings_for(result, "ORPHAN_PAGE") == [
        {
            "check": "ORPHAN_PAGE",
            "slug": "lonely",
            "detail": "No inbound wikilink from another book page.",
            "book_path": "book/sources/lonely.md",
            "severity": "info",
        }
    ]


def test_wiki_lint_flags_dead_wikilink(project: dict[str, Any]) -> None:
    _write_wiki_page(project["book"], "index.md", "# Wiki Index\n\nSee [[nonexistent]].\n")

    result = book.mos_book_lint()

    dead_links = _findings_for(result, "DEAD_LINK")
    assert result["dead_links"] == 1
    assert dead_links[0]["slug"] == "nonexistent"
    assert dead_links[0]["book_path"] == "book/index.md"
    assert dead_links[0]["severity"] == "error"


def test_wiki_lint_flags_repeated_index_title_token(project: dict[str, Any]) -> None:
    _write_wiki_page(
        project["book"],
        "index.md",
        "\n".join(
            [
                "# Book Index",
                "",
                "## Cache alpha",
                "slug: alpha",
                "book_path: book/sources/alpha.md",
                "",
                "## Cache beta",
                "slug: beta",
                "book_path: book/sources/beta.md",
                "",
                "## Cache gamma",
                "slug: gamma",
                "book_path: book/sources/gamma.md",
                "",
            ]
        ),
    )

    result = book.mos_book_lint()

    missing = _findings_for(result, "MISSING_CONCEPT_PAGE")
    assert result["missing_concept_pages"] == 1
    assert missing[0]["slug"] == "cache"
    assert missing[0]["book_path"] == "book/index.md"
    assert missing[0]["severity"] == "info"


def test_wiki_lint_flags_old_unresolved_contradiction(project: dict[str, Any]) -> None:
    page = _write_contradiction(project["book"], "cache")
    old = time.time() - (73 * 60 * 60)
    os.utime(page, (old, old))

    result = book.mos_book_lint()

    stale = _findings_for(result, "STALE_CLAIM")
    assert result["stale_claims"] == 1
    assert stale[0]["slug"] == "contradiction-cache"
    assert stale[0]["book_path"] == "book/contradictions/contradiction-cache.md"
    assert stale[0]["severity"] == "warning"


def test_wiki_lint_does_not_flag_fresh_unresolved_contradiction(
    project: dict[str, Any],
) -> None:
    _write_contradiction(project["book"], "cache")

    result = book.mos_book_lint()

    assert result["stale_claims"] == 0
    assert _findings_for(result, "STALE_CLAIM") == []


def test_wiki_lint_is_idempotent_for_finding_set(project: dict[str, Any]) -> None:
    _write_source(project["book"], "lonely")
    _write_wiki_page(project["book"], "index.md", "# Wiki Index\n\nSee [[missing]].\n")

    first = book.mos_book_lint()
    second = book.mos_book_lint()

    assert _finding_set(second) == _finding_set(first)
    assert second["orphan_pages"] == first["orphan_pages"]
    assert second["dead_links"] == first["dead_links"]
    assert second["missing_concept_pages"] == first["missing_concept_pages"]
    assert second["stale_claims"] == first["stale_claims"]
    assert second["lint_count"] == first["lint_count"]
