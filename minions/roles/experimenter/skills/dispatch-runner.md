# Skill — Dispatch Runner

Fire everything launchable in parallel via `exp_run`, then exit — no blocking, no serialization.

## Core move

Given an allocation plan, issue one non-blocking `exp_run` per `launch_now` unit, record returned `run_id`s, and hand off to `track-run`. Do not `exp_wait` during dispatch.

## Procedure

1. **Iterate the `launch_now` list.** For each unit: call `exp_run(target_id, command, cwd=..., env=..., gpus=[gpu_id], artifact_dir="artifacts/exp-{id}/")`. The `gpu_id` comes from the spread-first assignment in `allocate-resources` — pass it through as `CUDA_VISIBLE_DEVICES` / `gpus=[...]` so the run actually lands on the intended card.
2. **Fire them back-to-back.** Do not wait between `exp_run` calls. All N dispatches happen in a tight loop; every one returns immediately with `{run_id, pid, log_path}`. If you find yourself launching one and checking its status before launching the next, stop — that is serial execution in disguise.
3. **Record the handle.** Store `{run_id, pid, log_path, target_id, gpu_id, exp_id, unit}` immediately — losing a `run_id` means losing the ability to track or kill the job.
4. **Do not block.** Never follow an `exp_run` with a long-`timeout` `exp_wait` — that serializes the fleet. `exp_run` is fully detached (`nohup setsid`) per `SYSTEM.md`.
5. **Delegate heavy per-unit execution prep to a subagent** when a unit requires non-trivial scripting, data massage, or config expansion. Subagents have `exp_*` only; keep them within their assigned slice.
6. **Honour gates for queued units.** Dispatch resumes when a gate clears; do not pre-launch gated units to "save a round trip."
7. **Broadcast a short EACN handoff** listing the `exp_id → (run_id, target_id, gpu_id)` mapping so Noter / requester know jobs are alive and on which card.

## When to invoke

- After `allocate-resources` produces a plan.
- On wake-up when `exp_list` reveals a newly free GPU and the queue has a gated unit whose gate has cleared.

## Pitfalls

- Reaching for `exp_wait(timeout=3600)` out of habit. This is explicitly banned as a default primitive (§Fire-and-poll).
- Forgetting to persist `run_id` before the ephemeral session exits — detached jobs survive, your memory does not (root §6).
- Starting a subagent that inherits `eacn3_*`. Subagents must not; the whitelist enforces this.

## Output habit

One EACN message per dispatch batch: `{exp_id, run_id, target_id, log_path}` per unit, plus a pointer to the plan. Artifact destinations are reserved under `artifacts/exp-{id}/`.
