# Drive Evolution Loop

One-line: Orchestrate a full EvoAny generation cycle from mutation through selection.

## Procedure

1. Check current state with `evo_get_status()`. Identify which phase the loop is in.
2. If starting a new generation: call `evo_step(phase="begin_generation")`.
3. For each registered target:
   a. Generate variant (mutation or crossover from lineage).
   b. Call `evo_step(phase="code_ready")` when the variant branch is ready.
   c. Wait for policy review. If `policy_fail`, discard and try another variant.
   d. On `policy_pass`, run the benchmark and report fitness.
   e. Call `evo_step(phase="fitness_ready")` with results.
4. After all variants evaluated: `evo_step(phase="select")` to run NSGA-II selection.
5. Call `evo_step(phase="reflect_done")` after extracting lessons from this generation.
6. Report generation summary to EACN3 team via `eacn3_send_message`.

## When to invoke

When the project needs automated code optimization — improving performance,
accuracy, or efficiency of an identified code target through evolutionary search.

## Pitfalls

- Never skip the policy review phase (it prevents degenerate mutations).
- Always check `evo_check_cache` before re-evaluating a known variant.
- Report results to the team after each generation, not just at the end.
