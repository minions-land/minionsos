# Target Selection Strategy

One-line: Identify and prioritize optimization targets in a codebase for evolutionary search.

## Procedure

1. Analyze the project's codebase structure and benchmark entry point.
2. Identify candidate targets: functions, modules, or pipelines where
   optimization would improve the benchmark metric.
3. For each candidate, assess:
   - **Impact**: how much does this target affect the fitness metric?
   - **Mutability**: how amenable is this code to LLM-driven mutation?
   - **Isolation**: can this target be modified without breaking dependencies?
4. Rank candidates by (impact × mutability × isolation).
5. Register top-N targets via `evo_register_targets`.
6. Use `evo_boost_target` on high-priority targets, `evo_freeze_target` on
   targets that have converged.

## When to invoke

At the start of an evolution campaign, or when the current target set has
stagnated and new targets should be explored.

## Pitfalls

- Avoid targets that are tightly coupled to external APIs (hard to benchmark).
- Don't register too many targets at once — budget gets spread thin.
- Re-evaluate targets after major architectural changes in the codebase.
