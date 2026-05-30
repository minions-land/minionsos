---
slug: aspect-review
summary: Open when spawned by simulate-reviewer-instance, or when the orchestrator is asked for one narrow-aspect inspection; produce evidence-backed notes with one assigned stance. Delegate manuscript / code scanning to Codex when the aspect requires reading volume.
layer: logical
tools: codex
version: 4
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

The aspect subagent is local-only and EACN-invisible. It may not poll EACN, register agents, send messages, open project tasks, or read any review history (`branches/shared/reviews/**`, author rebuttals, changelogs, previous summaries during Pass A). It may read only the current submission package and files explicitly named in its prompt. Aspect menu:

| Aspect | Scope | Codex fit |
|---|---|---|
| `presentation` | structure, clarity, notation, figures, tables, readability | strong — Codex skims a long PDF/TeX quickly and surfaces unclear passages |
| `novelty` | originality, related work, overlap, contribution inflation | strong — Codex cross-checks the related-work section against the citation list |
| `theory` | formal claims, assumptions, proof obligations, algorithms, method soundness | moderate — Codex traces a derivation but reserve hard math for direct reading |
| `experiments` | baselines, controls, metrics, seeds, variance, ablations, protocol validity | strong — Codex tabulates baselines / metrics / seeds across the paper |
| `reproducibility` | code, scripts, environment, datasets, checkpoints, leakage, command-level reconstruction | strongest — Codex traces script → config → loader → metric end-to-end |
| `limitations` | claim scope, honest limitations, deployment risks, fairness, safety, ethics tied to the task | moderate — Codex reads the limitations section but stance/judgment stays here |

## Codex delegation

Codex GPT-5.5 (via the `codex` MCP tool, codex-subagent) is faster and cheaper than scanning the manuscript turn-by-turn yourself. Prefer it when:

- The aspect requires reading more than ~3 pages of manuscript, or comparing claims across distant sections.
- The aspect requires tracing a code path across files (always pair with `code-validity-review`).
- The aspect requires checking a bibliography against the body text.

Two modes (controlled by the `sandbox` arg on the single `codex` tool):

- `sandbox="read-only"` — read-only analysis. Pass it the aspect, the assigned stance, the submission paths, and the question. Use this for the typical aspect-review pass.
- `sandbox="danger-full-access"` (default) — full-access delegated sub-agent. Use when Codex needs to actually run scripts or chase through many files.

What stays here: the *decision pressure* (your stance-shaped judgment) and the final `aspect-note.md`. Codex returns evidence; you assemble it under the assigned stance.

## Procedure

1. Read the assigned current submission materials (or delegate the volume read to Codex).
2. If the aspect is `presentation` / `novelty` / `experiments` / `reproducibility` and the submission is non-trivial in size, call the `codex` MCP tool (`sandbox="read-only"`) with the aspect prompt + stance + submission pointers and treat its return as evidence input.
3. Apply the assigned stance / persona to the evidence, but keep every criticism evidence-backed.
4. Identify aspect-specific weaknesses, questions, required revisions, evidence pointers.
5. State decision pressure, not a final reviewer decision.
6. Write the result using `templates/aspect-note.md`. Short bullets with evidence attached; prefer specific, actionable revisions over general complaints.

## Pitfalls

- Making broad final judgments outside the assigned aspect.
- Criticizing without a concrete citation, section, table, code pointer, or artifact pointer.
- Reading `branches/shared/reviews/**`, author rebuttals, changelogs, or previous summaries during Pass A.
- Skipping Codex when the manuscript is long and then rationing your own reading. The point of `codex` is to keep the aspect subagent cheap; use it.
- Letting Codex *decide* the stance-shaped verdict. Codex returns evidence; the stance judgment stays in this skill.

