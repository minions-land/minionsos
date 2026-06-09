---
id: mos_exp_queue_status
kind: tool
domain: experiments
auth: [expert]
source: minions/tools/mcp/experiment_tools.py:110
since: stable
keywords: [queue, status, running, pending, failed, alive]
related: [mos_exp_queue_reconcile, mos_exp_queue_submit, mos_exp_queue_plan]
status: stable
---

# mos_exp_queue_status

**One line:** Inspect the project queue. Your "is the queue alive?" probe.

## Signature
```py
mos_exp_queue_status(port: int) -> {
  running: int,
  pending: int,
  no_capacity: int,
  done: int,
  failed: int,
  cells: [ { cell_id, state, attempts, max_retries, started_at, finished_at, ... } ],
}
```

## Use as triage
Use `_status` before diagnosing a scheduler failure. A healthy queue can
show a mix of `done`, `attempting`, and `pending` cells. **Always inspect
status before claiming the queue is dead.**

## FP detection
For each `cell_id` in `failed`, cross-check the on-disk run-dir for a
complete `metrics.csv`. If found, the cell is a `pitfall-queue-deadlaunch-fp`
victim — don't retry, salvage via `mos_publish_to_shared` instead.

## See also
- domain-experiments
- pitfall-queue-deadlaunch-fp
