"""
Cross-cutting authz tests for MinionsOS Memory V2 permission matrix.

SPEC PINNING NOTE: Some tests in this file are interface specifications for
streams that may not yet be merged into main at the time of writing:

  - Stream 1 (Reel V2): adds ethics cross-read exception in minions/tools/reel.py
    Tests: test_reel_cross_read_allowed_for_ethics, test_reel_cross_read_denied_for_peer
    These tests will XFAIL until Stream 1 merges.

  - Stream 3 (Book V2): adds mos_book_ratify with ethics-only authz in
    minions/tools/book.py (or similar)
    Tests: test_book_ratify_only_ethics
    These tests will XFAIL until Stream 3 merges.

All other tests (self-read, Gru cross-read, draft annotate) cover existing
behaviour and should pass on main.

Permission matrix being tested:

  Layer         | Self | Other Role | Noter | Ethics         | Gru
  Reel-Index    | RW   | —          | —     | R (cross-role) | R
  Draft         | RW   | R          | RW    | R + status W   | R
  Book          | R    | R          | W     | R + ratify     | R
  Shelf         | —    | —          | —     | —              | RW
"""

import importlib
import os
import sys
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_reel():
    """Import minions.tools.reel, skip if not importable."""
    try:
        return importlib.import_module("minions.tools.reel")
    except ImportError:
        pytest.skip("minions.tools.reel not importable")


def _import_book():
    """Import minions.tools.book, skip if not importable."""
    try:
        return importlib.import_module("minions.tools.book")
    except ImportError:
        pytest.skip("minions.tools.book not importable")


def _import_draft():
    """Import minions.tools.draft, skip if not importable."""
    try:
        return importlib.import_module("minions.tools.draft")
    except ImportError:
        pytest.skip("minions.tools.draft not importable")


# ---------------------------------------------------------------------------
# Reel authz tests
# ---------------------------------------------------------------------------

class TestReelAuthz:
    """
    Reel-Index (L0): self RW; Ethics + Gru cross-read; all others denied;
    Noter excluded entirely.
    """

    def test_reel_self_read(self, monkeypatch):
        """Coder reading its own reel index should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        reel = _import_reel()
        check = getattr(reel, "check_reel_read_authz", None)
        if check is None:
            pytest.skip("check_reel_read_authz not yet implemented (Stream 1)")
        # Reading own role — should not raise
        check(caller_role="coder", target_role="coder")

    def test_reel_cross_read_denied_for_peer(self, monkeypatch):
        """Coder reading Expert reel should be denied (PermissionError)."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        reel = _import_reel()
        check = getattr(reel, "check_reel_read_authz", None)
        if check is None:
            pytest.xfail("check_reel_read_authz not yet implemented (Stream 1 pending)")
        with pytest.raises(PermissionError):
            check(caller_role="coder", target_role="expert-ml")

    def test_reel_cross_read_allowed_for_ethics(self, monkeypatch):
        """Ethics reading Coder reel cross-role should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
        reel = _import_reel()
        check = getattr(reel, "check_reel_read_authz", None)
        if check is None:
            pytest.xfail("check_reel_read_authz not yet implemented (Stream 1 pending)")
        # Ethics cross-read — should not raise
        check(caller_role="ethics", target_role="coder")

    def test_reel_cross_read_allowed_for_gru(self, monkeypatch):
        """Gru reading any role's reel should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "gru")
        reel = _import_reel()
        check = getattr(reel, "check_reel_read_authz", None)
        if check is None:
            pytest.skip("check_reel_read_authz not yet implemented (Stream 1)")
        for target in ("coder", "ethics", "noter", "writer", "expert-phys"):
            check(caller_role="gru", target_role=target)

    def test_reel_noter_excluded(self, monkeypatch):
        """Noter has no reel access at all — even self-read should be denied."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "noter")
        reel = _import_reel()
        check = getattr(reel, "check_reel_read_authz", None)
        if check is None:
            pytest.xfail("check_reel_read_authz not yet implemented (Stream 1 pending)")
        with pytest.raises(PermissionError):
            check(caller_role="noter", target_role="noter")


# ---------------------------------------------------------------------------
# Book authz tests
# ---------------------------------------------------------------------------

class TestBookAuthz:
    """
    Book (L2): Note-only writes; Ethics ratifies; all others read-only.
    """

    def test_book_ratify_only_ethics(self, monkeypatch):
        """
        Only Ethics may call mos_book_ratify.
        Coder calling it should raise BookError (or PermissionError).
        Ethics calling it should succeed (or return without authz error).
        """
        book = _import_book()
        check = getattr(book, "check_book_ratify_authz", None)
        if check is None:
            pytest.xfail("check_book_ratify_authz not yet implemented (Stream 3 pending)")

        # Coder should be denied
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        BookError = getattr(book, "BookError", PermissionError)
        with pytest.raises((BookError, PermissionError)):
            check(caller_role="coder")

        # Ethics should pass
        monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
        check(caller_role="ethics")  # should not raise


# ---------------------------------------------------------------------------
# Draft authz tests
# ---------------------------------------------------------------------------

class TestDraftAuthz:
    """
    Draft (L1): all roles read; each role writes own nodes; Ethics can annotate
    any node's support_status.
    """

    def test_draft_annotate_self(self, monkeypatch):
        """Coder annotating its own hypothesis node should succeed."""
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        draft = _import_draft()
        check = getattr(draft, "check_draft_annotate_authz", None)
        if check is None:
            pytest.skip("check_draft_annotate_authz not yet implemented")
        # annotating own node (no field restriction)
        check(caller_role="coder", node_owner="coder", field=None)

    def test_draft_annotate_status_by_ethics(self, monkeypatch):
        """
        Ethics annotating any node's support_status field should succeed,
        even if the node was written by another role.
        """
        monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
        draft = _import_draft()
        check = getattr(draft, "check_draft_annotate_authz", None)
        if check is None:
            pytest.skip("check_draft_annotate_authz not yet implemented")
        # Ethics cross-annotating Coder's node's status field
        check(caller_role="ethics", node_owner="coder", field="support_status")

    def test_draft_annotate_status_by_non_ethics_denied(self, monkeypatch):
        """
        Non-Ethics role annotating another role's node's support_status
        should be denied.
        """
        monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
        draft = _import_draft()
        check = getattr(draft, "check_draft_annotate_authz", None)
        if check is None:
            pytest.skip("check_draft_annotate_authz not yet implemented")
        with pytest.raises(PermissionError):
            check(caller_role="coder", node_owner="writer", field="support_status")
