"""Contract test: Book→Paper skill layout coupling.

The book-to-paper skill (minions/roles/common/skills/book-to-paper.md) maps
Book-layout directories to paper sections. Its generation step is LLM-driven
and validated empirically, so it cannot be unit-tested for output quality. But
the *coupling* between the skill's consumed layout and the layout the worktree
actually seeds CAN be pinned:

    skill consumes:  Book.md, logic/, src/, evidence/  (+ proposal/)
    worktree seeds:  SHARED_SUBDIRS in _project_worktree.py

If a future worktree refactor renames `logic/` → `reasoning/` (or drops
`evidence/`), Book→Paper generation would silently break — the skill would look
for a directory that no longer exists. This test fails loudly at that moment.

This is the deterministic guard around the otherwise-empirical Book→Paper step.
"""

from __future__ import annotations

from minions.lifecycle._project_worktree import SHARED_SUBDIRS
from minions.paths import ROLES_DIR

# The Book-layout directories the book-to-paper skill reads to build each
# paper section. Sourced from the skill's own layer→section table. If the skill
# changes which directories it consumes, update this set in the same commit.
_BOOK_LAYOUT_CONSUMED_BY_SKILL = {
    "logic",  # problem, claims, concepts, experiments, solution/, related_work
    "src",  # configs, environment → methodology substrate
    "evidence",  # tables, figures → experiments numbers
    "proposal",  # pre-project materials
    "book",  # Book.md root manifest lives under the book surface
}


def _skill_body() -> str:
    path = ROLES_DIR / "common" / "skills" / "book-to-paper.md"
    assert path.exists(), "book-to-paper skill is missing — Book→Paper step has no driver"
    return path.read_text(encoding="utf-8")


def test_book_layout_consumed_by_skill_is_seeded_by_worktree() -> None:
    """Every Book-layout dir the skill reads must actually be seeded on main."""
    seeded = set(SHARED_SUBDIRS)
    missing = _BOOK_LAYOUT_CONSUMED_BY_SKILL - seeded
    assert not missing, (
        f"book-to-paper skill consumes Book-layout dirs the worktree no longer "
        f"seeds: {sorted(missing)}. Either restore them in SHARED_SUBDIRS or "
        f"update the skill's layer→section map. Book→Paper generation would "
        f"silently break otherwise."
    )


def test_book_to_paper_skill_pins_section_order() -> None:
    """The skill must name the fixed section order Book→Paper generates in.

    The user fixed this order: abstract → introduction → related work →
    methodology → experiments → conclusion. Pin it so a careless edit can't
    drop a section or reorder silently.
    """
    body = _skill_body().lower()
    for section in (
        "abstract",
        "introduction",
        "related work",
        "methodology",
        "experiments",
        "conclusion",
    ):
        assert section in body, (
            f"book-to-paper skill no longer names the '{section}' section — "
            f"the fixed paper section order is broken"
        )


def test_book_to_paper_skill_names_layer_sources() -> None:
    """The skill's layer→section map must reference the real Book directories.

    Guards the other direction of the coupling: the skill body must mention
    each consumed directory by name, so the map can't drift to phantom dirs.
    """
    body = _skill_body()
    for layer in ("logic/", "src/", "evidence/", "Book.md"):
        assert layer in body, (
            f"book-to-paper skill's section map no longer references '{layer}' — "
            f"the Book→Paper layer mapping has drifted from the real layout"
        )


def test_book_to_paper_skill_pins_comment_provenance_rule() -> None:
    """The skill must require Book provenance as %-comments, invisible in the PDF.

    User contract: every paper sentence traces to a Book source, but that source
    index must live in LaTeX `%` comments (stripped by the compiler) — never as
    visible body text. If a careless edit drops this rule, generated papers would
    either lose traceability or leak the source index into the rendered PDF.
    """
    body = _skill_body()
    # The rule must name the %-comment mechanism and the [VERIFY] header shape.
    assert "% [VERIFY]" in body, (
        "book-to-paper skill no longer specifies the `% [VERIFY]` provenance "
        "header — Book→Paper provenance comments are unpinned"
    )
    # It must state the load-bearing property: comments are stripped from the PDF.
    body_lower = body.lower()
    assert "stripped" in body_lower and "pdf" in body_lower, (
        "book-to-paper skill no longer states that `%` provenance comments are "
        "stripped from the PDF — the invisible-to-reader guarantee is unpinned"
    )
    # Visible provenance must be called out as an anti-pattern.
    assert "visible provenance" in body_lower, (
        "book-to-paper skill no longer flags 'visible provenance' as an "
        "anti-pattern — rendered source indexes could leak into the PDF"
    )
