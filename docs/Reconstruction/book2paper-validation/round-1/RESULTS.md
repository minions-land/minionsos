# Book→Paper validation — Round 1 (real data, end-to-end, no human)

**Input Book:** hand-built Book of the ResNet paper (He et al. 2015), a local-only validation fixture.
**Ground truth:** `examples/resnet-paper.pdf` (12 pages).
**Generated:** `round-1/paper/main.pdf` (13 pages, 6 sections, 8 tables, 3 figures), compiled with real `latexmk`.

## Scores vs ground-truth

| Axis | Score | Biggest gap |
|---|---|---|
| Evidence fidelity | 4/5 | Table NUMBERS perfect (0 invented/rounded across 9 tables). Non-numeric gaps: dropped caption qualifiers (e.g. Table 3 "VGG-16 based on our test"); a "throughout training" trajectory claim backed only by an endpoint table. |
| Claim coverage & scope | 4/5 | One **over-claim**: intro "can be ruled out" where Book says "argue (but do not formally prove)" / "unlikely". Dropped abstract headline: the 4-competition 1st-place sweep (kept ILSVRC, dropped the tail). |
| Structure / typography | 3/5 | Single-column 11pt report, not a two-column CV/ML venue paper. Missing signature conceptual diagrams (residual block, architecture). No `\appendix` tier. Conclusion forced even though the truth folds it in. |

**Mean ≈ 3.7 — NOT converged.** Generation itself is a clear success (real PDF, exact numbers); the gap is (a) one honesty defect (modality escalation) which is the highest-priority fix per our anti-overclaim value, and (b) venue-shape/figure polish.

## Round-2 skill deltas applied (book-to-paper.md v1→v2)

1. **Over-claim modality lint** (honesty, top priority): preserve source epistemic modality — `argue/unlikely/suggest` may NOT escalate to `ruled out/proven/established/eliminated`.
2. **Scope reconciliation**: diff `Book.md` abstract/claims_summary vs `logic/claims.md`; a headline asserted in the abstract but absent from claims must be surfaced or explicitly logged as an intentional drop — never silently truncated. Includes a list-truncation guard.
3. **Caption fidelity**: render `evidence/` table captions' methodological qualifiers verbatim; coverage ledger audits caption diffs, not just numbers.
4. **Trajectory-evidence rule**: a dynamic/temporal claim ("throughout training") backed only by an endpoint table must be hedged + flagged, never stated as if a curve shows it.
5. **Venue/format selector**: Book frontmatter (`venue`/`domain`) drives a two-column class for CV/ML venues, not a single-column default.
6. **Conceptual-figure path**: render schematic diagrams (TikZ) for `solution/architecture.md` component graphs + `algorithm.md` blocks — the method's signature visual, not an algorithm listing.
7. **Conditional conclusion + appendix tier**: fold the wrap-up into experiments when the venue omits a standalone conclusion; route substrate/secondary tables into `\appendix`.
