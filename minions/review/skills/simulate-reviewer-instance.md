---
slug: simulate-reviewer-instance
summary: Open during run-review-round Pass A to build one independent reviewer report by composing aspect subagents with mixed stances; outputs reviewer-i.md with one decision label and a complete Epistemic Rigor Summary (D1–D6) table.
layer: logical
tools: Task
version: 3
status: active
supersedes:
references: aspect-review, run-review-round
provenance: human
---

# Skill — Simulate Reviewer Instance

One reviewer instance is a *composite*: several aspect subagents, each inspecting a different part of the submission with a different stance.

## When to invoke

Called by `run-review-round` during Pass A to produce one `reviewer-<i>.md`, where `<i>` is 1–5. May also be invoked directly when the orchestrator needs to add an extra reviewer instance to an existing round (e.g. when reviewer 3 was redundant and a 4th independent perspective is wanted before consolidation).

## Structure

One reviewer instance =

- An assigned reviewer index `<i>` (1–5).
- An aspect mix, drawn from `presentation`, `novelty / related work`, `method / theory`, `experiments / baselines`, `reproducibility / code`, `limitations / scope`. Drop only aspects genuinely irrelevant to this submission.
- A stance mix, drawn from `minions/review/personas/*.md`. Different stances within the same reviewer instance wherever possible — uniform stance collapses the dynamic mix.
- Aspect outputs under `branches/main/reviews/round-<n>/aspect-notes/reviewer-<i>-<aspect>.md`, each using `templates/aspect-note.md`.
- A final report at `reviewer-<i>.md` using `templates/reviewer-instance.md`, with exactly one decision label and a complete "Epistemic Rigor Summary (D1–D6)" table.

### Dimension coverage requirement

Across this instance's aspect mix, the chosen aspects must collectively touch all six rigor dimensions (D1 Evidence Relevance, D2 Falsifiability Quality, D3 Scope Calibration, D4 Argument Coherence, D5 Exploration Integrity, D6 Methodological Rigor) so the instance can fill every row of its rigor summary. The default aspect-to-dimension mapping (see `skills/aspect-review.md`) covers all six when presentation + theory + experiments + reproducibility + limitations are present. If you drop an aspect as irrelevant, make sure the dimensions it carried are still exercised by another aspect, or note in the rigor summary why a dimension is N/A for this submission.

## Procedure

1. **Assign the reviewer index** `reviewer-<i>.md`.
2. **Choose aspects.** Include at least presentation, novelty / related work, method / theory, experiments / baselines, reproducibility / code, limitations / scope when the submission contains those surfaces. Drop only irrelevant ones, but preserve coverage of all six rigor dimensions (see Dimension coverage requirement above).
3. **Choose stances.** Read `minions/review/personas/*.md`. Assign different stances to aspect subagents within this reviewer instance where possible.
4. **Spawn aspect subagents.** Each gets: current submission materials only, its aspect instructions, its stance excerpt, read-only / EACN-invisible / local-only boundary, output path, `templates/aspect-note.md` as the required format, and explicit permission to fan out a nested read-only `Task` subagent (or, for code-trace work that must run scripts, a `Bash`-capable `Task` subagent) for volume reading. Long manuscripts and code-heavy submissions should default to nested `Task` delegation rather than line-by-line reading inside the subagent.
5. **Merge aspect notes.** Read only the aspect notes for this instance and write `reviewer-<i>.md` using `templates/reviewer-instance.md`.
6. **Synthesize the rigor summary.** Aggregate each aspect note's "Rigor Dimensions (D1–D6)" block into the reviewer instance's "Epistemic Rigor Summary (D1–D6)" table: every dimension gets a 1–5 score (1 critical · 2 major gap · 3 adequate · 4 strong · 5 exemplary) plus a strength / weakness / suggestion. When two aspects scored the same dimension, reconcile to one score and keep the lower one's concern visible. Lift every D3 over-claim flag into the explicit over-claim line — never let it stay buried in an aspect note.
7. **Choose the reviewer decision.** Exactly one label: `Strong Accept | Accept | Weak Accept | Borderline | Weak Reject | Reject | Strong Reject`. Decision follows this reviewer's evidence, not the expected meta-review outcome. The rigor table informs the decision but does not compute it — do not derive the label from a dimension average.

Output is a complete `reviewer-<i>.md` with major weaknesses, questions, limitations, required revisions, evidence list, the Epistemic Rigor Summary (D1–D6) table, and `## Decision`.

## Pitfalls

- Giving all aspect subagents the same stance. The dynamic mix is intentional.
- Letting one aspect dominate the reviewer report without evidence.
- Asking aspect subagents to decide workflow scope, poll EACN, or read review history.
- Over-smoothing disagreement between aspect notes. If one aspect strongly changes the decision pressure, preserve that tension.
- Leaving a rigor dimension blank because no single aspect owned it. If the aspect mix left a dimension uncovered, either add an aspect that exercises it or mark it N/A with a reason — do not ship an incomplete rigor table.
- Computing the `## Decision` from the dimension means. The rigor scores inform the decision; they never replace your evidence-weighted judgment.
