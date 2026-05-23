"""Unit tests for evaluator (mos_submit / mos_evaluate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.errors import ProjectError
from minions.tools.evaluator import EvaluateArgs, SubmitArgs, mos_evaluate, mos_submit


@pytest.fixture
def mock_hle_project(tmp_path: Path, monkeypatch):
    """Create a minimal HLE-style project structure for testing.

    Patches every path helper used by both the evaluator and publish layers
    so that mos_submit + mos_evaluate work end-to-end against ``tmp_path``.
    """
    port = 9999
    project_root = tmp_path / f"project_{port}"
    project_root.mkdir()

    # Create meta.json with hle-answer profile
    meta = {
        "port": port,
        "real_name": "test-hle",
        "profile": "hle-answer",
        "profile_evaluation": {
            "strategy": "answer_grader",
            "reference_path": "input/expected.json",
            "comparison_mode": "exact_match",
        },
        "profile_deliverable_schema": {
            "required": ["branches/shared/submissions/answer.json"],
            "publish_whitelist": {
                "gru": ["*"],
                "expert": ["handoffs", "submissions"],
                "coder": ["exp", "handoffs", "submissions"],
            },
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

    def mock_project_shared_lock(p: int) -> Path:
        return state_dir / "shared.lock"

    def mock_project_shared_branch_name(p: int) -> str:
        return f"minionsos/project-{p}-shared"

    import minions.paths
    import minions.tools.evaluator
    import minions.tools.publish

    # Patch in minions.paths
    monkeypatch.setattr(minions.paths, "project_dir", mock_project_dir)
    monkeypatch.setattr(minions.paths, "project_meta_json", mock_project_meta_json)
    monkeypatch.setattr(minions.paths, "project_shared_subdir", mock_project_shared_subdir)
    monkeypatch.setattr(minions.paths, "project_shared_workspace", mock_project_shared_workspace)
    monkeypatch.setattr(minions.paths, "project_shared_lock", mock_project_shared_lock)
    monkeypatch.setattr(
        minions.paths, "project_shared_branch_name", mock_project_shared_branch_name
    )

    # Patch in evaluator module
    monkeypatch.setattr(minions.tools.evaluator, "project_dir", mock_project_dir)
    monkeypatch.setattr(minions.tools.evaluator, "project_meta_json", mock_project_meta_json)
    monkeypatch.setattr(
        minions.tools.evaluator, "project_shared_subdir", mock_project_shared_subdir
    )

    # Patch in publish module
    monkeypatch.setattr(
        minions.tools.publish, "project_meta_json", mock_project_meta_json, raising=False
    )
    monkeypatch.setattr(
        minions.tools.publish, "project_shared_workspace", mock_project_shared_workspace
    )
    monkeypatch.setattr(minions.tools.publish, "project_shared_lock", mock_project_shared_lock)
    monkeypatch.setattr(
        minions.tools.publish, "project_shared_branch_name", mock_project_shared_branch_name
    )

    # Mock git operations - is_git_work_tree returns True for our shared dir
    def mock_is_git_work_tree(path: Path) -> bool:
        return True

    class MockResult:
        returncode = 0
        stdout = "abc123\n"
        stderr = ""

    def mock_run_git(cmd, cwd, **kwargs):
        return MockResult()

    monkeypatch.setattr(minions.tools.publish, "is_git_work_tree", mock_is_git_work_tree)
    monkeypatch.setattr(minions.tools.publish, "run_git", mock_run_git)

    # Mock subprocess.run for git commit
    import subprocess

    original_run = subprocess.run

    def mock_subprocess_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) > 1 and cmd[0] == "git":
            return MockResult()
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    # Mock StateStore for publish tool
    class MockStateStore:
        def get_project(self, port_arg: int):
            class Entry:
                github_push_target = None
                github_push_branch_prefix = None

            return Entry()

    monkeypatch.setattr(minions.tools.publish, "StateStore", MockStateStore)

    # Mock noter_wait nudge (best-effort, may fail silently anyway)
    try:
        import minions.tools.noter_wait as nw

        monkeypatch.setattr(nw, "nudge_noter", lambda p: None)
    except Exception:
        pass

    return port, project_root


def test_submit_answer(mock_hle_project):
    """Test mos_submit with answer payload."""
    port, project_root = mock_hle_project

    args = SubmitArgs(
        port=port,
        payload={"answer": 42, "confidence": 0.95, "reasoning_summary": "Computed via sympy"},
        kind="answer",
    )

    result = mos_submit(args)

    assert result["port"] == port
    assert result["kind"] == "answer"
    assert "answer.json" in result["path"]

    # Verify file was written
    submission_path = project_root / "branches" / "shared" / "submissions" / "answer.json"
    assert submission_path.exists()
    content = json.loads(submission_path.read_text(encoding="utf-8"))
    assert content["answer"] == 42
    assert content["confidence"] == 0.95


def test_evaluate_answer_grader_correct(mock_hle_project):
    """Test mos_evaluate with correct answer."""
    port, _project_root = mock_hle_project

    # Submit correct answer
    submit_args = SubmitArgs(
        port=port,
        payload={"answer": 42},
        kind="answer",
    )
    mos_submit(submit_args)

    # Evaluate
    eval_args = EvaluateArgs(port=port)
    result = mos_evaluate(eval_args)

    assert result["port"] == port
    assert result["strategy"] == "answer_grader"
    assert result["score"] == 1.0
    assert result["verdict"] == "correct"
    assert result["details"]["expected"] == 42
    assert result["details"]["submitted"] == 42


def test_evaluate_answer_grader_incorrect(mock_hle_project):
    """Test mos_evaluate with incorrect answer."""
    port, _project_root = mock_hle_project

    # Submit incorrect answer
    submit_args = SubmitArgs(
        port=port,
        payload={"answer": 99},
        kind="answer",
    )
    mos_submit(submit_args)

    # Evaluate
    eval_args = EvaluateArgs(port=port)
    result = mos_evaluate(eval_args)

    assert result["port"] == port
    assert result["strategy"] == "answer_grader"
    assert result["score"] == 0.0
    assert result["verdict"] == "incorrect"
    assert result["details"]["expected"] == 42
    assert result["details"]["submitted"] == 99


def test_evaluate_missing_submission(mock_hle_project):
    """Test mos_evaluate raises when submission is missing."""
    port, _project_root = mock_hle_project

    eval_args = EvaluateArgs(port=port)

    with pytest.raises(ProjectError, match="Submission answer not found"):
        mos_evaluate(eval_args)


def test_evaluate_missing_reference(mock_hle_project):
    """Test mos_evaluate raises when reference is missing."""
    port, project_root = mock_hle_project

    # Remove reference file
    (project_root / "input" / "expected.json").unlink()

    # Submit answer
    submit_args = SubmitArgs(port=port, payload={"answer": 42}, kind="answer")
    mos_submit(submit_args)

    # Evaluate should fail
    eval_args = EvaluateArgs(port=port)

    with pytest.raises(ProjectError, match="Reference answer not found"):
        mos_evaluate(eval_args)


def test_scientific_peer_review_import_path():
    """The scientific_peer_review strategy imports review_run, not mos_review_run.

    Regression test for v15-β: an earlier draft tried to import the MCP wrapper
    `mos_review_run` from `minions.tools.review`, but the wrapper lives in
    `minions.tools.mcp.evaluator_tools` and the underlying function is named
    `review_run`. This test pins the import so the scientific path doesn't
    silently break at runtime.
    """
    # Import the function the evaluator uses internally
    from minions.tools.review import ReviewRunArgs, review_run

    assert callable(review_run)
    assert ReviewRunArgs is not None


def test_paper_submit_path_traversal_rejected(mock_hle_project, tmp_path):
    """mos_submit kind=paper must reject paths outside the project tree."""
    port, _project_root = mock_hle_project

    # Try to submit a PDF from outside the project (a path traversal attempt)
    outside_pdf = tmp_path / "evil.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4\nfake")

    submit_args = SubmitArgs(
        port=port,
        payload={"pdf_path": str(outside_pdf)},
        kind="paper",
    )

    with pytest.raises(ProjectError, match="must live under project_"):
        mos_submit(submit_args)


def test_paper_submit_missing_pdf_path_rejected(mock_hle_project):
    """mos_submit kind=paper must reject empty pdf_path."""
    port, _project_root = mock_hle_project

    submit_args = SubmitArgs(
        port=port,
        payload={},
        kind="paper",
    )

    with pytest.raises(ProjectError, match=r"requires payload\.pdf_path"):
        mos_submit(submit_args)


def test_evaluate_with_adjudication_gate_accept(mock_hle_project, monkeypatch):
    """mos_evaluate with adjudication depth=single should run adjudicator first."""
    port, project_root = mock_hle_project

    # Update meta to include adjudication
    meta_path = project_root / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["profile_evaluation"]["adjudication"] = {"depth": "single"}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Submit correct answer
    submit_args = SubmitArgs(port=port, payload={"answer": 42}, kind="answer")
    mos_submit(submit_args)

    # Mock adjudicator to return Accept
    def mock_adjudicate(args):
        return {
            "status": "completed",
            "decision": "Accept",
            "confidence": 0.9,
            "evidence_refs": ["ref1"],
            "consolidated_path": "/fake/path",
            "summary_path": "/fake/summary",
        }

    import minions.tools.adjudicator

    monkeypatch.setattr(minions.tools.adjudicator, "mos_adjudicate", mock_adjudicate)

    # Evaluate
    eval_args = EvaluateArgs(port=port)
    result = mos_evaluate(eval_args)

    assert result["port"] == port
    assert result["strategy"] == "answer_grader"
    assert result["score"] == 1.0
    assert result["verdict"] == "correct"
    assert "adjudication" in result["details"]
    assert result["details"]["adjudication"]["decision"] == "Accept"


def test_evaluate_with_adjudication_gate_reject(mock_hle_project, monkeypatch):
    """mos_evaluate with adjudication Reject should short-circuit to score=0."""
    port, project_root = mock_hle_project

    # Update meta to include adjudication
    meta_path = project_root / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["profile_evaluation"]["adjudication"] = {"depth": "panel"}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Submit answer
    submit_args = SubmitArgs(port=port, payload={"answer": 99}, kind="answer")
    mos_submit(submit_args)

    # Mock adjudicator to return Reject
    def mock_adjudicate(args):
        return {
            "status": "completed",
            "decision": "Reject",
            "confidence": 0.8,
            "evidence_refs": ["counterexample"],
            "consolidated_path": "/fake/path",
            "summary_path": "/fake/summary",
        }

    import minions.tools.adjudicator

    monkeypatch.setattr(minions.tools.adjudicator, "mos_adjudicate", mock_adjudicate)

    # Evaluate
    eval_args = EvaluateArgs(port=port)
    result = mos_evaluate(eval_args)

    assert result["port"] == port
    assert result["strategy"] == "answer_grader"
    assert result["score"] == 0.0
    assert result["verdict"] == "rejected"
    assert result["details"]["reason"] == "adjudication_rejected"
    assert result["details"]["adjudication"]["decision"] == "Reject"


def test_evaluate_with_adjudication_gate_revise(mock_hle_project, monkeypatch):
    """mos_evaluate with adjudication Revise should short-circuit to revise_required."""
    port, project_root = mock_hle_project

    # Update meta to include adjudication
    meta_path = project_root / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["profile_evaluation"]["adjudication"] = {"depth": "panel"}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Submit answer
    submit_args = SubmitArgs(port=port, payload={"answer": 42}, kind="answer")
    mos_submit(submit_args)

    # Mock adjudicator to return Revise
    def mock_adjudicate(args):
        return {
            "status": "completed",
            "decision": "Revise",
            "confidence": 0.6,
            "evidence_refs": ["missing_step"],
            "consolidated_path": "/fake/path",
            "summary_path": "/fake/summary",
        }

    import minions.tools.adjudicator

    monkeypatch.setattr(minions.tools.adjudicator, "mos_adjudicate", mock_adjudicate)

    # Evaluate
    eval_args = EvaluateArgs(port=port)
    result = mos_evaluate(eval_args)

    assert result["port"] == port
    assert result["strategy"] == "answer_grader"
    assert result["score"] is None
    assert result["verdict"] == "revise_required"
    assert result["details"]["reason"] == "adjudication_revise_required"
    assert result["details"]["adjudication"]["decision"] == "Revise"
