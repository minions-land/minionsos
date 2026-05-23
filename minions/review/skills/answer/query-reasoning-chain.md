---
slug: query-reasoning-chain
summary: For an adjudication-instance reviewing a submitted answer, audit each load-bearing inference step in the submission's reasoning_summary and mark VERIFIED / UNVERIFIED / BROKEN.
layer: logical
tools:
version: 1
status: active
supersedes:
references: simulate-reviewer-instance
provenance: human
---

# Skill — Query Reasoning Chain

The submitted answer arrives with a `reasoning_summary` field. That summary is
a chain of inferences — definitions, equations, citations, code outputs,
inferences-from-inferences. Each step is either decisive (the answer changes
if it changes) or scaffolding. Adjudicators must audit the decisive steps.

## When to invoke

Called by an adjudication-instance pass when the submission carries a
non-trivial reasoning chain. Skip only when the submission is a pure lookup
with no chain to audit (multiple choice with no justification).

## Procedure

1. **Read `branches/shared/submissions/answer.json`** to get `payload.answer`
   and `payload.reasoning_summary`.
2. **Read `input/expected.json` if it exists** *only after* you have formed
   your independent verdict — to avoid anchoring. If no reference exists, work
   blind.
3. **Decompose the chain** into atomic inference steps. Each step has the
   shape *premise(s) → inference rule → conclusion*. Number them.
4. **For each step, attempt independent re-derivation.** Use `codex` for
   volume work (long derivations, large lookup tables). Use Bash for unit
   conversions, integer arithmetic, regex extraction over project files.
5. **Assign one verdict per step:**
   - `VERIFIED` — re-derived independently and matches.
   - `UNVERIFIED` — couldn't re-derive in the time budget. Note what would
     have been needed.
   - `BROKEN` — specific counter-derivation in hand. Cite it.
6. **Output to `aspect-notes/reviewer-<i>-reasoning-chain.md`** using
   `templates/aspect-note.md`. Include the per-step verdict table and the
   weakest link (the BROKEN or lowest-confidence UNVERIFIED).

## When to flip the decision

A single BROKEN step on a load-bearing inference is sufficient to push the
adjudicator's verdict to Reject regardless of other aspects. Multiple
UNVERIFIED scaffolding steps push toward Revise, not Reject.

## Pitfalls

- Treating the submission's wording as evidence for itself. The chain is a
  hypothesis; this skill exists to *test* it, not paraphrase it.
- Citing the same source the submitter cited without independently checking
  the source actually supports the inference.
- Letting a single elegant equation drown out a missing citation or a unit
  mismatch upstream.
