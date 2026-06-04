"""Tests for Book Wiki V2 slices A-E.

Slice A: claim-level reel_ref injection
Slice B: two-phase batch ingest
Slice C: compounding queries (save_synthesis)
Slice D-E: Ethics audit walk + verdict resolution
"""

from __future__ import annotations

from typing import Any

import pytest

from minions.tools import book, publish
from minions.tools import book_ingest  # 添加导入以支持正确的mock


@pytest.fixture
def project(tmp_path, monkeypatch, mock_git_operations):
    """Set up a minimal project layout for book tests."""
    port = 19999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "noter")
    monkeypatch.setenv("MINIONS_SESSION_ID", "sess-test-001")
    monkeypatch.setenv("MINIONS_DISABLE_MCP_AUTHZ", "1")

    project_dir = tmp_path / f"project_{port}"
    shared = project_dir / "branches" / "shared"
    (shared / "book" / "sources").mkdir(parents=True)
    (shared / "book" / "contradictions").mkdir(parents=True)
    (shared / "book" / "queries").mkdir(parents=True)
    (shared / "exp" / "exp-1").mkdir(parents=True)
    (shared / "exp" / "exp-2").mkdir(parents=True)
    (shared / "exp" / "exp-3").mkdir(parents=True)
    (project_dir / "state").mkdir(parents=True)
    (shared / "draft").mkdir(parents=True)

    # Mock path functions in multiple places since they're imported at module level
    import minions.paths
    from minions.tools import book_helpers

    def mock_shared_workspace(p):
        return tmp_path / f"project_{p}" / "branches" / "shared"

    def mock_workspace_root(p):
        return tmp_path / f"project_{p}" / "branches"

    # Mock in minions.paths
    monkeypatch.setattr(minions.paths, "project_shared_workspace", mock_shared_workspace)
    monkeypatch.setattr(minions.paths, "project_workspace_root", mock_workspace_root)

    # Mock in book_helpers (already imported from paths)
    monkeypatch.setattr(book_helpers, "project_workspace_root", mock_workspace_root)

    # Mock in publish module (already imported from paths)
    monkeypatch.setattr(publish, "project_shared_workspace", mock_shared_workspace)

    monkeypatch.setattr(
        book, "_book_root", lambda p: tmp_path / f"project_{p}" / "branches" / "shared" / "book"
    )
    monkeypatch.setattr(
        book,
        "project_shared_workspace",
        lambda p: tmp_path / f"project_{p}" / "branches" / "shared",
    )
    monkeypatch.setattr(
        book,
        "project_workspace_root",
        lambda p: tmp_path / f"project_{p}" / "branches",
    )

    # Mock publish to write the file in place without git
    def fake_publish(role, src_path, dst_subpath, commit_message, port):
        from pathlib import Path

        src = Path(src_path)
        dst = tmp_path / f"project_{port}" / "branches" / "shared" / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return {"role": role, "dst_subpath": dst_subpath, "commit": "fake"}

    def fake_publish_files(role, files, commit_message, port):
        from pathlib import Path

        for entry in files:
            src = Path(entry["src_path"])
            dst = tmp_path / f"project_{port}" / "branches" / "shared" / entry["dst_subpath"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "role": role,
            "dst_paths": [e["dst_subpath"] for e in files],
            "commit_sha": "fake",
        }

    monkeypatch.setattr(publish, "mos_publish_to_shared", fake_publish)
    monkeypatch.setattr(book_ingest, "mos_publish_files_to_shared", fake_publish_files)

    # Mock is_git_work_tree to avoid git checks in publish module
    monkeypatch.setattr(publish, "is_git_work_tree", lambda p: True)

    return {"port": port, "tmp": tmp_path, "shared": shared}


# ── Slice A: claim-level reel_ref ───────────────────────────────────────


def test_slice_a_claim_level_reel_ref_injected_by_default(project: dict[str, Any]) -> None:
    """Every substantive line in body gets the page-default reel_ref appended."""
    src = project["shared"] / "exp" / "exp-1" / "report.md"
    src.write_text(
        "# Experiment 1\n\nThe model achieves 85% accuracy.\nLoss converges by step 1000.\n"
    )

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="The model achieves 85% accuracy.\nLoss converges by step 1000.\n",
    )

    page_text = (project["shared"] / "book" / "sources" / "coder-exp-1.md").read_text()
    assert "^[noter/sess-test-001]" in page_text
    assert page_text.count("^[noter/sess-test-001]") == 2  # two claim lines


def test_slice_a_claim_refs_override_page_default(project: dict[str, Any]) -> None:
    """`claim_refs` dict overrides page-default ref for matching sentence prefixes."""
    src = project["shared"] / "exp" / "exp-1" / "report.md"
    src.write_text("# Test")

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="The model achieves 85% accuracy.\nLoss converges by step 1000.\n",
        reel_ref="coder/sess-A/task-default",
        claim_refs={"The model achieves": "coder/sess-A/task-accuracy-eval"},
    )

    page_text = (project["shared"] / "book" / "sources" / "coder-exp-1.md").read_text()
    assert "^[coder/sess-A/task-accuracy-eval]" in page_text
    assert "^[coder/sess-A/task-default]" in page_text  # default for the second line


def test_slice_a_already_present_ref_not_overwritten(project: dict[str, Any]) -> None:
    """Lines already carrying ^[ref] are not modified."""
    src = project["shared"] / "exp" / "exp-1" / "report.md"
    src.write_text("# Test")

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="The model achieves 85% accuracy. ^[manual/explicit/ref]\nLoss converges.\n",
        reel_ref="coder/sess-A/task-default",
    )

    page_text = (project["shared"] / "book" / "sources" / "coder-exp-1.md").read_text()
    assert "^[manual/explicit/ref]" in page_text
    # The default should not be appended to the line that already has a ref
    assert "85% accuracy. ^[manual/explicit/ref] ^[coder" not in page_text


# ── Slice B: batch ingest with order-independent contradiction detection ──


def test_slice_b_batch_ingest_finds_in_batch_contradictions(
    project: dict[str, Any],
) -> None:
    """Two sources contradicting each other in the same batch are detected,
    regardless of which is processed first."""
    src_a = project["shared"] / "exp" / "exp-1" / "report.md"
    src_a.write_text("# A")
    src_b = project["shared"] / "exp" / "exp-2" / "report.md"
    src_b.write_text("# B")

    result = book.mos_book_ingest_batch(
        sources=[
            {
                "src_path": "exp/exp-1/report.md",
                "source_role": "coder",
                "source_slug": "exp-1",
                "summary": (
                    "The transformer model is highly effective for sequence classification.\n"
                ),
            },
            {
                "src_path": "exp/exp-2/report.md",
                "source_role": "ethics",
                "source_slug": "exp-2",
                "summary": (
                    "The transformer model is not effective for sequence classification.\n"
                ),
            },
        ],
        port=project["port"],
    )

    # At least one of the two should detect the other
    assert result["total_contradictions"] >= 1
    found_pages = [r["contradiction_path"] for r in result["ingested"] if r["contradiction_path"]]
    assert found_pages, f"Expected at least one contradiction page, got {result}"


def test_slice_b_batch_ingest_returns_per_source_results(
    project: dict[str, Any],
) -> None:
    """Each entry in the batch returns its own ingest result."""
    for i in range(1, 4):
        d = project["shared"] / "exp" / f"exp-{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.md").write_text(f"# Exp {i}")

    result = book.mos_book_ingest_batch(
        sources=[
            {
                "src_path": f"exp/exp-{i}/report.md",
                "source_role": "coder",
                "source_slug": f"exp-{i}",
                "summary": f"Result {i}: independent finding number {i}.\n",
            }
            for i in range(1, 4)
        ],
        port=project["port"],
    )

    assert len(result["ingested"]) == 3
    for entry in result["ingested"]:
        assert "slug" in entry
        assert "book_path" in entry
        assert entry["book_path"].startswith("book/sources/")


# ── Slice C: compounding queries ────────────────────────────────────────


def test_slice_c_save_synthesis_writes_query_page(project: dict[str, Any]) -> None:
    """A role's synthesized answer becomes a queryable Book page."""
    result = book.mos_book_save_synthesis(
        question="What is the model's accuracy?",
        answer="Based on experiments exp-1 and exp-2, the model achieves 85% on the test set.",
        sources=["book/sources/coder-exp-1.md", "book/sources/coder-exp-2.md"],
        port=project["port"],
    )

    assert result["book_path"].startswith("book/queries/")
    page_path = project["shared"] / result["book_path"]
    page_text = page_path.read_text()
    assert "type: query" in page_text
    assert "question:" in page_text
    assert "Based on experiments exp-1 and exp-2" in page_text


def test_slice_c_save_synthesis_compounds_with_subsequent_query(
    project: dict[str, Any],
) -> None:
    """A saved synthesis appears in subsequent query results."""
    book.mos_book_save_synthesis(
        question="What is the convergence behavior?",
        answer="The loss converges by step 1000 across all experiments.",
        sources=["book/sources/coder-exp-1.md"],
        port=project["port"],
        slug="convergence-behavior",
    )

    query_result = book.mos_book_query("convergence", port=project["port"])
    assert query_result["total"] >= 1
    slugs = [m["slug"] for m in query_result["matches"]]
    assert "convergence-behavior" in slugs


def test_slice_c_query_returns_status_field(project: dict[str, Any]) -> None:
    """`mos_book_query` with `include_status=True` (default) returns a status field."""
    book.mos_book_save_synthesis(
        question="What is X?",
        answer="X is described as Y.",
        port=project["port"],
        slug="what-is-x",
    )
    query_result = book.mos_book_query("what is x", port=project["port"])
    assert query_result["matches"]
    assert "status" in query_result["matches"][0]


# ── Slice D-E: Ethics audit walk + verdict ──────────────────────────────


def test_slice_d_audit_walk_finds_unresolved_contradictions(
    project: dict[str, Any],
) -> None:
    """audit_walk surfaces every page with status=unresolved."""
    # Plant two sources that contradict, generating a contradiction page
    src_a = project["shared"] / "exp" / "exp-1" / "report.md"
    src_a.write_text("# A")
    src_b = project["shared"] / "exp" / "exp-2" / "report.md"
    src_b.write_text("# B")

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="The transformer model is highly accurate on the held-out test data set.\n",
        reel_ref="coder/sess-X/task-acc",
    )
    book.mos_book_ingest(
        src_path="exp/exp-2/report.md",
        source_role="ethics",
        source_slug="exp-2",
        port=project["port"],
        summary="The transformer model is not accurate on the held-out test data set.\n",
        reel_ref="ethics/sess-Y/task-audit",
    )

    walk_result = book.mos_book_audit_walk(port=project["port"])
    assert walk_result["queue_depth"] >= 1
    item = walk_result["audit_queue"][0]
    assert item["status"] == "unresolved"
    assert len(item["reel_refs"]) >= 1


def test_slice_e_resolve_contradiction_flips_status(
    project: dict[str, Any],
) -> None:
    """Ethics writes a verdict; page status changes from unresolved to resolved."""
    src_a = project["shared"] / "exp" / "exp-1" / "report.md"
    src_a.write_text("# A")
    src_b = project["shared"] / "exp" / "exp-2" / "report.md"
    src_b.write_text("# B")

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="The benchmark clearly shows the system is much faster than the baseline.\n",
    )
    book.mos_book_ingest(
        src_path="exp/exp-2/report.md",
        source_role="ethics",
        source_slug="exp-2",
        port=project["port"],
        summary="The benchmark clearly shows the system is not faster than the baseline.\n",
    )

    # Find the contradiction page
    walk = book.mos_book_audit_walk(port=project["port"])
    assert walk["queue_depth"] >= 1
    slug = walk["audit_queue"][0]["slug"]

    result = book.mos_book_resolve_contradiction(
        slug=slug,
        verdict="resolved",
        rationale=(
            "Both reports are correct in different evaluation conditions; "
            "exp-1 used GPU baseline, exp-2 used CPU. Verdict: contextual, "
            "not a true contradiction."
        ),
        port=project["port"],
        auditor_role="ethics",
    )

    assert result["verdict"] == "resolved"
    assert result["status"] == "resolved"

    # Verify status in file
    page_path = project["shared"] / "book" / "contradictions" / f"{slug}.md"
    if not page_path.exists():
        # Try canonical-form slug
        page_path = project["shared"] / "book" / "contradictions" / f"contradiction-{slug}.md"
    text = page_path.read_text()
    assert "status: " in text
    assert "## Verdict (resolved)" in text
    assert "ethics" in text


def test_slice_e_resolve_supports_alternate_verdicts(
    project: dict[str, Any],
) -> None:
    """Verdicts beyond 'resolved' are honored (superseded, out_of_scope)."""
    src_a = project["shared"] / "exp" / "exp-1" / "report.md"
    src_a.write_text("# A")
    src_b = project["shared"] / "exp" / "exp-2" / "report.md"
    src_b.write_text("# B")

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="The system is fully autonomous and operates without any oversight.\n",
    )
    book.mos_book_ingest(
        src_path="exp/exp-2/report.md",
        source_role="ethics",
        source_slug="exp-2",
        port=project["port"],
        summary="The system is not fully autonomous and requires constant oversight.\n",
    )

    walk = book.mos_book_audit_walk(port=project["port"])
    slug = walk["audit_queue"][0]["slug"]

    result = book.mos_book_resolve_contradiction(
        slug=slug,
        verdict="out_of_scope",
        rationale="This dispute concerns deployment policy, not technical accuracy.",
        port=project["port"],
        auditor_role="ethics",
    )
    assert result["verdict"] == "out_of_scope"
    assert result["status"] == "out_of_scope"


def test_slice_d_walk_filter_returns_only_matching_status(
    project: dict[str, Any],
) -> None:
    """`status_filter=None` should return all pages with reel refs."""
    src = project["shared"] / "exp" / "exp-1" / "report.md"
    src.write_text("# A")

    book.mos_book_ingest(
        src_path="exp/exp-1/report.md",
        source_role="coder",
        source_slug="exp-1",
        port=project["port"],
        summary="A solo source with no contradiction.\n",
        reel_ref="coder/sess-X/task-1",
    )

    # Filter unresolved → no contradictions exist, queue empty
    walk_unresolved = book.mos_book_audit_walk(status_filter="unresolved", port=project["port"])
    assert walk_unresolved["queue_depth"] == 0

    # No filter → the source page returns even though status is empty
    walk_any = book.mos_book_audit_walk(status_filter=None, port=project["port"])
    assert walk_any["queue_depth"] >= 1
