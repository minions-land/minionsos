"""Deliverable evaluation tool — scientific-paper evaluator.

Provides ``mos_evaluate`` and ``mos_submit``, the two MCP tools that close
the deliverable lifecycle:

1. ``mos_submit(port, payload, kind="paper")`` — Role asks Gru to persist the
   paper deliverable under ``branches/main/submissions/``.
2. ``mos_evaluate(port)`` — Gru runs full multi-pass peer review via
   ``mos_review_run`` and returns the decision label.

MinionsOS is an autonomous-scientific-discovery system: the only evaluation
strategy is ``scientific_peer_review``.
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
    payload: dict = Field(description="Deliverable payload (must contain pdf_path).")
    kind: Literal["paper"] = Field(
        default="paper",
        description="Deliverable kind. Only 'paper' is supported.",
    )
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata (venue, title, etc.).",
    )


class EvaluateArgs(BaseModel):
    port: int = Field(description="Project port.")
    reference_override: str | None = Field(
        default=None,
        description="Optional reference path override (for testing).",
    )


class SubmitResult(DictLikeBaseModel):
    """Result shape for ``mos_submit``.

    Returned after the paper deliverable is persisted under
    ``branches/main/submissions/`` and committed on the main branch.
    ``commit_sha`` is ``None`` only if the publish was a no-op (e.g. the file
    on disk already matched HEAD).
    """

    port: int = Field(description="Project port the deliverable was submitted to.")
    kind: Literal["paper"] = Field(description="Deliverable kind.")
    path: str = Field(description="Absolute path to the persisted submission file.")
    commit_sha: str | None = Field(
        default=None,
        description="SHA of the main-branch commit, or None if no diff was produced.",
    )


class EvaluateResult(DictLikeBaseModel):
    """Result shape for ``mos_evaluate``.

    ``scientific_peer_review`` produces a verdict label (decision) rather than
    a numeric score, so ``score`` is typically ``None``. ``details`` carries
    ``round_number`` / ``consolidated_path`` / ``summary_path`` / ``status``
    from the review round, plus ``on_done`` when a passing verdict triggers a
    project transition.
    """

    port: int = Field(description="Project port that was evaluated.")
    strategy: str = Field(description="Evaluation strategy that ran.")
    score: float | None = Field(
        default=None,
        description="Numeric score (None for label-only peer-review verdicts).",
    )
    verdict: str | None = Field(
        default=None,
        description="Verdict label (e.g. Accept / Reject / Weak Accept).",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy-specific details, plus on_done extras.",
    )


def mos_submit(args: SubmitArgs) -> SubmitResult:
    """Persist the paper deliverable under branches/main/submissions/.

    The calling Role asks Gru to call this tool. Gru reads the compiled PDF
    referenced by ``payload.pdf_path`` and commits it on the project main branch.

    Returns a :class:`SubmitResult` with ``port``, ``kind``, ``path``, and
    ``commit_sha``. The result is dict-like so callers using ``result["port"]``
    or ``result.get("commit_sha")`` keep working.
    """
    port = args.port

    submissions_dir = project_shared_subdir(port, "submissions")
    submissions_dir.mkdir(parents=True, exist_ok=True)

    submission_path = submissions_dir / "paper.pdf"
    # payload.pdf_path points at the compiled PDF. Path safety: must be either
    # absolute under the project's branches/ subtree, or relative (resolved
    # against project_dir). Refuses to read files outside the project to
    # prevent exfiltration.
    raw_pdf_path = str(args.payload.get("pdf_path", ""))
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

    submission_path.write_bytes(content)

    # Commit via publish tool
    from minions.tools.publish import mos_publish_to_shared

    result = mos_publish_to_shared(
        role="gru",  # Gru is the caller
        src_path=str(submission_path),
        dst_subpath=f"submissions/{submission_path.name}",
        commit_message="submit: paper deliverable",
        port=port,
    )

    logger.info(
        "mos_submit: port=%d kind=paper path=%s commit=%s",
        port,
        submission_path.name,
        result.get("commit_sha"),
    )

    return SubmitResult(
        port=port,
        kind="paper",
        path=str(submission_path),
        commit_sha=cast(str | None, result.get("commit_sha")),
    )


def mos_evaluate(args: EvaluateArgs) -> EvaluateResult:
    """Evaluate the project's paper deliverable via full peer review.

    Runs ``mos_review_run`` (multi-pass Area-Chair review) and returns the
    decision label. MinionsOS is scientific-discovery only, so there is a
    single strategy: ``scientific_peer_review``.

    Returns an :class:`EvaluateResult` with ``port``, ``strategy``, ``score``
    (None — peer review emits a label, not a number), ``verdict``, and
    ``details``. The result is dict-like so callers using ``result["verdict"]``
    keep working.
    """
    port = args.port
    meta_path = project_meta_json(port)
    if not meta_path.exists():
        raise ProjectError(f"Project {port} meta.json not found.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    logger.info("mos_evaluate: port=%d strategy=scientific_peer_review", port)

    result = _evaluate_scientific_peer_review(port, meta, args.reference_override)

    # on_done wiring: if profile declares shutdown_project / dormant and the
    # review returned a passing verdict, transition the project. Failures and
    # borderline outcomes leave the project active so the team can iterate.
    on_done = str(meta.get("profile_on_done", "none")).strip().lower()
    verdict = result.verdict
    passed = verdict in {"Strong Accept", "Accept", "Weak Accept"}
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

    # Find the submission package. Gru promotes the paper to branches/main/paper/;
    # an Expert worker drafts under its own branch (branches/<expert>/paper/).
    pdir = project_dir(port)
    submission_candidates = [
        pdir / "branches" / "main" / "paper",
    ]
    # Fall back to any Expert role branch that carries a paper/ package.
    branches_root = pdir / "branches"
    if branches_root.is_dir():
        for branch_dir in sorted(branches_root.glob("expert*")):
            submission_candidates.append(branch_dir / "paper")
    submission_path = None
    for candidate in submission_candidates:
        if candidate.exists() and (candidate / "submission-checklist.md").exists():
            submission_path = candidate
            break

    if submission_path is None:
        raise ProjectError(
            f"No submission package found for port {port}. "
            "Expected branches/main/paper/ or branches/<expert>/paper/ "
            "with submission-checklist.md."
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


__all__ = [
    "EvaluateArgs",
    "EvaluateResult",
    "SubmitArgs",
    "SubmitResult",
    "mos_evaluate",
    "mos_submit",
]
