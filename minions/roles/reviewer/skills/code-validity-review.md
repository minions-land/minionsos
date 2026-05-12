# Skill — Code Validity Review

Assess whether project code and evaluation scripts support the scientific claims
under review.

## Core move

Review code as evidence. The question is not whether the code is elegant; it is
whether implementation details could invalidate experiments, metrics, baselines,
or claims in the paper.

## Procedure

1. **Bind code to claims.** Identify the paper claim, experiment report, table,
   or figure that depends on the code being reviewed.
2. **Trace the execution path.** Read the relevant script, config, data loading,
   metric computation, baseline selection, and output serialization.
3. **Check validity risks.** Look for data leakage, train/test mixups, hardcoded
   results, benchmark shortcuts, stale baselines, seed contamination, cherry
   picking, metric mismatch, and unreported filtering.
4. **Check reproducibility hooks.** Verify that seeds, configs, commit SHAs,
   dataset versions, and command lines are recorded well enough for the claim.
5. **Separate bugs from style.** Ignore style and maintainability unless they
   create a realistic validity risk.
6. **Write evidence-backed findings.** Every criticism must cite a concrete code
   path, line, config, log, artifact, or missing provenance item.

## When to invoke

- Reviewer assigns a `Code validity` or `Experiment validity` subspect.
- A paper claim depends on scripts or metrics that have not been independently
  checked.
- Ethics flags a possible implementation/evidence mismatch and asks Reviewer for
  formal review input.

## Pitfalls

- Performing general code review instead of scientific validity review.
- Inferring a bug from unfamiliar style without tracing execution.
- Reading historical review context during a fresh Pass A review.
- Suggesting fixes in any role's branch (e.g. `branches/coder/`, `branches/writer/`); Reviewer is read-only on `branches/` and writes only under `artifacts/reviews/`.

## Output habit

Write findings in the current review round artifact with severity, claim
affected, evidence pointer, and the minimum revision or experiment needed to
resolve the risk.
