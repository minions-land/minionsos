---
slug: revision-delta
summary: Run the independent Pass B / Pass C revision check — one dedicated local subagent reads only the previous rolling summary, then checks current submission and rebuttal against it.
layer: logical
tools:
version: 2
status: active
supersedes:
references: run-review-round
provenance: human
---

# Skill — Revision Delta

Independent revision-check state. The revision-delta subagent is deliberately blind to current-round reviewer reports to preserve that independence.

## When to invoke

- During `run-review-round` if `artifacts/reviews/summaries/round-<n-1>.md` exists.
- First-round reviews have no prior summary; skip this skill. If downstream tooling expects the file, Reviewer main may write a minimal placeholder saying `skipped: no prior summary`.

## Structure

Two bounded reading passes:

- **Pass B (previous summary only)** — read `artifacts/reviews/summaries/round-<n-1>.md`. Do not read older summaries, older round directories, current `reviewer-<i>.md`, current `fresh.md`, or current `consolidated.md`.
- **Pass C (current revision materials)** — read the current submission and any author changelog / rebuttal attached to the review request.

Output is `revision_delta.md` using `templates/revision_delta.md`; for each prior issue, status ∈ {resolved, unresolved, insufficiently addressed, contradicted by rebuttal}, plus any new issues the revision itself introduced.

## Procedure

1. **Pass B: read previous summary only.** `artifacts/reviews/summaries/round-<n-1>.md`. Nothing else.
2. **Extract the prior issue checklist.** Compress the previous summary into concrete issues to verify.
3. **Pass C: read current revision materials.** Current submission and any author changelog / rebuttal attached to the review request.
4. **Assess resolution.** For each prior issue: resolved / unresolved / insufficiently addressed / contradicted by the rebuttal.
5. **Check introduced issues.** Note new problems caused by the revision itself.
6. **Write `revision_delta.md`** using `templates/revision_delta.md`. Keep it evidence-oriented: prior issue, current evidence, status, bottom line for the meta-review.

## Pitfalls

- Looking at current-round reviewer reports. This breaks the independent revision-check state.
- Re-litigating old raw reviews. The previous summary is the only allowed historical input.
- Treating author rebuttal claims as true without checking the current submission materials.
