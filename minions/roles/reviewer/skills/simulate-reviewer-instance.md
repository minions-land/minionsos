# Skill - Simulate Reviewer Instance

Build one independent simulated reviewer report from several local aspect
subagents.

## Core Move

One reviewer instance is not one mood and not one subagent. It is a composite
review formed by several aspect subagents that each inspect a different part of
the submission with a different stance.

## Procedure

1. **Assign the reviewer index.** Use `reviewer-<i>.md`, where `<i>` is 1-5.
2. **Choose aspects.** Include at least presentation, novelty/related work,
   method/theory, experiments/baselines, reproducibility/code, and
   limitations/scope when the submission contains those surfaces. Drop only
   aspects that are genuinely irrelevant.
3. **Choose stances.** Read available stance/persona files from
   `minions/roles/reviewer/personas/*.md`. Assign different stances to aspect
   subagents within the reviewer instance where possible.
4. **Spawn aspect subagents.** Each local subagent gets:
   - current submission materials only;
   - its aspect instructions;
   - its stance/persona excerpt;
   - the read-only / EACN-invisible / local-only boundary;
   - output path
     `artifacts/reviews/round-<n>/aspect-notes/reviewer-<i>-<aspect>.md`;
   - `templates/aspect-note.md` as the required format.
5. **Merge aspect notes.** Reviewer main reads only the aspect notes for this
   reviewer instance and writes `reviewer-<i>.md` using
   `templates/reviewer-instance.md`.
6. **Choose the reviewer decision.** Use exactly one label:
   `Strong Accept | Accept | Weak Accept | Borderline | Weak Reject | Reject | Strong Reject`.
   The decision should follow the evidence in this reviewer instance, not the
   expected final meta-review outcome.

## Pitfalls

- Giving all aspect subagents the same stance. The dynamic mix is intentional.
- Letting one aspect dominate the reviewer report without evidence.
- Asking aspect subagents to decide workflow scope, poll EACN, or read review
  history.
- Over-smoothing disagreement between aspect notes. If one aspect strongly
  changes the decision pressure, preserve that tension in the reviewer report.

## Output Habit

Write a complete `reviewer-<i>.md` with major weaknesses, questions, limitations,
required revisions, evidence list, and `## Decision`.
