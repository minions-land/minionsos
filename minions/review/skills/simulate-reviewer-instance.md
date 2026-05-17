---
slug: simulate-reviewer-instance
summary: Open during run-review-round Pass A to build one independent reviewer report by composing aspect subagents with mixed stances; outputs reviewer-i.md with one decision label.
layer: logical
tools:
version: 2
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
- Aspect outputs under `branches/shared/reviews/round-<n>/aspect-notes/reviewer-<i>-<aspect>.md`, each using `templates/aspect-note.md`.
- A final report at `reviewer-<i>.md` using `templates/reviewer-instance.md`, with exactly one decision label.

## Procedure

1. **Assign the reviewer index** `reviewer-<i>.md`.
2. **Choose aspects.** Include at least presentation, novelty / related work, method / theory, experiments / baselines, reproducibility / code, limitations / scope when the submission contains those surfaces. Drop only irrelevant ones.
3. **Choose stances.** Read `minions/review/personas/*.md`. Assign different stances to aspect subagents within this reviewer instance where possible.
4. **Spawn aspect subagents.** Each gets: current submission materials only, its aspect instructions, its stance excerpt, read-only / EACN-invisible / local-only boundary, output path, `templates/aspect-note.md` as the required format, and explicit permission to call `codex.ask_codex` (and for code-trace work, `codex.run_codex_worker`) for volume reading. Long manuscripts and code-heavy submissions should default to Codex delegation rather than line-by-line reading inside the subagent.
5. **Merge aspect notes.** Read only the aspect notes for this instance and write `reviewer-<i>.md` using `templates/reviewer-instance.md`.
6. **Choose the reviewer decision.** Exactly one label: `Strong Accept | Accept | Weak Accept | Borderline | Weak Reject | Reject | Strong Reject`. Decision follows this reviewer's evidence, not the expected meta-review outcome.

Output is a complete `reviewer-<i>.md` with major weaknesses, questions, limitations, required revisions, evidence list, and `## Decision`.

## Pitfalls

- Giving all aspect subagents the same stance. The dynamic mix is intentional.
- Letting one aspect dominate the reviewer report without evidence.
- Asking aspect subagents to decide workflow scope, poll EACN, or read review history.
- Over-smoothing disagreement between aspect notes. If one aspect strongly changes the decision pressure, preserve that tension.
