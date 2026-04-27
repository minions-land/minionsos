# Skill - Aspect Review

Instructions for a local aspect subagent inside one reviewer instance.

## Core Move

Inspect one narrow aspect of the current submission, with one assigned stance,
and produce evidence-backed notes for the parent reviewer instance.

## Aspect Menu

- `presentation`: structure, clarity, notation, figures, tables, and readability.
- `novelty`: originality, related work, overlap, and contribution inflation.
- `theory`: formal claims, assumptions, proof obligations, algorithms, and method
  soundness.
- `experiments`: baselines, controls, metrics, seeds, variance, ablations, and
  protocol validity.
- `reproducibility`: code, scripts, environment, datasets, checkpoints, leakage,
  and command-level reconstruction.
- `limitations`: claim scope, honest limitations, deployment risks, fairness,
  safety, and ethics tied to the task.

## Required Boundary

The aspect subagent is local-only and EACN-invisible. It must not poll EACN,
register agents, send messages, open project tasks, or read any review history.
It may read only the current submission package and the files explicitly named
in its prompt.

## Procedure

1. Read the assigned current submission materials.
2. Apply the assigned stance/persona, but keep every criticism evidence-backed.
3. Identify aspect-specific weaknesses, questions, required revisions, and
   evidence pointers.
4. State decision pressure, not a final reviewer decision.
5. Write the result using `templates/aspect-note.md`.

## Pitfalls

- Making broad final judgments outside the assigned aspect.
- Criticizing without a concrete citation, section, table, code pointer, or
  artifact pointer.
- Reading `artifacts/reviews/**`, author rebuttals, changelogs, or previous
  summaries during Pass A.

## Output Habit

Use short bullets with evidence attached. Prefer specific, actionable revisions
over general complaints.
