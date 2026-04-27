"""Pin reviewer-system prompt invariants that protect review isolation.

Reviewer is allowed to coordinate through Local EACN, but formal review quality
depends on two boundaries staying explicit:

1. Reviewer must not hand-roll EACN3 HTTP calls.
2. Pass A must stay history-blind, with history entering only through the
   immediately previous rolling summary during Pass B / Pass C.
"""

from __future__ import annotations

from pathlib import Path

REVIEWER_SYSTEM = (
    Path(__file__).resolve().parents[2] / "minions" / "roles" / "reviewer" / "SYSTEM.md"
)


def _text() -> str:
    return REVIEWER_SYSTEM.read_text(encoding="utf-8")


class TestReviewerSystemInvariants:
    def test_file_exists(self) -> None:
        assert REVIEWER_SYSTEM.exists(), f"missing: {REVIEWER_SYSTEM}"

    def test_forbids_handcrafted_eacn_http(self) -> None:
        t = _text()
        assert "Do not call the EACN3 HTTP API by hand" in t
        assert "signature mismatch" in t or "phantom" in t.lower()

    def test_documents_local_eacn_and_subagent_boundary(self) -> None:
        t = _text()
        assert "Local EACN" in t
        assert "Reviewer main owns all EACN-facing communication" in t
        assert "Review subagents are EACN-invisible" in t

    def test_preserves_pass_a_history_isolation(self) -> None:
        t = _text()
        assert "Pass A is intentionally blind to prior review history" in t
        assert "artifacts/reviews/summaries/round-<n-1>.md" in t
        assert "only during Pass B / Pass C" in t
