---
slug: run-experiments
summary: Submit, monitor, and collect GPU experiment results via the Python scheduler. Report-synthesis goes through Workflow (single-agent or pipeline shape).
layer: logical
tools: mos_exp_queue_submit, mos_exp_run, mos_exp_status, mos_exp_list, mos_exp_get, mos_exp_tail, mos_query_gpus, mos_exp_gpu_pool_get, Workflow
version: 2
status: active
supersedes:
references: bounded-repair-loop, feature-implementation, role-act-via-workflow
provenance: human
---

# Skill — Run Experiments

Submit, monitor, and collect GPU experiment results via the Python
scheduler. Report-synthesis goes through Workflow.

## When to invoke

- You have experiment scripts ready and need GPU execution.
- An EACN task requires training, evaluation, or parameter sweeps.
- You receive an experiment completion event and need to process results.

## Procedure

1. **Prepare scripts** under `branches/<expert>/src/experiments/`. Each script must be self-contained and exit non-zero on failure.
2. **Check GPU capacity**: `mos_query_gpus(target_id="auto")` and `mos_exp_gpu_pool_get()` for pool limits.
3. **Submit batch**: `mos_exp_queue_submit(units=[...])`. Use `mos_exp_run` only for single one-off jobs.
4. **Wait for EACN completion events** (one per experiment). Do not busy-poll status — the Python scheduler sends events automatically.
5. **On completion**: `mos_exp_get` to pull small result files; `mos_exp_tail` for log inspection.
6. **Delegate to Workflow**: dispatch a Workflow (`single-agent` for one
   bundle, `pipeline` shape for multi-experiment cross-analysis). Pass
   metrics, failure log, target schema as inputs; receive a size-bounded
   `{report_path, summary, next_actions[]}` per `role-act-via-workflow`.
7. **Store** result bundle in `branches/<expert>/exp/exp-<id>/`, then publish to `branches/shared/exp/exp-<id>/` via `mos_publish_to_shared`.
8. **Report findings** via EACN to the requesting role.

## Fire-and-poll rules

- `mos_exp_run` returns immediately with `{run_id, pid, log_path}` — never block on it.
- Prefer `mos_exp_queue_submit` for any multi-experiment workload.
- Python scheduler handles GPU packing and OOM retry automatically.
- Hard anomalies (NaN, process death) trigger automatic kill + EACN notification.
- Do NOT busy-poll status — wait for EACN events via `mos_await_events`.

## Pitfalls

- Do not run experiments in your main session — always submit to the queue.
- Do not fix experiment code bugs inline during a run — kill, fix, resubmit.
- Large files (>500 MB) stay remote — reference by path, use `mos_exp_tail` to inspect.
- Maximum parallel experiments limited by GPU pool — check with `mos_exp_gpu_pool_get`.
- On cold start, call `mos_exp_list` on every target to recover still-running experiments.
- Long Workflows (multi-experiment synthesis) MUST run with
  `run_in_background=true` per common §4 — bid-deadline traffic must
  never see a stale Expert.

