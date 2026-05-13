---
slug: code-validity-review
summary: Assess whether project code and evaluation scripts support the scientific claims under review — code as evidence, not elegance.
layer: logical
tools:
version: 2
status: active
supersedes:
references: aspect-review, simulate-reviewer-instance
provenance: human
---

# Skill — Code Validity Review

Code as evidence. The question is not whether the code is elegant; it is whether implementation details could invalidate experiments, metrics, baselines, or claims in the paper.

## When to invoke

- Reviewer assigns a `Code validity` or `Experiment validity` subspect.
- A paper claim depends on scripts or metrics that have not been independently checked.
- Ethics flags a possible implementation / evidence mismatch and asks Reviewer for formal review input.

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
