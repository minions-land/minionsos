# Mock-Review Preview — `<artifact slug>`

> **Scope:** evidence-angle preview only. Not a formal review round. Not a formal review decision.
> **Authored by:** Ethics (dev-time mock-review preview / validation set).
> **Target artifact:** `<path/to/artifact>` @ `<commit SHA or revision>`
> **Triggered by:** `<EACN message id / task id / proactive>`
> **Date:** `<YYYY-MM-DD>`

## Summary

One short paragraph: what the artifact claims, where the evidence is strongest, where it is weakest. Evidence-angle only — no style or taste critique.

## Claims and evidence

| # | Claim (short) | Cited evidence | Status |
|---|---|---|---|
| 1 | … | `[evidence: <path \| SHA \| URL \| event-id>]` | `verified` / `unsupported` / `contradicted` / `unclear` |
| 2 | … | … | … |

Add one row per substantive claim. `unsupported` / `contradicted` / `unclear` rows must be expanded in the next section.

## Flagged items

For each non-`verified` row above:

### `<claim short>`

- **Status:** `unsupported` / `contradicted` / `unclear`
- **What the artifact says:** `<verbatim or paraphrase, with path:line>`
- **What the cited evidence actually shows:** `<observation>` `[evidence: <pointer>]`
- **Gap or contradiction:** `<the specific delta>`
- **What would close the gap:** `<concrete pointer, experiment, citation, or rewrite>`

## Citation authenticity (if applicable)

For artifacts with a bibliography or external references — bullet entries that failed citation-authenticity check, each with the bib key, the claimed reference, and the discrepancy. Skip the section if no citations are in scope.

## Reproducibility check (if applicable)

For experiment reports — note any recomputed metric, seed/variance gap, or log/checkpoint that did not match the reported number. Skip if not in scope.

## Informal verdict (optional)

> *informal, non-binding, not a formal review decision:*
> `<one-line evidence-angle estimate, e.g. "evidence holds; would survive scrutiny" or "two unsupported core claims; likely Borderline if submitted today">`

Omit the section entirely if no estimate is warranted. Never use formal review decision labels as an authoritative verdict — this is a dev-time preview, not a review round outcome.

## Recommended next moves

- `<owning Role>`: `<concrete request, e.g. "add citation for Smith 2023 in §2.1" / "rerun seed sweep on baseline B">`
- `<owning Role>`: `<…>`

Keep entries actionable and bounded. If the right move is "ask Gru to run a formal review round via `mos_review_run`", say so explicitly.
