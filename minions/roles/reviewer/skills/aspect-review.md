---
slug: aspect-review
summary: Open when spawned by simulate-reviewer-instance, or when Reviewer main is asked for one narrow-aspect inspection; produce evidence-backed notes with one assigned stance.
layer: logical
tools:
version: 2
status: active
supersedes:
references: simulate-reviewer-instance
provenance: human
---

# Skill — Aspect Review

One narrow aspect, one assigned stance, evidence-backed notes for the parent reviewer instance. Local-only and EACN-invisible by design.

## When to invoke

Called by `simulate-reviewer-instance` when spawning an aspect subagent. Each reviewer instance spawns several of these in parallel. May also be invoked directly when Reviewer main is asked for a single narrow-aspect inspection (e.g. "audit reproducibility for round 3, no full review needed") outside the orchestrated round flow.

## Structure

The aspect subagent is local-only and EACN-invisible. It may not poll EACN, register agents, send messages, open project tasks, or read any review history (`artifacts/reviews/**`, author rebuttals, changelogs, previous summaries during Pass A). It may read only the current submission package and files explicitly named in its prompt. Aspect menu:

| Aspect | Scope |
|---|---|
| `presentation` | structure, clarity, notation, figures, tables, readability |
| `novelty` | originality, related work, overlap, contribution inflation |
| `theory` | formal claims, assumptions, proof obligations, algorithms, method soundness |
| `experiments` | baselines, controls, metrics, seeds, variance, ablations, protocol validity |
| `reproducibility` | code, scripts, environment, datasets, checkpoints, leakage, command-level reconstruction |
| `limitations` | claim scope, honest limitations, deployment risks, fairness, safety, ethics tied to the task |

## Procedure

1. Read the assigned current submission materials.
2. Apply the assigned stance / persona, but keep every criticism evidence-backed.
3. Identify aspect-specific weaknesses, questions, required revisions, evidence pointers.
4. State decision pressure, not a final reviewer decision.
5. Write the result using `templates/aspect-note.md`. Short bullets with evidence attached; prefer specific, actionable revisions over general complaints.

## Pitfalls

- Making broad final judgments outside the assigned aspect.
- Criticizing without a concrete citation, section, table, code pointer, or artifact pointer.
- Reading `artifacts/reviews/**`, author rebuttals, changelogs, or previous summaries during Pass A.
