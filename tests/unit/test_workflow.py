"""Phase 4 tests: submission gate, review routing, camera-ready eligibility."""

from __future__ import annotations

from pathlib import Path

from minions.lifecycle.workflow import (
    REVIEWER_CHECKLIST,
    ReviewRound,
    SubmissionVerdict,
    camera_ready_eligible,
    route_verdict,
    submission_gate_check,
)


class TestSubmissionVerdict:
    def test_enum_values(self) -> None:
        assert SubmissionVerdict.strong_accept.value == "strong_accept"
        assert SubmissionVerdict.accept.value == "accept"
        assert SubmissionVerdict.weak_accept.value == "weak_accept"
        assert SubmissionVerdict.borderline.value == "borderline"
        assert SubmissionVerdict.reject.value == "reject"

    def test_ordering(self) -> None:
        ordered = sorted(SubmissionVerdict, key=lambda v: v.rank)
        names = [v.value for v in ordered]
        assert names == [
            "reject",
            "borderline",
            "weak_accept",
            "accept",
            "strong_accept",
        ]


class TestReviewRound:
    def test_minimum_three_verdicts(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.strong_accept,
                SubmissionVerdict.accept,
            ],
        )
        assert len(rr.verdicts) == 3

    def test_aggregate_is_minimum(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.weak_accept,
                SubmissionVerdict.strong_accept,
            ],
        )
        assert rr.aggregate == SubmissionVerdict.weak_accept

    def test_all_accept(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.accept,
                SubmissionVerdict.strong_accept,
            ],
        )
        assert rr.aggregate == SubmissionVerdict.accept


class TestRouteVerdict:
    def test_accept_routes_to_camera_ready(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.accept,
                SubmissionVerdict.strong_accept,
            ],
        )
        assert route_verdict(rr) == "camera_ready"

    def test_strong_accept_routes_to_camera_ready(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.strong_accept,
                SubmissionVerdict.strong_accept,
                SubmissionVerdict.strong_accept,
            ],
        )
        assert route_verdict(rr) == "camera_ready"

    def test_reject_routes_to_revision(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.reject,
                SubmissionVerdict.accept,
            ],
        )
        assert route_verdict(rr) == "revision"

    def test_weak_accept_routes_to_revision(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.weak_accept,
                SubmissionVerdict.accept,
            ],
        )
        assert route_verdict(rr) == "revision"

    def test_borderline_routes_to_revision(self) -> None:
        rr = ReviewRound(
            round_number=1,
            verdicts=[
                SubmissionVerdict.accept,
                SubmissionVerdict.borderline,
                SubmissionVerdict.strong_accept,
            ],
        )
        assert route_verdict(rr) == "revision"


class TestCameraReadyEligible:
    def test_eligible_with_accept(self) -> None:
        rounds = [
            ReviewRound(
                round_number=1,
                verdicts=[
                    SubmissionVerdict.accept,
                    SubmissionVerdict.accept,
                    SubmissionVerdict.accept,
                ],
            ),
        ]
        ok, _reason = camera_ready_eligible(rounds)
        assert ok is True

    def test_not_eligible_with_no_rounds(self) -> None:
        ok, reason = camera_ready_eligible([])
        assert ok is False
        assert "no review" in reason.lower()

    def test_not_eligible_after_rejection(self) -> None:
        rounds = [
            ReviewRound(
                round_number=1,
                verdicts=[
                    SubmissionVerdict.reject,
                    SubmissionVerdict.accept,
                    SubmissionVerdict.accept,
                ],
            ),
        ]
        ok, _reason = camera_ready_eligible(rounds)
        assert ok is False

    def test_latest_round_determines_eligibility(self) -> None:
        rounds = [
            ReviewRound(
                round_number=1,
                verdicts=[
                    SubmissionVerdict.reject,
                    SubmissionVerdict.reject,
                    SubmissionVerdict.reject,
                ],
            ),
            ReviewRound(
                round_number=2,
                verdicts=[
                    SubmissionVerdict.accept,
                    SubmissionVerdict.accept,
                    SubmissionVerdict.strong_accept,
                ],
            ),
        ]
        ok, _reason = camera_ready_eligible(rounds)
        assert ok is True


class TestSubmissionGateCheck:
    def test_missing_project_dir_fails(self, tmp_path: Path) -> None:
        ok, _reason = submission_gate_check(tmp_path / "nonexistent")
        assert ok is False

    def test_empty_project_dir_fails(self, tmp_path: Path) -> None:
        project = tmp_path / "project_37596"
        project.mkdir()
        ok, _reason = submission_gate_check(project)
        assert ok is False

    def test_valid_submission_passes(self, tmp_path: Path) -> None:
        project = tmp_path / "project_37596"
        project.mkdir()
        (project / "workspace" / "main").mkdir(parents=True)
        artifacts = project / "artifacts"
        artifacts.mkdir()
        (artifacts / "paper.pdf").write_bytes(b"%PDF-fake")
        ok, _reason = submission_gate_check(project)
        assert ok is True

    def test_missing_pdf_fails(self, tmp_path: Path) -> None:
        project = tmp_path / "project_37596"
        project.mkdir()
        (project / "workspace" / "main").mkdir(parents=True)
        (project / "artifacts").mkdir()
        ok, reason = submission_gate_check(project)
        assert ok is False
        assert "pdf" in reason.lower()


class TestReviewerChecklist:
    def test_checklist_has_required_dimensions(self) -> None:
        names = {item["name"] for item in REVIEWER_CHECKLIST}
        assert "scientific_contribution" in names
        assert "presentation" in names
        assert "claim_strength" in names
        assert "code_reproducibility" in names
