---
slug: triage-request
summary: Assess an incoming experiment request for feasibility, priority, and execution shape before touching a GPU — the operational gatekeeper, not a scientific judge.
layer: logical
tools: mos_query_gpus, mos_exp_queue_status
version: 2
status: active
supersedes:
references: allocate-resources, dispatch-runner
provenance: human
---

# Skill — Triage Request

Decide how an incoming request enters the execution system: accept, queue, defer, redirect, or bounce back for clarification. You are the operational gatekeeper — not the scientific judge.

## When to invoke

- On every fresh experiment request event, before any `mos_exp_run` call.
- When a previously deferred request is revisited after a dependency clears.
- When a request arrives that looks like a duplicate of a running job — triage catches the duplication before resources are wasted.

## Structure

One decision per incoming request, recorded as a compact EACN reply: `{verdict, resource_envelope, execution_shape, upstream_dependency?}`. Verdicts: `accept` (hand off to `allocate-resources`), `queue` (upstream dependency pending), `defer` (feasibility blocked), `redirect` (to Coder / Expert via EACN), `need_info` (reply with the exact missing fields).

## Procedure

1. **Read the request end-to-end** from the EACN event: requester, stated goal, scripts, data paths, `gpus_needed`, deadline if any.
2. **Check clarity.** If script path, dataset, or success criterion is missing or ambiguous, reply on EACN asking exactly what is missing. Do not guess.
3. **Check feasibility against targets.** Cross-reference the project's `experiment_targets.yaml` (installed from `minions/config/experiment_targets.yaml.example` at project create; the runtime copy lives at the project root) and a recent `mos_query_gpus` poll. Is the required VRAM ever available? Is the toolchain installed on at least one target?
4. **Check dependencies.** Does this depend on a still-running run? If yes, note the upstream `run_id` as a gating condition.
5. **Decide shape.** One `mos_exp_run` call, a sweep requiring several parallel launches, or a long pipeline that needs a subagent team.
6. **Return a triage note on EACN** (see Structure). If accepting, hand off to `allocate-resources`; otherwise explain why in one short paragraph. Mark derived feasibility claims `[derived: mos_query_gpus @ <ts>]`.

## Pitfalls

- Triaging into execution in one step. Keep triage a pure decision; resource planning is separate.
- Judging the science. Weak-hypothesis requests bounce to Expert via EACN — do not silently shrink the experiment.
- Skipping feasibility because "probably fine." A 30-second `mos_query_gpus` saves hours of stuck queueing.
