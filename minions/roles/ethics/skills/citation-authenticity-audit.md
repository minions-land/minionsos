# Skill — Citation Authenticity Audit

Verify that every `.bib` entry and every Reviewer-cited prior work actually exists and matches the claimed author / year / venue / title.

## Core move

Hallucinated citations are the single highest-signal Ethics failure mode and the easiest to catch with web verification. For every audited batch, pick a sampled subset of citations, confirm each against an authoritative source, and flag mismatches.

## Procedure

1. **Scope the batch.** Decide whether this is a full sweep (e.g. before a submission gate) or a statistical sample (e.g. a periodic audit). For a sample, pick 20-30% of entries randomly, weighted toward: recently added entries, entries cited in high-stakes claims, entries near the abstract / introduction where hallucinations land readers, and entries in areas the project Expert did **not** produce.
2. **Collect the cite sites.** Build `(bib_key, sentence, file, line)` tuples for each audited entry so the claim context is preserved. For Reviewer-cited prior work that lives in review artifacts rather than a `.bib`, record `(review_round, reviewer_instance, quote)` instead.
3. **Verify each entry independently.** For each `(bib_key, claimed_title, claimed_authors, claimed_venue, claimed_year)`:
   - Web-search the exact title plus first author. Prefer the venue's own proceedings, arXiv, or DOI resolvers over aggregator pages.
   - Record the canonical URL, canonical title, canonical authors, canonical venue, canonical year.
   - Classify as `verified` (all four match), `drift` (entry exists but one or more fields differ — common for arXiv-vs-published mismatches), `wrong_context` (entry exists but does not say what the cite site claims), or `fabricated` (no such paper found).
4. **Spot-check the claim, not just the title.** For high-stakes citations, open the source and check whether the sentence that cites it is actually supported by the cited paper's claims. A real paper cited for a false claim is still an Ethics failure.
5. **Write the output.** For every `drift` / `wrong_context` / `fabricated` entry, write a flag file at `artifacts/ethics/flags/open/<slug>.md` with: bib_key, cite site, claimed vs actual, canonical URL, severity, and a short remediation suggestion (remove, replace, rewrite the sentence). Summarise the batch in `artifacts/ethics/reports/report-<ts>.md` with counts per classification.
6. **Announce on EACN.** One short `mos_send_message` to the cite site's author Role (Writer for `.bib` entries, Reviewer for review-artifact cites) pointing at the flag files; do not paste the full report into EACN.

## When to invoke

- Before any submission gate (initial submission, rebuttal, camera-ready).
- On any round that materially changes the bibliography (new related-work section, new method comparison, new reviewer-requested prior-work addition).
- Periodically during active writing phases so hallucinations do not accumulate.
- On demand when Gru or the author requests a citation sweep.

## Pitfalls

- Verifying only the title and skipping the venue. Hallucinated venues are common.
- Accepting aggregator pages (ResearchGate, academic-mirror sites) as canonical. Use the venue or arXiv directly.
- Flagging `drift` as `fabricated`. Reserve `fabricated` for entries with no real paper behind them.
- Auditing entries the project Expert produced without independent verification: the Expert may share the same hallucination. Always verify independently.
- Letting the report grow into a narrative. Keep reports operational: classification counts, flag pointers, remediation.

## Output habit

- Each flag file cites the canonical URL and the claim it fails to support. Resolved flags move to `artifacts/ethics/flags/resolved/` with a short note on what fixed it.
- Report files are dated and stay under `artifacts/ethics/reports/`.
- Every report and flag is marked with `[evidence: <URL|commit|EACN event id>]` per the Evidence-first EACN communication convention.
