# Skill — Triage Request

Assess an incoming experiment request for feasibility, priority, and execution shape before touching a GPU.

## Core move

Decide how the request should enter the execution system: accept, queue, defer, redirect, or bounce back for clarification. You are the operational gatekeeper — you are not judging scientific merit.

## Procedure

1. **Read the request end-to-end** from the EACN event. Note requester, stated goal, scripts, data paths, `gpus_needed`, deadline if any.
2. **Check clarity.** If the script path, dataset, or success criterion is missing or ambiguous, reply on EACN asking exactly what is missing. Do not guess.
3. **Check feasibility against targets.** Cross-reference `experiment_targets.yaml` and a recent `query_gpus` poll. Is the required VRAM ever available? Is the toolchain installed on at least one target?
4. **Check dependencies.** Does this depend on a still-running run? If yes, note the upstream `run_id` as a gating condition.
5. **Decide shape.** One `exp_run` call, a sweep requiring several parallel launches, or a long pipeline that needs a subagent team? Record the decision.
6. **Return a triage note on EACN** (see Output habit). If accepting, hand off to `allocate-resources`; if not, explain why in one short paragraph.

## When to invoke

- On every fresh experiment request event, before any `exp_run` call.
- When a previously deferred request is revisited after a dependency clears.
- When a request arrives that looks like a duplicate of a running job — triage catches the duplication before resources are wasted.

## Pitfalls

- Triaging into execution in one step. Keep triage a pure decision; resource planning is a separate step.
- Judging the science. If the hypothesis seems weak, bounce it to Expert via EACN, don't silently shrink the experiment.
- Skipping feasibility because "probably fine." A 30-second `query_gpus` saves hours of stuck queueing.

## Output habit

Post a compact EACN reply: request summary, verdict (`accept` / `queue` / `defer` / `redirect` / `need_info`), rough resource envelope, execution shape, and any upstream dependency. Mark derived feasibility claims `[derived: query_gpus @ <ts>]` per root §9 so the audit trail is explicit.
