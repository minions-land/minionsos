"""Cross-cutting authz tests for the MinionsOS Memory permission matrix.

Permission matrix:

  Layer         | Self | Other Role | Ethics         | Gru
  Reel-Index    | RW   | —          | R (cross-role) | R
  Draft         | RW   | R          | R + status W   | R
  Book          | R    | R          | R + ratify     | R
"""

import pytest

from minions.tools import book, draft, reel

# ---------------------------------------------------------------------------
# Reel authz tests
# ---------------------------------------------------------------------------


class TestReelAuthz:
    """
    Reel-Index (L0): self RW; Ethics + Gru cross-read; all others denied;
    no observatory process has Reel access.
    """

    def test_reel_self_read(self, monkeypatch):
        """Expert reading its own reel index should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "expert")
        reel.check_reel_read_authz(caller_role="expert", target_role="expert")

    def test_reel_cross_read_denied_for_peer(self, monkeypatch):
        """Peer Expert reading another Expert reel should be denied."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "expert-a")
        with pytest.raises(PermissionError):
            reel.check_reel_read_authz(caller_role="expert-a", target_role="expert-ml")

    def test_reel_cross_read_allowed_for_ethics(self, monkeypatch):
        """Ethics reading an Expert reel cross-role should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
        reel.check_reel_read_authz(caller_role="ethics", target_role="expert")

    def test_reel_cross_read_allowed_for_gru(self, monkeypatch):
        """Gru reading any role's reel should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "gru")
        for target in ("expert", "ethics", "expert-phys"):
            reel.check_reel_read_authz(caller_role="gru", target_role=target)

    def test_reel_observatory_excluded(self, monkeypatch):
        """Observatory process has no reel access at all."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "observatory")
        with pytest.raises(PermissionError):
            reel.check_reel_read_authz(caller_role="observatory", target_role="observatory")


# ---------------------------------------------------------------------------
# Book authz tests
# ---------------------------------------------------------------------------


class TestBookAuthz:
    """
    Book (L2): Ethics ratifies; all others read-only.
    """

    def test_book_ratify_only_ethics(self, monkeypatch):
        """
        Only Ethics may call mos_book_ratify.
        Expert calling it should raise BookError (or PermissionError).
        Ethics calling it should succeed (or return without authz error).
        """
        monkeypatch.setenv("MINIONS_ROLE_NAME", "expert")
        with pytest.raises((book.BookError, PermissionError)):
            book.check_book_ratify_authz(caller_role="expert")

        monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
        book.check_book_ratify_authz(caller_role="ethics")


# ---------------------------------------------------------------------------
# Draft authz tests
# ---------------------------------------------------------------------------


class TestDraftAuthz:
    """
    Draft (L1): all roles read; each role writes own nodes; Ethics can annotate
    any node's support_status.
    """

    def test_draft_annotate_self(self, monkeypatch):
        """Expert annotating its own hypothesis node should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "expert")
        draft.check_draft_annotate_authz(caller_role="expert", node_owner="expert", field=None)

    def test_draft_annotate_status_by_ethics(self, monkeypatch):
        """
        Ethics annotating any node's support_status field should succeed,
        even if the node was written by another role.
        """
        monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
        draft.check_draft_annotate_authz(
            caller_role="ethics",
            node_owner="expert",
            field="support_status",
        )

    def test_draft_annotate_status_by_non_ethics_denied(self, monkeypatch):
        """
        Non-Ethics role annotating another role's node's support_status
        should be denied.
        """
        monkeypatch.setenv("MINIONS_ROLE_NAME", "expert")
        with pytest.raises(PermissionError):
            draft.check_draft_annotate_authz(
                caller_role="expert",
                node_owner="expert-peer",
                field="support_status",
            )
