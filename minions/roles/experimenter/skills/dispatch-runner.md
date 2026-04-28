# Skill — Dispatch Runner

Submit launchable work to the Python queue, then exit — no manual polling loop.

## Core move

Given queue-ready units, call `exp_queue_submit` once. The Python scheduler issues non-blocking `exp_run` calls, records run handles, and keeps pending work flowing on later reconciles.

## Procedure

1. **Submit all units.** Call `exp_queue_submit(units=[...])`; include `reserve_mb` / `min_free_mb` when known.
2. **Record the batch id.** Store `{batch_id, unit_ids}` in scratchpad or the requester-facing note so later wake-ups can call `exp_queue_status`.
3. **Do not block.** Never follow queue submission with long `exp_wait`; Python reconciles and tracks detached runs.
4. **Delegate heavy per-unit execution prep to a subagent** when a unit requires non-trivial scripting, data massage, or config expansion. Subagents have `exp_*` only; keep them within their assigned slice.
5. **Broadcast a short EACN handoff** listing the batch id, currently launched units, and pending count so Noter / requester know jobs are alive.

## When to invoke

- After `allocate-resources` produces queue-ready units.
- On wake-up when a new request should be merged into the global queue.

## Pitfalls

- Reaching for `exp_wait(timeout=3600)` out of habit. This is explicitly banned as a default primitive (§Fire-and-poll).
- Forgetting to persist `batch_id` before the ephemeral session exits — detached jobs survive, your memory does not (root §6).
- Starting a subagent that inherits `eacn3_*`. Subagents must not; the whitelist enforces this.

## Output habit

One EACN message per dispatch batch: `{batch_id, submitted, launched_now, pending}` plus a pointer to status/report artifacts.
