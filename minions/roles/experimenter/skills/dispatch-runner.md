---
slug: dispatch-runner
summary: Submit launchable work to the Python queue via exp_queue_submit, record the batch id, and exit — no manual polling loop.
layer: logical
tools: exp_queue_submit
version: 2
status: active
supersedes:
references: allocate-resources, track-run
provenance: human
---

# Skill — Dispatch Runner

Submit once, persist the batch id, exit. The Python scheduler issues non-blocking `exp_run` calls, records run handles, and keeps pending work flowing on later reconciles.

## When to invoke

- After `allocate-resources` produces queue-ready units.
- On wake-up when a new request should be merged into the global queue.

## Structure

One call to `exp_queue_submit`; store `{batch_id, unit_ids}` in scratchpad or the requester-facing note so later wake-ups can call `exp_queue_status`. Never follow with long `exp_wait` — Python reconciles and tracks detached runs. Heavy per-unit execution prep (non-trivial scripting, data massage, config expansion) is delegated to a subagent whose whitelist is `exp_*` only.

## Procedure

1. **Submit all units.** `exp_queue_submit(units=[...])`; include `reserve_mb` / `min_free_mb` when known.
2. **Record the batch id.** Store `{batch_id, unit_ids}` in scratchpad or the requester-facing note so later wake-ups can call `exp_queue_status`.
3. **Do not block.** Never follow queue submission with long `exp_wait`; Python reconciles and tracks detached runs.
4. **Delegate heavy per-unit execution prep to a subagent** when a unit requires non-trivial scripting, data massage, or config expansion. Subagents have `exp_*` only; they must not inherit `eacn3_*`.
5. **Broadcast a short EACN handoff** listing the batch id, currently launched units, and pending count so Noter / requester know jobs are alive: `{batch_id, submitted, launched_now, pending}` plus a pointer to status / report artifacts.

## Pitfalls

- Reaching for `exp_wait(timeout=3600)` out of habit. This is explicitly banned as a default primitive (§Fire-and-poll).
- Forgetting to persist `batch_id` before the ephemeral session exits — detached jobs survive, your memory does not.
- Starting a subagent that inherits `eacn3_*`. Subagents must not; the whitelist enforces this.
