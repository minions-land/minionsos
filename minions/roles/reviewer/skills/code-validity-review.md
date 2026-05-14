---
slug: code-validity-review
summary: Deep-trace zoom of the experiments / reproducibility aspects — open only when an aspect-review needs to walk actual code paths to decide whether implementation details invalidate a paper claim. Not a parallel review type.
layer: logical
tools:
version: 3
status: active
supersedes:
references: aspect-review, simulate-reviewer-instance
provenance: human
---

# Skill — Code Validity Review

The deep-trace zoom of `aspect-review`'s `experiments` and `reproducibility` aspects. Most of the time, those aspects produce findings from the submission package alone — claims, tables, configs, logs. This skill opens only when the aspect's evidence trail requires walking actual code paths (script → config → data loader → metric → output) to decide whether an implementation detail invalidates a claim.

The question is not whether the code is elegant. It is whether implementation details could invalidate experiments, metrics, baselines, or claims.

## Relationship to aspect-review

This skill is not a third reviewer aspect. It is the *callable mode* an `experiments` or `reproducibility` aspect subagent escalates to when surface-level reading cannot resolve a validity question.

Decision rule:

- **Use `aspect-review` directly** with the `experiments` or `reproducibility` aspect when the submission package, configs, and reported metrics are enough to surface findings. This is the default path.
- **Open `code-validity-review`** when an aspect finding requires walking code paths to confirm or reject. Examples: a metric whose definition is only resolvable by reading the script; a baseline whose true configuration is only in code; a leakage suspicion that needs a data-loader trace.

Output of `code-validity-review` lands inside the same aspect note (an `experiments` or `reproducibility` aspect-note) — it is a deeper evidence layer, not a separate artifact.

## When to invoke

- An `experiments` or `reproducibility` aspect-review surfaced a question that cannot be resolved from the submission package alone, and the parent reviewer instance asks for a code-trace.
- Ethics flags a possible implementation / evidence mismatch and asks Reviewer for formal code-trace input.
- Reviewer main is asked directly for a code-trace zoom outside the orchestrated round flow.

If none of those triggers apply, use `aspect-review` with `experiments` or `reproducibility` instead.

## Structure

Every finding is bound to a specific claim, cites a concrete code path / line / config / log / artifact / missing-provenance item, and states the minimum revision or experiment needed to resolve the risk. Style and maintainability are out of scope unless they create a realistic validity risk. Reviewer is read-only on `branches/**` and writes only under `artifacts/reviews/round-<n>/`.

Validity-risk checklist: data leakage, train / test mixups, hardcoded results, benchmark shortcuts, stale baselines, seed contamination, cherry-picking, metric mismatch, unreported filtering.

## Procedure

1. **Bind code to claims.** Identify the paper claim, experiment report, table, or figure the code supports.
2. **Trace the execution path.** Relevant script, config, data loading, metric computation, baseline selection, output serialization.
3. **Check validity risks** per the checklist above.
4. **Check reproducibility hooks.** Seeds, configs, commit SHAs, dataset versions, command lines recorded well enough for the claim.
5. **Separate bugs from style.** Ignore style and maintainability unless they create a realistic validity risk.
6. **Write evidence-backed findings** in the current review round artifact with severity, claim affected, evidence pointer, and the minimum revision or experiment needed to resolve.

## Pitfalls

- Performing general code review instead of scientific validity review.
- Inferring a bug from unfamiliar style without tracing execution.
- Reading historical review context during a fresh Pass A review.
- Suggesting fixes in any role's branch (e.g. `branches/coder/`, `branches/writer/`); Reviewer is read-only on `branches/` and writes only under `artifacts/reviews/`.
