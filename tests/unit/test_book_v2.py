"""Tests for Book V2 schema: status, paper_role, ratify, open_question, dead_end."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import book_special
from minions.tools.book import (
    BookError,
    mos_book_dead_end,
    mos_book_ingest,
    mos_book_open_question,
    mos_book_query,
    mos_book_ratify,
)

# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def book_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Set up a minimal project layout and return its port."""
    port = 19991
    shared = tmp_path / f"project_{port}" / "branches" / "main"
    for subdir in (
        "book/sources",
        "book/contradictions",
        "book/queries",
        "book/open_questions",
        "state",
    ):
        (shared / subdir).mkdir(parents=True, exist_ok=True)
    (shared / "book" / "index.md").write_text("", encoding="utf-8")
    (shared / "book" / "log.md").write_text("", encoding="utf-8")
    (shared / "state" / "shared.lock").write_text("", encoding="utf-8")

    # Mock mos_publish_to_shared for book_special module
    def _fake_publish_to_shared(
        *, role, src_path, dst_subpath, commit_message, port=None, **kwargs
    ):
        import shutil

        from minions.tools.book_helpers import _book_root

        book_root = _book_root(port)
        src = Path(src_path)
        dst = book_root / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return {
            "port": port,
            "role": role,
            "dst_path": dst_subpath,
            "commit_sha": "fake-sha",
            "pushed": False,
            "push_branch": None,
            "branch": "main",
        }

    monkeypatch.setattr(book_special, "mos_publish_to_shared", _fake_publish_to_shared)

    # Mock mos_publish_files_to_shared for book_special module (dead_end, open_question)
    def _fake_publish_files_for_special(*, role, files, commit_message, port=None, **kwargs):
        import shutil

        dst_paths = []
        for entry in files:
            src = Path(entry["src_path"])
            dst_subpath = entry["dst_subpath"]
            # dst_subpath is like "book/sources/dead-end-x.md" or "book/index.md"
            dst = shared / dst_subpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            dst_paths.append(dst_subpath)

        return {
            "port": port,
            "role": role,
            "dst_paths": dst_paths,
            "commit_sha": "fake-sha",
            "pushed": False,
            "push_branch": None,
            "branch": "main",
        }

    monkeypatch.setattr(
        book_special, "mos_publish_files_to_shared", _fake_publish_files_for_special
    )

    # Mock mos_publish_files_to_shared for book_ingest module
    def _fake_publish_files(*, role, files, commit_message, port=None, **kwargs):
        import shutil

        dst_paths = []
        for entry in files:
            src = Path(entry["src_path"])
            dst_subpath = entry["dst_subpath"]
            # dst_subpath is like "book/sources/expert-dummy.md"
            # We need to put it under shared/
            dst = shared / dst_subpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            dst_paths.append(dst_subpath)

        return {
            "port": port,
            "role": role,
            "dst_paths": dst_paths,
            "commit_sha": "fake-sha",
            "pushed": False,
            "push_branch": None,
            "branch": "main",
        }

    from minions.tools import book_ingest

    monkeypatch.setattr(book_ingest, "mos_publish_files_to_shared", _fake_publish_files)

    # Mock _publish_files in book_promote module for ratify
    from minions.tools import book_promote

    def _fake_promote_publish_files(port, files, message):
        import shutil

        dst_paths = []
        for src_path, rel_dst in files:
            # rel_dst is like "sources/slug.md" or "log.md"
            dst = shared / "book" / rel_dst
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst)
            dst_paths.append(f"book/{rel_dst}")
        return {
            "port": port,
            "dst_paths": dst_paths,
            "commit_sha": "fake-sha",
            "pushed": False,
        }

    monkeypatch.setattr(book_promote, "_publish_files", _fake_promote_publish_files)

    monkeypatch.setenv("MINIONS_PORT", str(port))
    # MINIONS_PROJECTS_ROOT points directly at tmp_path so project_dir(port)
    # resolves to tmp_path/project_{port}.
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    return port


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_dead_end_creates_page_with_refuted_status(book_project: int, tmp_path: Path) -> None:
    """mos_book_dead_end creates a page with status: refuted."""
    result = mos_book_dead_end(
        "Gradient descent diverges on sparse inputs",
        "Three experiments (exp-01, exp-02, exp-03) all showed NaN loss by epoch 5.",
        port=book_project,
    )
    assert result["book_path"].startswith("book/sources/dead-end-")
    page_path = tmp_path / f"project_{book_project}" / "branches" / "main" / result["book_path"]
    assert page_path.exists()
    content = page_path.read_text(encoding="utf-8")
    assert 'status: "refuted"' in content or "status: refuted" in content
    assert "MUST NEVER BE DELETED" in content or "refuted" in content


def test_dead_end_requires_non_empty_claim(book_project: int) -> None:
    with pytest.raises(BookError, match="claim"):
        mos_book_dead_end("", "some evidence", port=book_project)


def test_dead_end_requires_non_empty_evidence(book_project: int) -> None:
    with pytest.raises(BookError, match="refutation_evidence"):
        mos_book_dead_end("Some claim", "", port=book_project)


def test_open_question_creates_page(book_project: int, tmp_path: Path) -> None:
    """mos_book_open_question creates a page with status: open_question."""
    result = mos_book_open_question(
        "Does attention sink emerge in SSM architectures?",
        related_pages=["book/sources/ssm-baseline.md"],
        port=book_project,
    )
    assert result["book_path"].startswith("book/open_questions/")
    page_path = tmp_path / f"project_{book_project}" / "branches" / "main" / result["book_path"]
    assert page_path.exists()
    content = page_path.read_text(encoding="utf-8")
    assert "status: open_question" in content
    assert "SSM" in content or "attention" in content.lower()


def test_ratify_requires_ethics_role(book_project: int, tmp_path: Path) -> None:
    """mos_book_ratify rejects non-ethics callers."""
    # First ingest a page so there is something to ratify.
    shared = tmp_path / f"project_{book_project}" / "branches" / "main"
    src = shared / "dummy.md"
    src.write_text("# Dummy\n\nSome content.", encoding="utf-8")
    ingest_result = mos_book_ingest(
        src_path=str(src),
        source_role="expert",
        source_slug="dummy-ratify-test",
        port=book_project,
    )
    slug = ingest_result["slug"]
    with pytest.raises(BookError, match="Ethics-only"):
        mos_book_ratify(slug, "Some evidence review.", ratifier_role="expert", port=book_project)


def test_ratify_updates_frontmatter(book_project: int, tmp_path: Path) -> None:
    """mos_book_ratify sets ratified_by: ethics and appends Ratification section."""
    shared = tmp_path / f"project_{book_project}" / "branches" / "main"
    src = shared / "ratify-me.md"
    src.write_text("# Finding\n\nCritical result.", encoding="utf-8")
    ingest_result = mos_book_ingest(
        src_path=str(src),
        source_role="expert",
        source_slug="ratify-me",
        port=book_project,
    )
    slug = ingest_result["slug"]
    result = mos_book_ratify(
        slug,
        "Evidence is sound; three independent replications confirmed.",
        ratifier_role="ethics",
        port=book_project,
    )
    assert result["slug"] == slug
    page_path = tmp_path / f"project_{book_project}" / "branches" / "main" / result["book_path"]
    content = page_path.read_text(encoding="utf-8")
    assert 'ratified_by: "ethics"' in content or "ratified_by: ethics" in content
    assert "## Ratification" in content
    assert "three independent replications" in content


def test_query_status_filter(book_project: int, tmp_path: Path) -> None:
    """mos_book_query status_filter only returns pages matching that status."""
    # Create a refuted dead-end page.
    mos_book_dead_end(
        "This approach is broken",
        "Experiment shows 100% failure rate.",
        slug="broken-approach",
        port=book_project,
    )
    # Query without filter — should find it.
    results_all = mos_book_query("broken approach", max_pages=10, port=book_project)
    assert results_all["total"] >= 1

    # Query with status_filter=refuted — should still find it.
    results_refuted = mos_book_query(
        "broken approach", max_pages=10, status_filter="refuted", port=book_project
    )
    assert results_refuted["total"] >= 1
    for m in results_refuted["matches"]:
        assert m["status"] == "refuted"

    # Query with status_filter=verified — should NOT find it.
    results_verified = mos_book_query(
        "broken approach", max_pages=10, status_filter="verified", port=book_project
    )
    for m in results_verified["matches"]:
        assert m["status"] == "verified"


def test_query_returns_paper_role_and_motif_kind(book_project: int, tmp_path: Path) -> None:
    """mos_book_query always returns paper_role, motif_kind, ratified_by fields."""
    shared = tmp_path / f"project_{book_project}" / "branches" / "main"
    src = shared / "simple.md"
    src.write_text("# Simple\n\nA finding.", encoding="utf-8")
    mos_book_ingest(
        src_path=str(src),
        source_role="expert",
        source_slug="simple-finding",
        port=book_project,
    )
    results = mos_book_query("simple finding", max_pages=5, port=book_project)
    assert results["total"] >= 1
    match = results["matches"][0]
    # Fields must be present (may be empty strings).
    assert "paper_role" in match
    assert "motif_kind" in match
    assert "ratified_by" in match
