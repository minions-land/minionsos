# EvoAny — Evolutionary Code Optimization

## Core scope

Git-based evolutionary algorithm engine. Treats git branches as candidate
individuals and benchmark results as fitness. Automates code optimization
through LLM-driven mutation, crossover, reflection, and NSGA-II selection.

Source: https://github.com/DataLab-atom/EvoAny

## Key concepts

- **Target**: a code region to optimize (function, module, pipeline)
- **Individual**: a git branch containing a variant of the target
- **Fitness**: quantitative benchmark output (latency, accuracy, score, etc.)
- **Generation**: one cycle of mutation → policy review → evaluation → selection
- **Lineage**: branch ancestry tracking for crossover and reflection

## State machine phases

```
begin_generation → code_ready → policy_pass/fail → fitness_ready → select → reflect_done
```

Each phase is advanced by `evo_step`. The Expert drives the loop by calling
`evo_step` with the appropriate phase transition after completing each stage.

## Multi-agent architecture (internal to EvoAny)

1. **Orchestrator** — drives main loop, dispatches workers, triggers selection
2. **Map** — analyzes code, identifies optimization targets
3. **Worker** — generates variants (mutation/crossover) and evaluates them
4. **Policy** — reviews diffs, approves/rejects before benchmark
5. **Reflect** — writes memory, extracts lessons, runs synergy checks

## Typical workflow

1. `evo_init(repo, benchmark_cmd, objectives)` — point at a repo with a runnable benchmark
2. `evo_register_targets(targets)` — identify what to optimize
3. `evo_report_seed(baseline)` — establish baseline fitness
4. Loop: `evo_step(phase)` through generations until convergence or budget exhaustion
5. `evo_get_status()` / `evo_get_lineage()` to inspect progress

## Integration with MinionsOS

When mounted as a skill node, the Expert uses EvoAny's MCP tools to drive
evolution loops on the project's codebase. The Expert communicates results
back to the team via EACN3 and publishes final optimized code through
`mos_publish_to_shared` → `handoffs/`.

## Pitfalls

- Fitness function must be deterministic and fast (< 5 min per eval)
- Policy agent can reject too aggressively — tune approval threshold
- Premature convergence if mutation pressure is too low
- Branch explosion if selection pressure is too low
