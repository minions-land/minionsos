# Skill — Prepare Rebuttal

Turn a batch of reviewer feedback into a clear, evidence-backed, well-packaged response.

## Core move

Group review issues, decide which need new evidence vs clarification vs concession, coordinate the evidence gathering via EACN, and draft concise response blocks that do not promise what the team cannot deliver.

## Procedure

1. **Ingest reviews.** Read all reviewer reports and Reviewer's consolidated summary at `artifacts/reviews/summaries/` (see Reviewer 3-Pass model). Do not work from individual reviews alone — the consolidated summary already dedupes and prioritizes.
2. **Group issues.** Cluster review points by topic (method, experiments, clarity, related work, claims scope). Within each cluster, rank by severity and by how many reviewers raised it. Shared concerns across reviewers are top priority.
3. **Classify response type per issue.**
   - `new evidence` → needs Experimenter to run something or Expert to provide analysis.
   - `clarification` → prose fix; no new experiment.
   - `scope adjustment` → concede and tighten the claim.
   - `disagreement` → rebut with citation / derivation.
4. **Coordinate evidence requests via EACN.** For each `new evidence` issue, open a targeted request to Experimenter or Expert with the exact question and the deadline. Do not wait on speculative experiments the team cannot finish in the rebuttal window.
5. **Draft response blocks.** One block per issue cluster: restate the concern in one line, state the response, cite the evidence (table / figure / section / new experiment `exp-{id}`). Keep blocks short — reviewers skim rebuttals.
6. **Audit honesty.** No promise of "will do in camera-ready" unless the team actually can. No silent scope expansion. Material weaknesses must be acknowledged, not dodged.
7. **Final pass for consistency** with the paper's existing claims and with what Reviewer's consolidated summary emphasized.

## When to invoke

- When a batch of reviews arrives and the rebuttal window opens.
- When camera-ready requires addressing remaining reviewer concerns (smaller scope, same discipline).

## Pitfalls

- Responding issue-by-issue in review order instead of grouping. Reviewers see disorganization; the area chair sees confusion.
- Over-promising future work that the team has no capacity for.
- Silently rewriting a claim rather than explicitly acknowledging the scope change.

## Output habit

Draft under `branches/writer/paper/rebuttal/` with one file per response block; link the source review point and the supporting evidence. Every evidence cite is marked `[derived: artifacts/exp-<id>/report.md]` or `[derived: section <N>]` per root §9.
