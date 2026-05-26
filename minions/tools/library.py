"""Library (L4) — cross-project transferable knowledge — interface stub.

STATUS: development interface only. No live functionality. This module
defines the intended API surface so callers can import the symbols without
breaking; every function raises ``NotImplementedError`` with a clear
message until V4 is implemented.

V4 DESIGN NOTES (fill in before activating):
  - Purpose: Library is the layer above Shelf. Where Shelf aggregates
    per-project graphs into a queryable cross-project index, Library
    extracts *reusable, transferable knowledge* — methods, theorems,
    dead-ends, open questions — that can seed a new project.
  - Source: curated subset of Book pages (``paper_role ∈ {theorem,
    method, limitation, future_work}`` + ``status ∈ {verified, refuted}``)
    from multiple projects, filtered by Gru / Ethics ratification.
  - Storage: ``~/.minionsos/library.json`` (global, Gru-only write).
  - Authz: Gru writes; all project Roles can read (query) via
    ``mos_library_query``; no Role writes directly.
  - Key operations:
      mos_library_ingest(port)          # Gru: pull ratified Book pages into Library
      mos_library_query(text, ...)      # all Roles: search transferable knowledge
      mos_library_link(lib_slug, port)  # Gru: link a Library entry to a project's Book
  - Trigger: Gru-on-project-close or Gru-manual; not automatic.
  - Deduplication: same claim from N projects should collapse into one
    Library entry with N project_ports listed as sources.

Relationship to Shelf:
  Shelf is structural (graph of concepts and their cross-project
  relationships). Library is semantic (curated claims ready to seed new
  work). They are complementary; a Library entry may reference a
  Shelf node for graph context.
"""

from __future__ import annotations


def mos_library_ingest(port: int) -> dict[str, object]:
    """(V4-FUTURE) Pull ratified Book pages from project *port* into Library."""
    raise NotImplementedError(
        "Library (L4) is not yet implemented. "
        "See minions/tools/library.py docstring for V4 design notes."
    )


def mos_library_query(
    text: str,
    *,
    status_filter: str | None = None,
    paper_role_filter: str | None = None,
    max_results: int = 10,
) -> dict[str, object]:
    """(V4-FUTURE) Search Library for transferable knowledge matching *text*."""
    raise NotImplementedError(
        "Library (L4) is not yet implemented. "
        "See minions/tools/library.py docstring for V4 design notes."
    )


def mos_library_link(
    lib_slug: str,
    port: int,
    *,
    book_slug: str | None = None,
) -> dict[str, object]:
    """(V4-FUTURE) Link a Library entry to a project's Book page."""
    raise NotImplementedError(
        "Library (L4) is not yet implemented. "
        "See minions/tools/library.py docstring for V4 design notes."
    )


__all__ = [
    "mos_library_ingest",
    "mos_library_query",
    "mos_library_link",
]
