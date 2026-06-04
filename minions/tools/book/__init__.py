"""Book module - Memory system for MinionsOS.

This package splits the monolithic book.py (3146 lines) into focused modules:
- query.py - BM25 retrieval and search
- ingest.py - Source ingestion and indexing
- promote.py - Content promotion and ratification
- audit.py - Contradiction detection and resolution
- utils.py - Shared utilities (imported from book_utils)

All public APIs are re-exported here for backward compatibility.
"""

# Import everything from the original book.py functions
# This maintains 100% backward compatibility
from minions.tools.book_impl import (
    # Public API - all mos_book_* functions
    mos_book_audit_walk,
    mos_book_crystallize_session,
    mos_book_dead_end,
    mos_book_ingest,
    mos_book_ingest_batch,
    mos_book_lint,
    mos_book_open_question,
    mos_book_promote_verified,
    mos_book_query,
    mos_book_ratify,
    mos_book_resolve_contradiction,
    mos_book_save_synthesis,
    mos_book_scan_edges,
)

__all__ = [
    "mos_book_audit_walk",
    "mos_book_crystallize_session",
    "mos_book_dead_end",
    "mos_book_ingest",
    "mos_book_ingest_batch",
    "mos_book_lint",
    "mos_book_open_question",
    "mos_book_promote_verified",
    "mos_book_query",
    "mos_book_ratify",
    "mos_book_resolve_contradiction",
    "mos_book_save_synthesis",
    "mos_book_scan_edges",
]
