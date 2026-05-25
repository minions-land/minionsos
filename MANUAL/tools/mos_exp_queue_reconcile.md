---
id: mos_exp_queue_reconcile
kind: tool
domain: experiments
auth: [coder]
source: minions/tools/mcp/experiment_tools.py:103
since: stable
keywords: [queue, reconcile, reap, dispatch, retry, sweep]
related: [mos_exp_queue_submit, mos_exp_queue_status, pitfall-queue-deadlaunch-fp]
status: stable
---

# mos_exp_queue_reconcile

**One line:** Reap finished cells, dispatch the next wave to the GPU pool.

## Signature
```py
mos_exp_queue_reconcile(
  port: int,
  max_dispatch: int | None,    # cap new launches this call
) -> { reaped, dispatched, queue_state }
```

## Don't
- **Don't reconcile defensively in a loop.** Project_37596 spent 46 minutes
  "simmering" on bare reconciles that did nothing.
- **Don't reconcile while the dead-launch FP bug is unresolved.** You'll burn
  retry budget on cells that already produced valid `metrics.csv`. File
  `mos_issue_report` first; salvage via direct `mos_publish_to_shared`.

## When to call
- Right after `mos_exp_queue_submit` to start dispatch.
- On EACN events of type `experiment_completed`.
- Periodically while a sweep is active — but **only when there's something to reap**.
  Use `mos_exp_queue_status` first; if no rows are in `running` with `finished_at`,
  skip the reconcile.

## See also
- domain-experiments
- pitfall-queue-deadlaunch-fp
- mos_exp_queue_status
