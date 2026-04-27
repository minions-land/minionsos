# Skill - Run Review Round

Execute one complete formal review round as an Area Chair / journal Editor.

## Core Move

Produce 3-5 independent reviewer reports before reading any historical review
context, then run the independent revision-delta path, write the meta-review
packet, and publish the result through Local EACN.

## Procedure

1. **Triage the request.** Confirm the review target, submitted materials, and
   whether this is round 1 or a revision. If the target is missing, ask for it
   through Local EACN instead of reviewing work-in-progress.
2. **Create the round directory.** Use `artifacts/reviews/round-<n>/` with
   `aspect-notes/` inside it.
3. **Run Pass A first.** Spawn reviewer instances using
   `skills/simulate-reviewer-instance.md`. Pass A sees only the current
   submission package. It does not see prior summaries, prior reviews, rebuttals,
   changelogs, or Reviewer-main paraphrases of those materials.
4. **Start with 3 reviewer instances.** After the third report, decide whether
   to create reviewer 4 or 5:
   - continue for complex submissions, mixed theory/experiment claims, extensive
     code/reproduction surfaces, or high-stakes revision history;
   - continue when reviewer decisions or major weaknesses materially disagree;
   - continue when reviewer 3 surfaces substantial new issues;
   - stop when reviewer 3 is largely redundant with reviewers 1 and 2.
5. **Write `fresh.md`.** Concatenate `reviewer-1.md` through the final generated
   reviewer report. Do not summarize or reconcile them in `fresh.md`.
6. **Run Pass B / C only for revisions.** If
   `artifacts/reviews/summaries/round-<n-1>.md` exists, spawn one dedicated
   revision-delta subagent using `skills/revision-delta.md`. If it does not
   exist, skip Pass B / C.
7. **Write the meta-review packet.** Use `templates/consolidated.md`. Include
   the notification, Area-Chair / Editor meta-review, exact `## Decision`, any
   revision-delta highlights, and every individual reviewer report.
8. **Write the rolling summary.** Use `templates/summary.md`. Keep it compressed
   and safe for the next round's Pass B / C.
9. **Publish the result.** Use `skills/publish-review-result.md` to create a
   Local EACN task or message containing the full consolidated packet when
   feasible.

## Pitfalls

- Treating `fresh.md` as a synthesis. It is only a direct concatenation of
  individual reviews.
- Letting reviewer instances see prior reviews or rebuttals during Pass A.
- Counting the revision-delta subagent as one of the 3-5 reviewer instances.
- Publishing only a short verdict and forcing other roles to chase separate
  review files. The consolidated packet should be self-contained.

## Output Habit

At the end of the skill, the round should have `reviewer-<i>.md`, `fresh.md`,
optional `revision_delta.md`, `consolidated.md`, and
`summaries/round-<n>.md`, plus an EACN notification/task pointing at or
containing `consolidated.md`.
