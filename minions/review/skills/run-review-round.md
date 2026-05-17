---
slug: run-review-round
summary: Execute one formal review round as Area Chair / journal Editor — 3-5 independent reviewer reports before any history, independent revision-delta pass, meta-review packet, EACN publish.
layer: composite
tools:
version: 2
status: active
supersedes:
references: simulate-reviewer-instance, revision-delta, finalize-review-packet, aspect-review
provenance: human
---

# Skill — Run Review Round

One complete formal review round; the orchestration skeleton for the 3-Pass progressive disclosure workflow used by `mos_review_run`.

## When to invoke

- `mos_review_run` has launched you with a submission package and round number.
- Previous-round summary path is or is not provided in the initial prompt (controls Pass B / C).

If the submission package is missing material the review depends on, raise it as a weakness or required revision in the consolidated packet — you do not have an EACN identity to ask for it.

## Structure

The round writes to `branches/shared/reviews/round-<n>/` with `aspect-notes/` inside. Three mutually isolated passes:

- **Pass A** — 3–5 independent reviewer instances see current submission only. No prior summaries, prior reviews, rebuttals, changelogs, or orchestrator paraphrases.
- **Pass B / C** — one dedicated revision-delta subagent reads the previous rolling summary first, then current revision materials. Does not see current-round reviewer reports.
- **Meta-review** — the orchestrator consolidates; writes the packet and rolling summary.

Reviewer count starts at 3; grow to 4 or 5 when submission is complex, when reviewer decisions or major weaknesses materially disagree, or when reviewer 3 surfaces substantial new issues. Stop when the marginal reviewer is largely redundant.

## Procedure

1. **Read the initial prompt.** Confirm submission directory, round number, and whether a prior summary path was provided.
2. **Create the round directory.** `branches/shared/reviews/round-<n>/aspect-notes/`.
3. **Run Pass A first.** Spawn reviewer instances per `simulate-reviewer-instance`. Pass A sees only the current submission package.
4. **Grow from 3.** After the third report, decide on reviewer 4 / 5 per the structure criteria. Stop when reviewer 3 is largely redundant with 1 and 2.
5. **Write `fresh.md`.** Concatenate `reviewer-1.md` through the final generated reviewer report. No summary, no reconciliation.
6. **Run Pass B / C only for revisions.** If a prior summary path was provided, spawn one `revision-delta` subagent. Otherwise write `revision_delta.md` containing only `skipped: no prior summary`.
7. **Write the meta-review packet** using `templates/consolidated.md`: notification, AC / Editor meta-review, exact `## Decision`, revision-delta highlights (if any), every individual reviewer report.
8. **Write the rolling summary** using `templates/summary.md`. Compressed and safe for the next round's Pass B / C.
9. **Finalize** per `finalize-review-packet`. End the run with `consolidated.md` path and decision label on the last line.

End state: `reviewer-<i>.md` files, `fresh.md`, `revision_delta.md`, `consolidated.md`, `summaries/round-<n>.md`. Gru reads `consolidated.md` after `mos_review_run` returns and relays the result on the project's Local EACN.

## Pitfalls

- Treating `fresh.md` as a synthesis. It is a direct concatenation of individual reviews.
- Letting reviewer instances see prior reviews or rebuttals during Pass A.
- Counting the revision-delta subagent as one of the 3–5 reviewer instances.
- Trying to publish on EACN — you have no agent identity; Gru relays after you exit.
