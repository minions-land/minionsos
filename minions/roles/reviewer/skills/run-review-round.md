---
slug: run-review-round
summary: Execute one formal review round as Area Chair / journal Editor — 3-5 independent reviewer reports before any history, independent revision-delta pass, meta-review packet, EACN publish.
layer: composite
tools:
version: 2
status: active
supersedes:
references: simulate-reviewer-instance, revision-delta, publish-review-result, aspect-review
provenance: human
---

# Skill — Run Review Round

One complete formal review round; the orchestration skeleton for the Reviewer's 3-Pass progressive disclosure workflow.

## When to invoke

- Reviewer has been assigned a review target for round 1 or a revision.
- The submission package is present and sufficient for Pass A (current-round materials; no prior summaries leaked).

Missing target → ask through Local EACN instead of reviewing work-in-progress.

## Structure

The round writes to `artifacts/reviews/round-<n>/` with `aspect-notes/` inside. Three mutually isolated passes:

- **Pass A** — 3–5 independent reviewer instances see current submission only. No prior summaries, prior reviews, rebuttals, changelogs, or Reviewer-main paraphrases.
- **Pass B / C** — one dedicated revision-delta subagent reads the previous rolling summary first, then current revision materials. Does not see current-round reviewer reports.
- **Meta-review** — Reviewer main consolidates; writes the packet and rolling summary.

Reviewer count starts at 3; grow to 4 or 5 when submission is complex, when reviewer decisions or major weaknesses materially disagree, or when reviewer 3 surfaces substantial new issues. Stop when the marginal reviewer is largely redundant.

## Procedure

1. **Triage the request.** Confirm review target, submitted materials, and whether this is round 1 or a revision.
2. **Create the round directory.** `artifacts/reviews/round-<n>/aspect-notes/`.
3. **Run Pass A first.** Spawn reviewer instances per `simulate-reviewer-instance`. Pass A sees only the current submission package.
4. **Grow from 3.** After the third report, decide on reviewer 4 / 5 per the structure criteria. Stop when reviewer 3 is largely redundant with 1 and 2.
5. **Write `fresh.md`.** Concatenate `reviewer-1.md` through the final generated reviewer report. No summary, no reconciliation.
6. **Run Pass B / C only for revisions.** If `artifacts/reviews/summaries/round-<n-1>.md` exists, spawn one `revision-delta` subagent. Otherwise skip.
7. **Write the meta-review packet** using `templates/consolidated.md`: notification, AC / Editor meta-review, exact `## Decision`, revision-delta highlights (if any), every individual reviewer report.
8. **Write the rolling summary** using `templates/summary.md`. Compressed and safe for the next round's Pass B / C.
9. **Publish** per `publish-review-result`.

End state: `reviewer-<i>.md` files, `fresh.md`, optional `revision_delta.md`, `consolidated.md`, `summaries/round-<n>.md`, and an EACN notification / task pointing at or containing `consolidated.md`.

## Pitfalls

- Treating `fresh.md` as a synthesis. It is a direct concatenation of individual reviews.
- Letting reviewer instances see prior reviews or rebuttals during Pass A.
- Counting the revision-delta subagent as one of the 3–5 reviewer instances.
- Publishing only a short verdict and forcing other roles to chase separate review files. The consolidated packet is self-contained.
