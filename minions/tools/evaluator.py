"""Deliverable evaluation tool — profile-aware evaluator dispatch.

Provides ``mos_evaluate`` and ``mos_submit``, the two MCP tools that close
the deliverable lifecycle:

1. ``mos_submit(port, payload, kind)`` — Role asks Gru to persist a
   deliverable (answer, paper, patch, etc.) under ``branches/shared/submissions/``.
2. ``mos_evaluate(port)`` — Gru runs the project's profile-defined evaluation
   strategy and returns a score/verdict.

Evaluation strategies:
- ``scientific_peer_review`` — delegates to ``mos_review_run`` for full
  multi-pass peer review (the original MinionsOS behavior).
- ``answer_grader`` — compares ``submissions/answer.json`` to
  ``input/expected.json`` (HLE, MMLU, GPQA, etc.).
- ``test_runner`` — runs a test suite and reports pass/fail (SWE-bench, etc.).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from minions.errors import ProjectError
from minions.paths import project_dir, project_meta_json, project_shared_subdir

logger = logging.getLogger(__name__)


class SubmitArgs(BaseModel):
    port: int = Field(description="Project port.")
    payload: dict = Field(description="Deliverable payload (structure depends on kind).")
    kind: Literal["answer", "paper", "patch", "report"] = Field(
        description="Deliverable kind (answer | paper | patch | report)."
    )
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata (confidence, reasoning_summary, etc.).",
    )


class EvaluateArgs(BaseModel):
    port: int = Field(description="Project port.")
    reference_override: str | None = Field(
        default=None,
        description="Optional reference path override (for testing).",
    )


def mos_submit(args: SubmitArgs) -> dict[str, object]:
    """Persist a deliverable under branches/shared/submissions/.

    The calling Role (typically Expert or Writer) composes the payload and
    asks Gru to call this tool. Gru validates the payload against the
    project's profile deliverable schema, writes it to disk, and commits
    on the shared branch.

    Returns ``{port, kind, path, commit_sha}``.
    """
    port = args.port
    kind = args.kind
    payload = args.payload
    metadata = args.metadata or {}

    # Resolve submission path based on kind
    submissions_dir = project_shared_subdir(port, "submissions")
    submissions_dir.mkdir(parents=True, exist_ok=True)

    if kind == "answer":
        submission_path = submissions_dir / "answer.json"
        content = json.dumps(
            {
                "answer": payload.get("answer"),
                "confidence": payload.get("confidence"),
                "reasoning_summary": payload.get("reasoning_summary"),
                **metadata,
            },
            indent=2,
        )
    elif kind == "paper":
        submission_path = submissions_dir / "paper.pdf"
        # For paper submissions, payload should contain a path to the PDF.
        # Path safety: must be either absolute under the project's branches/
        # subtree, or relative (resolved against project_dir). Refuses to read
        # files outside the project to prevent exfiltration.
        raw_pdf_path = str(payload.get("pdf_path", ""))
        if not raw_pdf_path:
            raise ProjectError("Paper submission requires payload.pdf_path")
        pdf_path = Path(raw_pdf_path)
        if not pdf_path.is_absolute():
            pdf_path = project_dir(port) / pdf_path
        pdf_path = pdf_path.resolve()
        project_root = project_dir(port).resolve()
        try:
            pdf_path.relative_to(project_root)
        except ValueError as exc:
            raise ProjectError(
                f"Paper PDF path must live under project_{port}/, got: {pdf_path}"
            ) from exc
        if not pdf_path.exists():
            raise ProjectError(f"Paper PDF not found: {pdf_path}")
        content = pdf_path.read_bytes()
    elif kind == "patch":
        submission_path = submissions_dir / "solution.patch"
        content = payload.get("patch_content", "")
    elif kind == "report":
        submission_path = submissions_dir / "report.md"
        content = payload.get("report_content", "")
    else:
        raise ProjectError(f"Unknown submission kind: {kind}")

    # Write submission
    if isinstance(content, bytes):
        submission_path.write_bytes(content)
    else:
        submission_path.write_text(content, encoding="utf-8")

    # Commit via publish tool
    from minions.tools.publish import mos_publish_to_shared

    result = mos_publish_to_shared(
        role="gru",  # Gru is the caller
        src_path=str(submission_path),
        dst_subpath=f"submissions/{submission_path.name}",
        commit_message=f"submit: {kind} deliverable",
        port=port,
    )

    logger.info(
        "mos_submit: port=%d kind=%s path=%s commit=%s",
        port,
        kind,
        submission_path.name,
        result.get("commit_sha"),
    )

    return {
        "port": port,
        "kind": kind,
        "path": str(submission_path),
        "commit_sha": result.get("commit_sha"),
    }


def mos_evaluate(args: EvaluateArgs) -> dict[str, object]:
    """Evaluate the project's deliverable using its profile-defined strategy.

    Reads the project's mission profile from meta.json, dispatches to the
    appropriate evaluator, and returns a score/verdict.

    Returns ``{port, strategy, score, verdict, details}``.
    """
    port = args.port
    meta_path = project_meta_json(port)
    if not meta_path.exists():
        raise ProjectError(f"Project {port} meta.json not found.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    profile_eval = meta.get("profile_evaluation", {})
    strategy = profile_eval.get("strategy", "scientific_peer_review")

    logger.info("mos_evaluate: port=%d strategy=%s", port, strategy)

    if strategy == "scientific_peer_review":
        return _evaluate_scientific_peer_review(port, meta, args.reference_override)
    elif strategy == "answer_grader":
        return _evaluate_answer_grader(port, meta, args.reference_override)
    elif strategy == "test_runner":
        return _evaluate_test_runner(port, meta, args.reference_override)
    else:
        raise ProjectError(f"Unknown evaluation strategy: {strategy}")


def _evaluate_scientific_peer_review(
    port: int, meta: dict, reference_override: str | None
) -> dict[str, object]:
    """Delegate to review_run for full peer review."""
    from minions.tools.review import ReviewRunArgs, review_run

    # Find the submission package (typically under branches/main/paper/)
    pdir = project_dir(port)
    submission_candidates = [
        pdir / "branches" / "main" / "paper",
        pdir / "branches" / "writer" / "paper",
    ]
    submission_path = None
    for candidate in submission_candidates:
        if candidate.exists() and (candidate / "submission-checklist.md").exists():
            submission_path = candidate
            break

    if submission_path is None:
        raise ProjectError(
            f"No submission package found for port {port}. "
            "Expected branches/main/paper/ or branches/writer/paper/ with submission-checklist.md."
        )

    # ReviewRunArgs takes only port / submission_path / prior_summary_path.
    # Round number is auto-allocated by review_run; reviewer_count is fixed at 3.
    review_args = ReviewRunArgs(
        port=port,
        submission_path=str(submission_path),
        prior_summary_path=None,
    )
    result = review_run(review_args)

    return {
        "port": port,
        "strategy": "scientific_peer_review",
        "score": None,  # Peer review produces a decision label, not a numeric score
        "verdict": result.get("decision"),
        "details": {
            "round_number": result.get("round"),
            "consolidated_path": result.get("consolidated_path"),
            "summary_path": result.get("summary_path"),
            "status": result.get("status"),
        },
    }


def _evaluate_answer_grader(
    port: int, meta: dict, reference_override: str | None
) -> dict[str, object]:
    """Compare submission answer to reference (exact match or numeric close)."""
    profile_eval = meta.get("profile_evaluation", {})
    reference_path_rel = reference_override or profile_eval.get(
        "reference_path", "input/expected.json"
    )
    comparison_mode = profile_eval.get("comparison_mode", "exact_match")

    pdir = project_dir(port)
    reference_path = pdir / reference_path_rel
    submission_path = project_shared_subdir(port, "submissions") / "answer.json"

    if not reference_path.exists():
        raise ProjectError(f"Reference answer not found: {reference_path}")
    if not submission_path.exists():
        raise ProjectError(f"Submission answer not found: {submission_path}")

    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    submission = json.loads(submission_path.read_text(encoding="utf-8"))

    expected_answer = reference.get("answer")
    submitted_answer = submission.get("answer")

    if comparison_mode == "exact_match":
        correct = expected_answer == submitted_answer
    elif comparison_mode == "numeric_close":
        try:
            expected_num = float(expected_answer)
            submitted_num = float(submitted_answer)
            correct = abs(expected_num - submitted_num) < 1e-6
        except (ValueError, TypeError):
            correct = False
    else:
        raise ProjectError(f"Unknown comparison mode: {comparison_mode}")

    score = 1.0 if correct else 0.0
    verdict = "correct" if correct else "incorrect"

    logger.info(
        "answer_grader: port=%d expected=%r submitted=%r correct=%s",
        port,
        expected_answer,
        submitted_answer,
        correct,
    )

    return {
        "port": port,
        "strategy": "answer_grader",
        "score": score,
        "verdict": verdict,
        "details": {
            "expected": expected_answer,
            "submitted": submitted_answer,
            "comparison_mode": comparison_mode,
        },
    }


def _evaluate_test_runner(
    port: int, meta: dict, reference_override: str | None
) -> dict[str, object]:
    """Run test suite and report pass/fail (SWE-bench style)."""
    # Placeholder for test_runner strategy (v15-δ will implement this for SWE-bench)
    raise ProjectError("test_runner strategy not yet implemented (reserved for v15-δ).")


__all__ = ["EvaluateArgs", "SubmitArgs", "mos_evaluate", "mos_submit"]
