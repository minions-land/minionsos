---
slug: citation-authenticity-audit
summary: Verify every .bib entry and review-cited prior work actually exists and matches the claimed author / year / venue / title; hallucinated citations are the highest-signal Ethics failure.
layer: logical
tools: eacn3_send_message
version: 2
status: active
supersedes:
references: evidence-pointer-sweep
provenance: human
---

# Skill — Citation Authenticity Audit

Hallucinated citations are the single highest-signal Ethics failure mode and the easiest to catch with web verification. Sample, verify, flag.

## When to invoke

- Before any submission gate (initial submission, rebuttal, camera-ready).
- On any round that materially changes the bibliography (new related-work section, new method comparison, new review-requested prior-work addition).
- Periodically during active writing phases so hallucinations do not accumulate.
- On demand when Gru or the author requests a citation sweep.

Experts run the full pre-submission citation sweep on the entire `.bib` before a submission gate. Ethics performs independent sampled oversight in the same window to catch drift, hallucinated entries, and wrong-context cites.

## Structure

Each audited entry is classified `verified` (all four fields match), `drift` (entry exists but ≥ 1 field differs — common arXiv-vs-published case), `wrong_context` (entry exists but does not say what the cite site claims), or `fabricated` (no such paper found). Outputs:

- Per-flag file: draft in `branches/ethics/flag-<slug>.md`, publish to `branches/shared/ethics/flag-<slug>.md` — bib_key, cite site, claimed vs actual, canonical URL, severity, remediation, status.
- Batch report: draft in `branches/ethics/report-<ts>.md`, publish to `branches/shared/ethics/report-<ts>.md` — counts per classification.
- EACN ping to the cite site's author Role; for review-artifact cites, identify the `review_round` and `reviewer_instance` metadata. Do not paste full reports into EACN.

Verification sources: venue proceedings, arXiv, DOI resolvers — never aggregator pages.

## Procedure

1. **Scope the batch.** Full sweep (submission gate) or statistical sample (periodic audit). For a sample, pick 20–30 % of entries weighted toward: recently added entries, entries cited in high-stakes claims, entries near the abstract / introduction, entries in areas the project Expert did **not** produce.
2. **Collect cite sites.** Tuples of `(bib_key, sentence, file, line)`. For review-cited prior work in review artifacts, use `(review_round, reviewer_instance, quote)`.
3. **Verify each entry independently.** For each `(bib_key, claimed_title, claimed_authors, claimed_venue, claimed_year)`: web-search exact title plus first author (prefer venue / arXiv / DOI), record canonical URL / title / authors / venue / year, classify per the four-category scheme.
4. **Spot-check the claim, not just the title.** For high-stakes citations, open the source and check whether the citing sentence is supported by the cited paper's claims. A real paper cited for a false claim is still an Ethics failure.
5. **Write the output.** One flag file per `drift` / `wrong_context` / `fabricated` entry; one summary report per batch with counts.
6. **Publish and announce on EACN.** Publish reports and flags to `branches/shared/ethics/` via `mos_publish_to_shared`, then send a short `eacn3_send_message` to the affected author Role pointing at the flag files. Resolved flags stay in the flat shared layout with `status: resolved` and a short note. Every report and flag is marked `[evidence: <URL|commit|EACN event id>]`.

## Pitfalls

- Verifying only the title and skipping the venue. Hallucinated venues are common.
- Accepting aggregator pages (ResearchGate, academic-mirror sites) as canonical. Use the venue or arXiv directly.
- Flagging `drift` as `fabricated`. Reserve `fabricated` for entries with no real paper behind them.
- Auditing entries the project Expert produced without independent verification: the Expert may share the same hallucination.
- Letting the report grow into a narrative. Keep reports operational.
