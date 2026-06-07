"""Pin invariants for the review MCP tool and its prompt assets.

Review rounds are run by the ``mos_review_run`` MCP tool. This module pins:

1. The checklist gate parser correctly accepts ✓/X-checked Required items
   and rejects empty / ✗-marked items.
2. The Decision-label extractor finds the canonical labels in
   consolidated.md.
3. The review prompt assets exist at the expected paths.
"""

from __future__ import annotations

from pathlib import Path

from minions.paths import REVIEW_DIR
from minions.tools.review import (
    DECISION_LABELS,
    _extract_decision,
    parse_checklist,
)


class TestReviewAssets:
    def test_system_prompt_exists(self) -> None:
        system = REVIEW_DIR / "SYSTEM.md"
        assert system.is_file()
        text = system.read_text(encoding="utf-8")
        assert "Area-Chair" in text or "Area Chair" in text
        assert "mos_review_run" in text
        assert "Pass A" in text and "Pass B" in text and "Pass C" in text

    def test_review_skills_present(self) -> None:
        skills = REVIEW_DIR / "skills"
        assert skills.is_dir()
        names = {p.stem for p in skills.glob("*.md")}
        assert {
            "run-review-round",
            "simulate-reviewer-instance",
            "aspect-review",
            "code-validity-review",
            "revision-delta",
            "finalize-review-packet",
        }.issubset(names)

    def test_review_personas_present(self) -> None:
        personas = REVIEW_DIR / "personas"
        assert personas.is_dir()
        assert any(personas.glob("*.md"))

    def test_review_templates_present(self) -> None:
        tpl = REVIEW_DIR / "templates"
        assert tpl.is_dir()
        names = {p.stem for p in tpl.glob("*.md")}
        assert {
            "aspect-note",
            "reviewer-instance",
            "fresh",
            "revision_delta",
            "consolidated",
            "summary",
            "submission-checklist",
        }.issubset(names)


class TestChecklistGate:
    def test_all_required_checked_passes(self) -> None:
        body = """
## Required (all must be checked ✓)

- [✓] Problem statement
- [✓] Literature survey
- [✓] Main experiment
- [✓] Baseline comparison
- [✓] Ablation study
- [✓] Case visualization

## Conditionally required (mark N/A with justification if not applicable)

- [ ] Mathematical formulation
"""
        result = parse_checklist(body)
        assert result.passed
        assert result.missing_required == []

    def test_unchecked_required_item_rejects(self) -> None:
        body = """
## Required

- [✓] Problem statement
- [ ] Main experiment
- [✗] Baseline comparison
"""
        result = parse_checklist(body)
        assert not result.passed
        assert any("Main experiment" in item for item in result.missing_required)
        assert any("Baseline comparison" in item for item in result.missing_required)

    def test_x_marked_item_passes(self) -> None:
        # Some authors use lowercase x rather than ✓.
        body = """
## Required

- [x] Problem statement
- [X] Main experiment
"""
        assert parse_checklist(body).passed

    def test_conditional_section_does_not_block(self) -> None:
        # An unchecked item under "Conditionally required" must not gate the run.
        body = """
## Required

- [✓] Problem statement
- [✓] Main experiment

## Conditionally required

- [ ] Mathematical formulation
"""
        assert parse_checklist(body).passed

    def test_missing_required_section_treats_no_items_as_pass(self) -> None:
        # If there is no Required section, there are no required items to fail —
        # the tool's caller is expected to also verify the file exists upstream.
        body = "## Strongly recommended\n\n- [ ] SOTA baseline\n"
        result = parse_checklist(body)
        assert result.passed
        assert result.missing_required == []


class TestDecisionExtraction:
    def test_extracts_each_canonical_label(self, tmp_path: Path) -> None:
        for label in DECISION_LABELS:
            f = tmp_path / f"{label.replace(' ', '_')}.md"
            f.write_text(
                f"# Round 1 Consolidated\n\n## Decision\n\n{label}\n\nbody...\n",
                encoding="utf-8",
            )
            assert _extract_decision(f) == label

    def test_returns_none_when_no_decision_section(self, tmp_path: Path) -> None:
        f = tmp_path / "no_decision.md"
        f.write_text("# Round 1\n\n## Notes\n\nstuff\n", encoding="utf-8")
        assert _extract_decision(f) is None

    def test_returns_none_for_unknown_label(self, tmp_path: Path) -> None:
        f = tmp_path / "weird.md"
        f.write_text("## Decision\n\nMaybe Accept?\n", encoding="utf-8")
        assert _extract_decision(f) is None

    def test_handles_emphasis_around_label(self, tmp_path: Path) -> None:
        f = tmp_path / "emph.md"
        f.write_text("## Decision\n\n**Weak Accept**\n", encoding="utf-8")
        assert _extract_decision(f) == "Weak Accept"
