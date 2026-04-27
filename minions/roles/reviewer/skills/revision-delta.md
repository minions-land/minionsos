# Skill - Revision Delta

Run the independent Pass B / Pass C revision check.

## Core Move

A dedicated local revision-delta subagent reads only the previous rolling
summary first, then checks the current submission and author rebuttal/changelog
against that summary. It does not read current-round reviewer reports.

## Procedure

1. **Pass B: read previous summary only.** Read
   `artifacts/reviews/summaries/round-<n-1>.md`. Do not read older summaries,
   older round directories, current `reviewer-<i>.md`, current `fresh.md`, or
   current `consolidated.md`.
2. **Extract the prior issue checklist.** Compress the previous summary into
   concrete issues to verify.
3. **Pass C: read current revision materials.** Read the current submission and
   any author changelog / rebuttal attached to the review request.
4. **Assess resolution.** For each prior issue, mark resolved, unresolved,
   insufficiently addressed, or contradicted by the rebuttal.
5. **Check introduced issues.** Note new problems caused by the revision itself.
6. **Write `revision_delta.md`.** Use `templates/revision_delta.md`.

## First Round

If no previous summary exists, skip this skill. Reviewer main may write a minimal
placeholder saying `skipped: no prior summary` only if downstream tooling expects
the file.

## Pitfalls

- Looking at current-round reviewer reports. This breaks the independent
  revision-check state.
- Re-litigating old raw reviews. The previous summary is the only allowed
  historical input.
- Treating author rebuttal claims as true without checking the current
  submission materials.

## Output Habit

Keep the delta evidence-oriented: prior issue, current evidence, status, and
bottom line for the meta-review.
