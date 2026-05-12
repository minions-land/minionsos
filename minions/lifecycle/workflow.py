"""Submission gate, review routing, and camera-ready eligibility.

Implements the Phase 4 workflow gates described in the repair roadmap:
- Submission gate validates a package exists before review.
- Review routing maps reviewer verdicts to next actions.
- Camera-ready eligibility requires Accept or Strong Accept.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_VERDICT_RANK = {
    "reject": 0,
    "borderline": 1,
    "weak_accept": 2,
    "accept": 3,
    "strong_accept": 4,
}


class SubmissionVerdict(enum.Enum):
    strong_accept = "strong_accept"
    accept = "accept"
    weak_accept = "weak_accept"
    borderline = "borderline"
    reject = "reject"

    @property
    def rank(self) -> int:
        return _VERDICT_RANK[self.value]


@dataclass
class ReviewRound:
    round_number: int
    verdicts: list[SubmissionVerdict] = field(default_factory=list)

    @property
    def aggregate(self) -> SubmissionVerdict:
        """The aggregate verdict is the most critical (lowest-ranked) opinion."""
        if not self.verdicts:
            return SubmissionVerdict.reject
        return min(self.verdicts, key=lambda v: v.rank)


def route_verdict(review_round: ReviewRound) -> str:
    """Return ``'camera_ready'`` or ``'revision'`` based on the round's aggregate."""
    agg = review_round.aggregate
    if agg.rank >= SubmissionVerdict.accept.rank:
        return "camera_ready"
    return "revision"


def camera_ready_eligible(rounds: list[ReviewRound]) -> tuple[bool, str]:
    """Check whether the latest review round qualifies for camera-ready."""
    if not rounds:
        return False, "No review rounds completed."
    latest = max(rounds, key=lambda r: r.round_number)
    agg = latest.aggregate
    if agg.rank >= SubmissionVerdict.accept.rank:
        return True, f"Round {latest.round_number} aggregate: {agg.value}."
    return False, (
        f"Round {latest.round_number} aggregate: {agg.value} — "
        "revision required before camera-ready."
    )


def submission_gate_check(project_dir: Path) -> tuple[bool, str]:
    """Validate that a submission package exists in *project_dir*.

    MinionsOS layout: the project's main branch worktree lives at
    ``project_{port}/branches/main``. A submission package is present when
    that branch dir exists and ``artifacts/`` contains at least one PDF.
    """
    if not project_dir.is_dir():
        return False, f"Project directory does not exist: {project_dir}"
    branches = project_dir / "branches"
    main_branch = branches / "main"
    if not branches.is_dir():
        return False, "Missing branches/ container."
    if not main_branch.is_dir():
        return False, "Missing branches/main/ directory."
    artifacts = project_dir / "artifacts"
    if not artifacts.is_dir():
        return False, "Missing artifacts/ directory."
    pdfs = list(artifacts.glob("*.pdf"))
    if not pdfs:
        return False, "No PDF found in artifacts/ — paper required for review."
    return True, f"Submission package found: {pdfs[0].name}."


REVIEWER_CHECKLIST: list[dict[str, str]] = [
    {"name": "scientific_contribution", "prompt": "Is the contribution novel and significant?"},
    {"name": "presentation", "prompt": "Is the paper clearly written and well-organized?"},
    {"name": "claim_strength", "prompt": "Are claims well-supported by evidence and experiments?"},
    {
        "name": "missing_baselines",
        "prompt": "Are important baselines or comparisons missing?",
    },
    {"name": "citation_risk", "prompt": "Are citations accurate and complete?"},
    {
        "name": "hallucination_risk",
        "prompt": "Are there unsupported or fabricated claims in the paper or code?",
    },
    {
        "name": "code_reproducibility",
        "prompt": "Can the results be reproduced from the submitted code?",
    },
]
