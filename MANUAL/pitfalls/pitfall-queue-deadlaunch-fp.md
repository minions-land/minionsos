---
id: pitfall-queue-deadlaunch-fp
kind: pitfall
domain: experiments
auth: [expert]
source: minions/tools/experiment_scheduler.py:1
since: v15.10
keywords: [queue, deadlaunch, oom, exit, false, positive, retry, project_workspace]
related: [mos_exp_queue_submit, mos_exp_queue_reconcile, mos_issue_report]
status: stable
---

# pitfall: queue cells flagged `failed` despite valid `metrics.csv`

**Symptom:**
```
status=oom exit_code=-9
bash: ... /MinionsOS/{project_workspace}/experiments/logs/exp-...: No such file or directory
```
But `metrics.csv` shows 30 000 steps, val_acc=1.0. **8 of 8 retries on
b10p9_b20p9 cells settled at `failed` despite each producing valid metrics.**

## Cause

`{project_workspace}` placeholder did not get substituted in `log_path`.
The training command runs fine, but the post-run `.exit` marker write fails,
the supervisor's reaper marks `oom`/`-9` / `dead-launch`, and the retry budget
burns to exhaustion.

Estimated waste at 2-GPU concurrency: **~3.3 hours of pure-burn compute**
across the b10p9 group.

## Recipe — preflight

Before submitting any sweep:
```python
cells = build_cells(...)
for c in cells[:3]:
    assert "{project_workspace}" not in c["log_path"], "BAD: log_path not expanded"
    assert c["log_path"].startswith("/"), "BAD: log_path not absolute"
mos_exp_queue_submit(port=37596, cells=cells, max_retries=3, group="...")
```

## Recipe — recovery (mid-storm)

Don't reconcile defensively — every reconcile dispatches more retries.
Instead:
1. Check `mos_exp_queue_status(port=...)` for the FP cells.
2. For each cell whose run-dir contains a complete `metrics.csv`:
   ```python
   # bulk-publish the actually-completed runs
  mos_publish_to_shared(role="expert-math",
    src_path=f"/abs/branches/expert-math/runs/{cell_id}/result.json",
    dst_subpath=f"handoffs/{cell_id}/result.json",
    commit_message=f"expert-math: salvage FP-flagged-but-completed cell {cell_id}")
   ```
3. File `mos_issue_report` (severity=P1, component=queue, link to evidence).
4. Stop reconciling until the underlying scheduler bug is patched.

## Detection heuristic

If `mos_exp_status(exp_id)` reports `state=failed exit_code=-9` but you can
read `metrics.csv` from disk and see `step=30000`, you're hitting this bug.
**Always cross-check disk before flagging a run as failed.**
