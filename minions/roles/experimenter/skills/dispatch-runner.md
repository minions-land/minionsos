# Skill — Dispatch Runner

Fire everything launchable in parallel via `exp_run`, then exit — no blocking, no serialization.

## Core move

Given an allocation plan, issue one non-blocking `exp_run` per `launch_now` unit, record returned `run_id`s, and hand off to `track-run`. Do not `exp_wait` during dispatch.

## Procedure

1. **Iterate the `launch_now` list.** For each unit: call `exp_run(target_id, command, cwd=..., env=..., gpus=..., artifact_dir="artifacts/exp-{id}/")`.
2. **Record the handle.** Store `{run_id, pid, log_path, target_id, exp_id, unit}` immediately — losing a `run_id` means losing the ability to track or kill the job.
3. **Do not block.** Never follow an `exp_run` with a long-`timeout` `exp_wait` — that serializes the fleet. `exp_run` is fully detached (`nohup setsid`) per `SYSTEM.md`.
4. **Delegate heavy per-unit execution prep to a subagent** when a unit requires non-trivial scripting, data massage, or config expansion. Subagents have `exp_*` only; keep them within their assigned slice.
5. **Honour gates for queued units.** Dispatch resumes when a gate clears; do not pre-launch gated units to "save a round trip."
6. **Broadcast a short EACN handoff** listing the `exp_id → run_id` mapping so Noter / requester know jobs are alive.

## When to invoke

- After `allocate-resources` produces a plan.
- On wake-up when `exp_list` reveals a newly free GPU and the queue has a gated unit whose gate has cleared.

## Pitfalls

- Reaching for `exp_wait(timeout=3600)` out of habit. This is explicitly banned as a default primitive (§Fire-and-poll).
- Forgetting to persist `run_id` before the ephemeral session exits — detached jobs survive, your memory does not (root §6).
- Starting a subagent that inherits `eacn3_*`. Subagents must not; the whitelist enforces this.

## Output habit

One EACN message per dispatch batch: `{exp_id, run_id, target_id, log_path}` per unit, plus a pointer to the plan. Artifact destinations are reserved under `artifacts/exp-{id}/`.
