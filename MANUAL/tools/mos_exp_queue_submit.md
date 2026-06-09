---
id: mos_exp_queue_submit
kind: tool
domain: experiments
auth: [expert]
source: minions/tools/mcp/experiment_tools.py:96
since: stable
keywords: [queue, submit, sweep, cells, retry, sweep, batch]
related: [mos_exp_queue_reconcile, mos_exp_queue_status, mos_exp_gpu_pool_set, pitfall-queue-deadlaunch-fp]
status: stable
---

# mos_exp_queue_submit

**One line:** Submit a Cartesian sweep into the project's persistent SQLite queue.

## Signature
```py
mos_exp_queue_submit(
  port: int,
  cells: list[dict],         # each = full param dict + computed log_path
  max_retries: int = 2,
  priority: int = 0,
  group: str | None,
) -> { submitted, rejected, queue_state }
```

## Critical preflight
```py
# Check log_path expansion BEFORE submitting (catches the FP retry storm)
assert "{project_workspace}" not in cells[0]["log_path"]
assert cells[0]["log_path"].startswith("/")
```

## max_retries semantics
**Carries OVER between reconciles.** If yesterday's run hit the cap, today's
submission of the same cell starts at `attempts=cap` and goes straight to
`failed`. Bump `max_retries` if you're re-submitting after a reaper bug fix.

## Example
```py
mos_exp_queue_submit(
  port=<port>,
  cells=cells,                  # 108 = 3 eps × 3 β1 × 3 β2 × 4 seeds
  max_retries=3,
  group="p4-eps-beta",
)
```

## See also
- domain-experiments
- pitfall-queue-deadlaunch-fp
