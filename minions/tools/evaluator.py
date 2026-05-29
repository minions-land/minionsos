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
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from minions.errors import ProjectError
from minions.paths import project_dir, project_meta_json, project_shared_subdir
from minions.tools._returns import DictLikeBaseModel

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


class SubmitResult(DictLikeBaseModel):
    """Result shape for ``mos_submit``.

    Returned after a deliverable is persisted under ``branches/shared/submissions/``
    and committed on the shared branch. ``commit_sha`` is ``None`` only if the
    publish was a no-op (e.g. the file on disk already matched HEAD).
    """

    port: int = Field(description="Project port the deliverable was submitted to.")
    kind: Literal["answer", "paper", "patch", "report"] = Field(description="Deliverable kind.")
    path: str = Field(description="Absolute path to the persisted submission file.")
    commit_sha: str | None = Field(
        default=None,
        description="SHA of the shared-branch commit, or None if no diff was produced.",
    )


class EvaluateResult(DictLikeBaseModel):
    """Result shape for ``mos_evaluate``.

    All evaluation strategies (``scientific_peer_review``, ``answer_grader``,
    ``test_runner``) and the adjudication-gate short-circuits return this shape.
    ``score`` may be ``None`` for strategies that produce a verdict label rather
    than a numeric score (e.g. peer review) or for ``revise_required`` outcomes.
    ``details`` carries strategy-specific information: peer review surfaces
    ``round_number``/``consolidated_path``; answer_grader surfaces
    ``expected``/``submitted``/``comparison_mode``; the adjudication gate adds
    ``adjudication`` and ``reason``; ``on_done`` is recorded when a passing
    verdict triggers a project transition.
    """

    port: int = Field(description="Project port that was evaluated.")
    strategy: str = Field(description="Evaluation strategy that ran.")
    score: float | None = Field(
        default=None,
        description="Numeric score (None if the strategy emits a label-only verdict).",
    )
    verdict: str | None = Field(
        default=None,
        description="Verdict label (e.g. correct/incorrect/rejected/revise_required/Accept).",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy-specific details, plus adjudication/on_done extras.",
    )


def mos_submit(args: SubmitArgs) -> SubmitResult:
    """Persist a deliverable under branches/shared/submissions/.

    The calling Role (typically Expert or Writer) composes the payload and
    asks Gru to call this tool. Gru validates the payload against the
    project's profile deliverable schema, writes it to disk, and commits
    on the shared branch.

    Returns a :class:`SubmitResult` with ``port``, ``kind``, ``path``, and
    ``commit_sha``. The result is dict-like so callers using ``result["port"]``
    or ``result.get("commit_sha")`` keep working.
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

    return SubmitResult(
        port=port,
        kind=kind,
        path=str(submission_path),
        commit_sha=cast(str | None, result.get("commit_sha")),
    )


def mos_evaluate(args: EvaluateArgs) -> EvaluateResult:
    """Evaluate the project's deliverable using its profile-defined strategy.

    Reads the project's mission profile from meta.json, dispatches to the
    appropriate evaluator, and returns a score/verdict.

    If the profile declares ``evaluation.adjudication.depth`` as ``single`` or
    ``panel``, runs ``mos_adjudicate`` first as a gate. The grader only fires
    when adjudication returns ``decision=Accept``; ``Reject`` short-circuits
    to ``{score=0, verdict=rejected}`` and ``Revise`` short-circuits to
    ``{verdict=revise_required}``. Adjudication depth ``none`` (default for
    scientific-paper) skips the gate and goes straight to the grader.

    Returns an :class:`EvaluateResult` with ``port``, ``strategy``, ``score``,
    ``verdict``, and ``details``. The result is dict-like so callers using
    ``result["score"]`` or ``result.get("verdict")`` keep working.
    """
    port = args.port
    meta_path = project_meta_json(port)
    if not meta_path.exists():
        raise ProjectError(f"Project {port} meta.json not found.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    profile_eval = meta.get("profile_evaluation", {})
    strategy = profile_eval.get("strategy", "scientific_peer_review")

    logger.info("mos_evaluate: port=%d strategy=%s", port, strategy)

    # Adjudication gate (runs before the grader when depth != none).
    adjudication_block = profile_eval.get("adjudication") or {}
    adj_depth = str(adjudication_block.get("depth", "none")).strip().lower()
    adjudication_result: dict[str, object] | None = None
    if adj_depth in {"single", "panel"}:
        from minions.tools.adjudicator import AdjudicateArgs, mos_adjudicate

        logger.info("mos_evaluate: adjudication gate depth=%s", adj_depth)
        adjudication_result = mos_adjudicate(
            AdjudicateArgs(
                port=port,
                depth=cast(Literal["none", "single", "panel"], adj_depth),
            )
        )
        decision = adjudication_result.get("decision")
        if decision == "Reject":
            return EvaluateResult(
                port=port,
                strategy=strategy,
                score=0.0,
                verdict="rejected",
                details={
                    "adjudication": adjudication_result,
                    "reason": "adjudication_rejected",
                },
            )
        if decision == "Revise":
            return EvaluateResult(
                port=port,
                strategy=strategy,
                score=None,
                verdict="revise_required",
                details={
                    "adjudication": adjudication_result,
                    "reason": "adjudication_revise_required",
                },
            )
        # decision == "Accept" or status="skipped" / "error" — fall through to
        # the grader. An adjudication error must not silently bypass scoring;
        # the grader still runs and reports its own verdict, with the
        # adjudication payload preserved in details.

    if strategy == "scientific_peer_review":
        result = _evaluate_scientific_peer_review(port, meta, args.reference_override)
    elif strategy == "answer_grader":
        result = _evaluate_answer_grader(port, meta, args.reference_override)
    elif strategy == "test_runner":
        result = _evaluate_test_runner(port, meta, args.reference_override)
    else:
        raise ProjectError(f"Unknown evaluation strategy: {strategy}")

    if adjudication_result is not None:
        result.details["adjudication"] = adjudication_result

    # on_done wiring: if profile declares shutdown_project / dormant and the
    # grader returned a passing verdict, transition the project. Failures and
    # revise_required leave the project active so the team can iterate.
    on_done = str(meta.get("profile_on_done", "none")).strip().lower()
    verdict = result.verdict
    score = result.score
    passed = verdict in {"correct", "Accept"} or (isinstance(score, (int, float)) and score >= 1.0)
    if passed and on_done in {"shutdown_project", "dormant"}:
        try:
            _apply_on_done(port, on_done)
            result.details["on_done"] = on_done
        except Exception as exc:
            logger.warning("mos_evaluate: on_done=%s failed for port=%d: %s", on_done, port, exc)

    return result


def _apply_on_done(port: int, on_done: str) -> None:
    """Transition the project according to the profile's on_done setting.

    Best-effort: failures are logged at the call site but do not raise so a
    successful evaluation is never reported as failed because of a shutdown
    hiccup.
    """
    if on_done == "shutdown_project":
        from minions.lifecycle.project import project_close

        project_close(port)
    elif on_done == "dormant":
        from minions.lifecycle.project import project_dormant

        project_dormant(port)


def _evaluate_scientific_peer_review(
    port: int, meta: dict, reference_override: str | None
) -> EvaluateResult:
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

    return EvaluateResult(
        port=port,
        strategy="scientific_peer_review",
        score=None,  # Peer review produces a decision label, not a numeric score
        verdict=cast(str | None, result.get("decision")),
        details={
            "round_number": result.get("round"),
            "consolidated_path": result.get("consolidated_path"),
            "summary_path": result.get("summary_path"),
            "status": result.get("status"),
        },
    )


def _evaluate_answer_grader(
    port: int, meta: dict, reference_override: str | None
) -> EvaluateResult:
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

    return EvaluateResult(
        port=port,
        strategy="answer_grader",
        score=score,
        verdict=verdict,
        details={
            "expected": expected_answer,
            "submitted": submitted_answer,
            "comparison_mode": comparison_mode,
        },
    )


def _evaluate_test_runner(port: int, meta: dict, reference_override: str | None) -> EvaluateResult:
    """Run test suite and report pass/fail (SWE-bench style)."""
    # Placeholder for test_runner strategy (v15-δ will implement this for SWE-bench)
    raise ProjectError("test_runner strategy not yet implemented (reserved for v15-δ).")


__all__ = [
    "EvaluateArgs",
    "EvaluateResult",
    "SubmitArgs",
    "SubmitResult",
    "mos_evaluate",
    "mos_submit",
]
