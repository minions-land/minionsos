"""Unit tests for adjudication layer (mos_adjudicate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.tools.adjudicator import (
    AdjudicateArgs,
    _extract_confidence,
    _extract_decision,
    _extract_evidence_refs,
    mos_adjudicate,
    set_spawner,
)


@pytest.fixture
def mock_adjudication_project(tmp_path: Path, monkeypatch):
    """Create a minimal project structure for adjudication testing."""
    port = 9998
    project_root = tmp_path / f"project_{port}"
    project_root.mkdir()

    # Create meta.json with hle-answer profile
    meta = {
        "port": port,
        "real_name": "test-adjudicate",
        "profile": "hle-answer",
        "profile_evaluation": {
            "strategy": "answer_grader",
            "reference_path": "input/expected.json",
            "comparison_mode": "exact_match",
            "adjudication": {"depth": "panel"},
        },
    }
    meta_path = project_root / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Create input/expected.json
    input_dir = project_root / "input"
    input_dir.mkdir()
    expected = {"answer": 42}
    (input_dir / "expected.json").write_text(json.dumps(expected), encoding="utf-8")

    # Create branches/shared/submissions/
    shared_dir = project_root / "branches" / "shared"
    submissions_dir = shared_dir / "submissions"
    submissions_dir.mkdir(parents=True)

    # Create state/shared.lock for publish tool
    state_dir = project_root / "state"
    state_dir.mkdir()
    (state_dir / "shared.lock").touch()

    # Path helpers
    def mock_project_dir(p: int) -> Path:
        return project_root

    def mock_project_meta_json(p: int) -> Path:
        return meta_path

    def mock_project_shared_subdir(p: int, subdir: str) -> Path:
        return shared_dir / subdir

    def mock_project_shared_workspace(p: int) -> Path:
        return shared_dir

    def mock_project_reviews_dir(p: int) -> Path:
        return shared_dir / "reviews"

    import minions.paths

    monkeypatch.setattr(minions.paths, "project_dir", mock_project_dir)
    monkeypatch.setattr(minions.paths, "project_meta_json", mock_project_meta_json)
    monkeypatch.setattr(minions.paths, "project_shared_subdir", mock_project_shared_subdir)
    monkeypatch.setattr(minions.paths, "project_shared_workspace", mock_project_shared_workspace)
    monkeypatch.setattr(minions.paths, "project_reviews_dir", mock_project_reviews_dir)

    # Mock git operations
    class MockResult:
        returncode = 0
        stdout = "abc123\n"
        stderr = ""

    def mock_run(*args, **kwargs):
        return MockResult()

    import subprocess

    monkeypatch.setattr(subprocess, "run", mock_run)

    return port, project_root


def test_adjudicate_depth_none_skips(mock_adjudication_project):
    """depth=none should skip adjudication."""
    port, _project_root = mock_adjudication_project

    args = AdjudicateArgs(port=port, depth="none")
    result = mos_adjudicate(args)

    assert result["status"] == "skipped"
    assert result["reason"] == "depth=none"


def test_adjudicate_missing_submission(mock_adjudication_project):
    """Missing submission should error."""
    port, _project_root = mock_adjudication_project

    args = AdjudicateArgs(port=port, depth="single")
    result = mos_adjudicate(args)

    assert result["status"] == "error"
    assert "answer.json not found" in result["reason"]


def test_adjudicate_single_spawns_one_instance(mock_adjudication_project):
    """depth=single should spawn 1 adjudicator instance."""
    port, project_root = mock_adjudication_project

    # Create submission
    submission_path = project_root / "branches" / "shared" / "submissions" / "answer.json"
    submission_path.write_text(json.dumps({"answer": 42}), encoding="utf-8")

    spawned_prompts: list[str] = []

    def fake_spawner(*, workspace: Path, prompt: str, timeout: int, lock_label=None):
        spawned_prompts.append(prompt)
        # Write the expected outputs
        round_dir = project_root / "branches" / "shared" / "reviews" / "round-1"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "aspect-notes").mkdir(exist_ok=True)

        if "adjudicator 1" in prompt:
            (round_dir / "reviewer-1.md").write_text(
                "# Adjudicator 1\n\n## Decision\n\nAccept\n\nConfidence: 0.9\n", encoding="utf-8"
            )
        elif "finishing adjudication" in prompt:
            consolidated = round_dir / "consolidated.md"
            consolidated.write_text(
                "# Consolidated\n\n## Decision\n\nAccept\n\nConfidence: 0.9\n\n## Evidence Refs\n\n- ref1\n",
                encoding="utf-8",
            )
            summary_dir = project_root / "branches" / "shared" / "reviews" / "summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            (summary_dir / "round-1.md").write_text("# Summary\n\nAccept\n", encoding="utf-8")
        return True, None

    original_spawner = set_spawner(fake_spawner)
    try:
        args = AdjudicateArgs(port=port, depth="single")
        result = mos_adjudicate(args)

        assert result["status"] == "completed"
        assert result["decision"] == "Accept"
        assert result["confidence"] == 0.9
        assert len(spawned_prompts) == 2  # 1 adjudicator + 1 consolidation
        assert "adjudicator 1" in spawned_prompts[0]
    finally:
        set_spawner(original_spawner)


def test_adjudicate_panel_spawns_three_instances(mock_adjudication_project):
    """depth=panel should spawn 3 adjudicator instances."""
    port, project_root = mock_adjudication_project

    # Create submission
    submission_path = project_root / "branches" / "shared" / "submissions" / "answer.json"
    submission_path.write_text(json.dumps({"answer": 42}), encoding="utf-8")

    spawned_prompts: list[str] = []

    def fake_spawner(*, workspace: Path, prompt: str, timeout: int, lock_label=None):
        spawned_prompts.append(prompt)
        round_dir = project_root / "branches" / "shared" / "reviews" / "round-1"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "aspect-notes").mkdir(exist_ok=True)

        for i in range(1, 4):
            if f"adjudicator {i}" in prompt:
                (round_dir / f"reviewer-{i}.md").write_text(
                    f"# Adjudicator {i}\n\n## Decision\n\nAccept\n\nConfidence: 0.8\n",
                    encoding="utf-8",
                )
        if "finishing adjudication" in prompt:
            consolidated = round_dir / "consolidated.md"
            consolidated.write_text(
                "# Consolidated\n\n## Decision\n\nAccept\n\nConfidence: 0.85\n\n## Evidence Refs\n\n- ref1\n- ref2\n",
                encoding="utf-8",
            )
            summary_dir = project_root / "branches" / "shared" / "reviews" / "summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            (summary_dir / "round-1.md").write_text("# Summary\n\nAccept\n", encoding="utf-8")
        return True, None

    original_spawner = set_spawner(fake_spawner)
    try:
        args = AdjudicateArgs(port=port, depth="panel")
        result = mos_adjudicate(args)

        assert result["status"] == "completed"
        assert result["decision"] == "Accept"
        assert result["confidence"] == 0.85
        assert len(spawned_prompts) == 4  # 3 adjudicators + 1 consolidation
        assert "adjudicator 1" in spawned_prompts[0]
        assert "adjudicator 2" in spawned_prompts[1]
        assert "adjudicator 3" in spawned_prompts[2]
    finally:
        set_spawner(original_spawner)


def test_extract_decision():
    """Test decision extraction from consolidated.md."""
    consolidated = Path("/tmp/test_consolidated.md")
    consolidated.write_text(
        "# Consolidated\n\n## Decision\n\nAccept\n\nConfidence: 0.9\n", encoding="utf-8"
    )
    assert _extract_decision(consolidated) == "Accept"

    consolidated.write_text(
        "# Consolidated\n\n## Decision\n\nReject\n\nConfidence: 0.7\n", encoding="utf-8"
    )
    assert _extract_decision(consolidated) == "Reject"

    consolidated.write_text(
        "# Consolidated\n\n## Decision\n\nRevise\n\nConfidence: 0.6\n", encoding="utf-8"
    )
    assert _extract_decision(consolidated) == "Revise"

    consolidated.unlink()


def test_extract_confidence():
    """Test confidence extraction from consolidated.md."""
    consolidated = Path("/tmp/test_consolidated.md")
    consolidated.write_text(
        "# Consolidated\n\n## Decision\n\nAccept\n\nConfidence: 0.95\n", encoding="utf-8"
    )
    assert _extract_confidence(consolidated) == 0.95

    consolidated.write_text("# Consolidated\n\nNo confidence here\n", encoding="utf-8")
    assert _extract_confidence(consolidated) == 0.5  # default

    consolidated.unlink()


def test_extract_evidence_refs():
    """Test evidence refs extraction from consolidated.md."""
    consolidated = Path("/tmp/test_consolidated.md")
    consolidated.write_text(
        "# Consolidated\n\n## Evidence Refs\n\n- ref1\n- ref2\n- ref3\n\n## Other\n\nstuff\n",
        encoding="utf-8",
    )
    refs = _extract_evidence_refs(consolidated)
    assert refs == ["ref1", "ref2", "ref3"]

    consolidated.write_text("# Consolidated\n\nNo evidence section\n", encoding="utf-8")
    refs = _extract_evidence_refs(consolidated)
    assert refs == []

    consolidated.unlink()
