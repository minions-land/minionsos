---
slug: check-self-consistency
summary: Re-derive the submitted answer by an independent path and report whether the two paths converge.
layer: logical
tools:
version: 1
status: active
supersedes:
references: query-reasoning-chain
provenance: human
---

# Skill — Check Self-Consistency

A correct answer is reachable from multiple starting points. A wrong answer
usually only survives one specific path through the problem. Self-consistency
re-derives along an independent path and reports the gap.

## When to invoke

Called by an adjudication-instance for any submission where the answer can be
arrived at via more than one route — most numeric, factual, and code-output
questions. Skip only when the problem genuinely admits a single derivation
path (canonical lookup with no alternative computation).

## Procedure

1. **Identify an independent path.** Examples:
   - Different formula (∫ vs. discrete sum, closed-form vs. simulation).
   - Different unit system (SI vs. imperial, with explicit conversion).
   - Different source (primary paper vs. canonical textbook restatement).
   - Different code path (independent script in `branches/coder/exp/` vs. the
     submitter's script). Spawn via `codex(sandbox=danger-full-access)` if
     execution is needed.
2. **Run the independent path end-to-end.** Do not peek at the submitted
   value while computing — compute, then compare.
3. **Compare values.** Tolerances:
   - Exact-match domains (multiple choice, named entity): byte-equal after
     canonicalisation (case, whitespace).
   - Numeric: relative error ≤ 1e-6 unless the problem states a coarser
     tolerance.
   - Free-form: paraphrase-equivalent under a strict reading.
4. **Output to `aspect-notes/reviewer-<i>-self-consistency.md`**. Record the
   two paths, the two values, and the verdict: `MATCH | NEAR-MATCH (within
   tolerance) | DIVERGE`.

## When to flip the decision

DIVERGE pushes verdict to Reject (one of the two paths is wrong; absent a
specific reason to prefer the submitter's path, the divergence itself is the
weakness). NEAR-MATCH is a Revise — the team should reconcile and explain.

## Pitfalls

- Picking an "independent" path that secretly shares the same source of error
  (using the same library function under a different wrapper).
- Stopping at the first divergence without locating *which* step diverged —
  the audit should be informative even when the verdict is clear.
- Allowing tolerance to absorb a real disagreement; if the problem demands
  exact match, do not soften it.
