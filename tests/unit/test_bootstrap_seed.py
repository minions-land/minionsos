"""Unit tests for Draft bootstrap seeding at project creation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.lifecycle.project import project_create
from minions.paths import project_shared_draft_json
from minions.state.store import StateStore


@pytest.fixture
def mock_project_env(tmp_path: Path, monkeypatch, mock_git_operations):
    """Mock project environment for bootstrap testing.

    Returns ``(projects_root, state_root)``. ``state_root`` holds an isolated
    ``projects.json`` so ``StateStore(root=state_root)`` never touches the real
    ``minions/state/projects.json`` — a bare ``StateStore()`` reads the live
    state dir (``MINIONS_PROJECTS_ROOT`` does not redirect it), which exhausts
    the port range once enough real projects exist and makes this test fail for
    reasons unrelated to bootstrap seeding.
    """
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(tmp_path / "author_repo"))
    state_root = tmp_path / "state"
    state_root.mkdir()

    # Create minimal author repo
    author_repo = tmp_path / "author_repo"
    author_repo.mkdir()
    import subprocess

    subprocess.run(["git", "init"], cwd=author_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=author_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=author_repo,
        check=True,
        capture_output=True,
    )
    (author_repo / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=author_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=author_repo,
        check=True,
        capture_output=True,
    )

    return tmp_path, state_root


def test_project_create_seeds_bootstrap_node(mock_project_env: tuple[Path, Path]):
    """project_create should seed Draft with B-000 bootstrap node."""
    _projects_root, state_root = mock_project_env
    store = StateStore(root=state_root)

    entry = project_create(
        real_name="test-bootstrap",
        brief="Test project for bootstrap seeding",
        topic_doc="input/test.md",
        profile="scientific-paper",
        store=store,
    )

    # Draft should exist
    draft_path = project_shared_draft_json(entry.port)
    assert draft_path.exists()

    # Load and verify structure
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["project_port"] == entry.port
    assert (
        draft["root_question"]
        == "Test project for bootstrap seeding\n\nTopic document: input/test.md"
    )
    assert len(draft["nodes"]) == 1
    assert len(draft["edges"]) == 0

    # Verify bootstrap node
    bootstrap = draft["nodes"][0]
    assert bootstrap["id"] == "B-000"
    assert bootstrap["type"] == "bootstrap"
    assert (
        bootstrap["text"] == "Test project for bootstrap seeding\n\nTopic document: input/test.md"
    )
    assert bootstrap["support_status"] == "verified"
    assert bootstrap["author_role"] == "system"
    assert bootstrap["provenance"] == "system"
    assert bootstrap["confidence"] == 1.0

    # Verify metadata
    metadata = bootstrap["metadata"]
    assert metadata["profile"] == "scientific-paper"
    assert "gru" in metadata["roles_expected"]
    assert "expert" in metadata["roles_expected"]
    assert "ethics" in metadata["roles_expected"]
    assert "noter" not in metadata["roles_expected"]
    assert metadata["topic_doc"] == "input/test.md"
    assert metadata["real_name"] == "test-bootstrap"
    assert "deliverable" in metadata


def test_bootstrap_node_without_brief(mock_project_env: tuple[Path, Path]):
    """Bootstrap should use project name when brief is not provided."""
    _projects_root, state_root = mock_project_env
    store = StateStore(root=state_root)

    entry = project_create(
        real_name="no-brief-project",
        profile="scientific-paper",
        store=store,
    )

    draft_path = project_shared_draft_json(entry.port)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    bootstrap = draft["nodes"][0]
    assert bootstrap["text"] == "Project: no-brief-project"
    assert draft["root_question"] == "Project: no-brief-project"


def test_bootstrap_node_has_correct_type_prefix():
    """Bootstrap node type should map to 'B' prefix."""
    from minions.tools.draft import TYPE_PREFIX

    assert "bootstrap" in TYPE_PREFIX
    assert TYPE_PREFIX["bootstrap"] == "B"


def test_bootstrap_decay_half_life():
    """Bootstrap nodes should have very long decay (effectively never decay)."""
    from minions.tools.draft import DECAY_HALF_LIFE_DAYS

    assert "bootstrap" in DECAY_HALF_LIFE_DAYS
    assert DECAY_HALF_LIFE_DAYS["bootstrap"] >= 9999.0
