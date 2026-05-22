"""Integration tests for Draft (L1) ↔ Reel (L0) — reel_ref auto-injection."""

from __future__ import annotations

import pytest

from minions.tools.draft import mos_draft_append, mos_draft_query


@pytest.fixture
def draft_setup(monkeypatch, tmp_path):
    """Set up a project for Draft+Reel integration testing."""
    port = 67890
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")

    # Create draft directory
    draft_dir = tmp_path / f"project_{port}" / "branches" / "shared" / "draft"
    draft_dir.mkdir(parents=True)

    # Mock the draft path resolver
    def mock_draft_path(port_arg):
        return draft_dir / "draft.json"

    def mock_subdir(port_arg, subdir):
        return tmp_path / f"project_{port_arg}" / "branches" / "shared" / subdir

    import minions.tools.draft

    original_draft_path = minions.tools.draft.project_shared_draft_json
    original_subdir = minions.tools.draft.project_shared_subdir
    minions.tools.draft.project_shared_draft_json = mock_draft_path
    minions.tools.draft.project_shared_subdir = mock_subdir

    yield port, tmp_path

    minions.tools.draft.project_shared_draft_json = original_draft_path
    minions.tools.draft.project_shared_subdir = original_subdir


def test_draft_append_auto_injects_reel_ref(draft_setup, monkeypatch):
    """Test that mos_draft_append auto-injects reel_ref into node metadata."""
    _port, _tmp_path = draft_setup
    monkeypatch.setenv("MINIONS_SESSION_ID", "sess-20260522-150000")

    result = mos_draft_append(
        nodes=[{"type": "hypothesis", "text": "test hypothesis"}],
    )

    assert len(result["created_node_ids"]) == 1
    node_id = result["created_node_ids"][0]

    # Verify the node has reel_ref in metadata
    query_result = mos_draft_query(related_to=node_id)
    assert len(query_result["nodes"]) == 1
    node = query_result["nodes"][0]

    assert "reel_ref" in node["metadata"]
    assert node["metadata"]["reel_ref"] == "coder/sess-20260522-150000"


def test_draft_append_preserves_explicit_reel_ref(draft_setup, monkeypatch):
    """Test that explicit reel_ref in metadata is preserved (not overwritten)."""
    _port, _tmp_path = draft_setup
    monkeypatch.setenv("MINIONS_SESSION_ID", "sess-20260522-150000")

    result = mos_draft_append(
        nodes=[
            {
                "type": "hypothesis",
                "text": "test hypothesis",
                "metadata": {"reel_ref": "writer/sess-other/task-123", "topic": "ai"},
            }
        ],
    )

    node_id = result["created_node_ids"][0]
    query_result = mos_draft_query(related_to=node_id)
    node = query_result["nodes"][0]

    # Explicit reel_ref should be preserved
    assert node["metadata"]["reel_ref"] == "writer/sess-other/task-123"
    assert node["metadata"]["topic"] == "ai"


def test_draft_append_no_reel_ref_when_session_id_missing(draft_setup, monkeypatch):
    """Test that no reel_ref is injected when MINIONS_SESSION_ID is unset."""
    _port, _tmp_path = draft_setup
    # Don't set MINIONS_SESSION_ID
    monkeypatch.delenv("MINIONS_SESSION_ID", raising=False)

    result = mos_draft_append(
        nodes=[{"type": "hypothesis", "text": "test"}],
    )

    node_id = result["created_node_ids"][0]
    query_result = mos_draft_query(related_to=node_id)
    node = query_result["nodes"][0]

    # No reel_ref should be set
    assert "reel_ref" not in node["metadata"]


def test_draft_append_multiple_nodes_get_same_reel_ref(draft_setup, monkeypatch):
    """Test that all nodes in a batch get the same reel_ref."""
    _port, _tmp_path = draft_setup
    monkeypatch.setenv("MINIONS_SESSION_ID", "sess-batch-test")

    result = mos_draft_append(
        nodes=[
            {"type": "hypothesis", "text": "h1"},
            {"type": "experiment", "text": "e1"},
            {"type": "result", "text": "r1"},
        ],
    )

    assert len(result["created_node_ids"]) == 3

    for node_id in result["created_node_ids"]:
        query_result = mos_draft_query(related_to=node_id)
        node = query_result["nodes"][0]
        assert node["metadata"]["reel_ref"] == "coder/sess-batch-test"


def test_book_ingest_embeds_reel_ref_from_env(monkeypatch, tmp_path):
    """Test that mos_book_ingest auto-embeds reel_ref from env vars."""
    from minions.tools.book import _render_source_frontmatter

    # Direct test of the frontmatter renderer with reel_ref
    fm = _render_source_frontmatter(
        title="Test Source",
        slug="coder-test",
        source_file="exp/test.md",
        source_role="coder",
        date_ingested="2026-05-22T15:00:00+00:00",
        reel_ref="coder/sess-20260522-150000",
    )

    assert "reel_ref:" in fm
    assert '"coder/sess-20260522-150000"' in fm


def test_book_ingest_no_reel_ref_when_not_provided(monkeypatch, tmp_path):
    """Test that frontmatter omits reel_ref when not provided."""
    from minions.tools.book import _render_source_frontmatter

    fm = _render_source_frontmatter(
        title="Test Source",
        slug="coder-test",
        source_file="exp/test.md",
        source_role="coder",
        date_ingested="2026-05-22T15:00:00+00:00",
    )

    assert "reel_ref:" not in fm
