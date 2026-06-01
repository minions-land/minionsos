---
slug: aspect-review
summary: Open when spawned by simulate-reviewer-instance, or when the orchestrator is asked for one narrow-aspect inspection; produce evidence-backed notes with one assigned stance. Delegate manuscript / code scanning to a nested Task subagent when the aspect requires reading volume.
layer: logical
tools: Task
version: 5
status: active
supersedes:
references: simulate-reviewer-instance, code-validity-review
provenance: human
---

# Skill — Aspect Review

One narrow aspect, one assigned stance, evidence-backed notes for the parent reviewer instance. Local-only and EACN-invisible by design.

## When to invoke

Called by `simulate-reviewer-instance` when spawning an aspect subagent. Each reviewer instance spawns several of these in parallel. May also be invoked directly when the orchestrator is asked for a single narrow-aspect inspection (e.g. "audit reproducibility for round 3, no full review needed") outside the orchestrated round flow.

If an `experiments` or `reproducibility` finding requires walking actual code paths to confirm — script → config → data loader → metric → output — escalate to `code-validity-review` instead of staying inside this skill. Code-validity-review is the deep-trace zoom of those two aspects, not a separate aspect.

## Structure

The aspect subagent is local-only and EACN-invisible. It may not poll EACN, register agents, send messages, open project tasks, or read any review history (`branches/main/reviews/**`, author rebuttals, changelogs, previous summaries during Pass A). It may read only the current submission package and files explicitly named in its prompt. Aspect menu:

| Aspect | Scope | Nested-`Task` fit |
|---|---|---|
| `presentation` | structure, clarity, notation, figures, tables, readability | strong — a nested subagent skims a long PDF/TeX quickly and surfaces unclear passages |
| `novelty` | originality, related work, overlap, contribution inflation | strong — a nested subagent cross-checks the related-work section against the citation list |
| `theory` | formal claims, assumptions, proof obligations, algorithms, method soundness | moderate — a nested subagent traces a derivation but reserve hard math for direct reading |
| `experiments` | baselines, controls, metrics, seeds, variance, ablations, protocol validity | strong — a nested subagent tabulates baselines / metrics / seeds across the paper |
| `reproducibility` | code, scripts, environment, datasets, checkpoints, leakage, command-level reconstruction | strongest — a nested subagent traces script → config → loader → metric end-to-end |
| `limitations` | claim scope, honest limitations, deployment risks, fairness, safety, ethics tied to the task | moderate — a nested subagent reads the limitations section but stance/judgment stays here |

## Subagent delegation

A nested read-only `Task` subagent is faster and cheaper than scanning the manuscript turn-by-turn yourself. Prefer it when:

- The aspect requires reading more than ~3 pages of manuscript, or comparing claims across distant sections.
- The aspect requires tracing a code path across files (always pair with `code-validity-review`).
- The aspect requires checking a bibliography against the body text.

Two delegation shapes:

- read-only analysis subagent — pass it the aspect, the assigned stance, the submission paths, and the question. Use this for the typical aspect-review pass.
- `Bash`-capable code-trace subagent — use when the trace needs to actually run scripts or chase through many files.

What stays here: the *decision pressure* (your stance-shaped judgment) and the final `aspect-note.md`. The nested subagent returns evidence; you assemble it under the assigned stance.

## Procedure

1. Read the assigned current submission materials (or delegate the volume read to a nested `Task` subagent).
2. If the aspect is `presentation` / `novelty` / `experiments` / `reproducibility` and the submission is non-trivial in size, fan out a read-only `Task` subagent with the aspect prompt + stance + submission pointers and treat its return as evidence input.
3. Apply the assigned stance / persona to the evidence, but keep every criticism evidence-backed.
4. Identify aspect-specific weaknesses, questions, required revisions, evidence pointers.
5. State decision pressure, not a final reviewer decision.
6. Map each finding to the applicable rigor dimension(s) (D1–D6) and fill the "Rigor Dimensions (D1–D6)" section of `templates/aspect-note.md` for the dimensions this aspect bears on. Surface any D3 scope / over-claim finding as `OVER-CLAIM`.
7. Write the result using `templates/aspect-note.md`. Short bullets with evidence attached; prefer specific, actionable revisions over general complaints.

## Rigor dimension mapping

Each aspect typically carries a subset of the six dimensions. Score only what the aspect actually exercises:

| Aspect | Primary dimensions |
|---|---|
| `presentation` | D4 Argument Coherence (narrative arc, notation, figure/table clarity) |
| `novelty` | D3 Scope Calibration (contribution inflation), D1 Evidence Relevance (positioning vs cited work) |
| `theory` | D2 Falsifiability Quality (are claims testable / refutable?), D3 Scope Calibration (theorem vs proposition), D1 Evidence Relevance (does the proof support the stated claim?) |
| `experiments` | D6 Methodological Rigor (baselines, ablations, stats), D1 Evidence Relevance (do results support the claim?), D3 Scope Calibration (metric–claim alignment) |
| `reproducibility` | D6 Methodological Rigor (seeds, configs, command-level reconstruction), D5 Exploration Integrity (does the documented process show real failures/dead-ends?) |
| `limitations` | D3 Scope Calibration (over/under-claim), D5 Exploration Integrity (honest dead-ends vs post-hoc justification) |

## Pitfalls

- Making broad final judgments outside the assigned aspect.
- Criticizing without a concrete citation, section, table, code pointer, or artifact pointer.
- Reading `branches/main/reviews/**`, author rebuttals, changelogs, or previous summaries during Pass A.
- Skipping the nested subagent when the manuscript is long and then rationing your own reading. The point of nested `Task` delegation is to keep the aspect subagent cheap; use it.
- Letting the nested subagent *decide* the stance-shaped verdict. It returns evidence; the stance judgment stays in this skill.
- Scoring a rigor dimension the aspect does not actually exercise. Leave inapplicable dimensions out rather than guessing.

