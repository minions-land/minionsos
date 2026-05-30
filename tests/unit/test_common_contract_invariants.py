"""Pin common-contract (roles/SYSTEM.md) invariants so they survive edits.

Issue #86 failure mode 3 (coordination deadlock): roles that only learn
"idle silently when nothing is pending" mutually yield and freeze the
team. The canonical contract must teach the PAIRED rule — drain a
no-decision event silently, AND initiate (DM / task) when idle or
blocked — and must keep `eacn3_send_message` / `eacn3_create_task`
framed as first-class, always-available initiation tools.

If these disappear, the deadlock class of bugs returns, so we lock them
in at the canonical home rather than only in the (derived) forever-loop
prompt.
"""

from __future__ import annotations

from pathlib import Path

COMMON_SYSTEM = Path(__file__).resolve().parents[2] / "minions" / "roles" / "SYSTEM.md"


def _text() -> str:
    return COMMON_SYSTEM.read_text(encoding="utf-8")


class TestCommonContractInvariants:
    def test_file_exists(self) -> None:
        assert COMMON_SYSTEM.exists(), f"missing: {COMMON_SYSTEM}"

    def test_quiet_branch_discipline_present(self) -> None:
        t = _text()
        assert "Quiet-branch discipline" in t

    def test_quiet_branch_pairs_drain_with_initiate(self) -> None:
        """Both halves must be present and explicitly paired — teaching only
        'idle silently' is what over-corrected into the mutual-yield
        deadlock (issue #86)."""
        collapsed = " ".join(_text().split())
        # Drain-silently half.
        assert "drain silently" in collapsed or "drain only" in collapsed.lower()
        # Initiate half.
        assert "Idle / blocked / stalled" in collapsed
        assert "initiate, do NOT wait" in collapsed or "initiate, do not wait" in collapsed
        # The pairing must be explicit so a future editor doesn't drop one
        # half (the failure mode the issue documents).
        assert "pulls in opposite directions" in collapsed or "pairs them" in collapsed

    def test_initiation_tools_are_first_class(self) -> None:
        collapsed = " ".join(_text().split())
        assert "eacn3_send_message" in collapsed
        assert "eacn3_create_task" in collapsed
        # Framed as always-available / first-class, on par with the wake tool.
        assert "first-class" in collapsed
        assert "always available" in collapsed or "always-available" in collapsed

    def test_prefers_task_ownership_over_dm_for_dependencies(self) -> None:
        """The deadlock-breaker is task ownership (claim/bid/result), not DM.
        The contract must say so explicitly, with invited_agent_ids."""
        collapsed = " ".join(_text().split())
        assert "claim/bid/result" in collapsed or "claim/bid/result obligation" in collapsed
        assert "invited_agent_ids" in collapsed
        # The active executor side must also be encouraged.
        assert "bid / claim" in collapsed or "bid/claim" in collapsed

    def test_initiate_distinct_from_keepalive_ack(self) -> None:
        """The initiate-when-idle rule must not contradict the ack-only
        cache_keepalive turn."""
        collapsed = " ".join(_text().split())
        assert "cache_keepalive" in collapsed
        assert "ack-only" in collapsed or "ack turn" in collapsed
