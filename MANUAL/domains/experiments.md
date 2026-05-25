---
id: domain-experiments
kind: domain
domain: experiments
auth: [coder]
source: minions/tools/mcp/experiment_tools.py:1
since: stable
keywords: [exp, experiment, queue, gpu, training, sweep, dispatch]
related: [mos_exp_run, mos_exp_queue_submit, mos_exp_queue_reconcile, pitfall-queue-deadlaunch-fp]
status: stable
---

# Domain: Experiments

Coder owns this surface. Other roles request via EACN message — they don't
run experiments themselves.

## The two questions before any sweep

1. **Did `log_path` substitute correctly?** If `cells[0]["log_path"]` contains
   the literal `{project_workspace}`, you're about to fire 3 hours of GPU into
   a retry storm. See `pitfall-queue-deadlaunch-fp`.
2. **Is `max_retries` carrying over?** Failed cells from yesterday count
   against today's quota. Bump it if you're re-submitting a known-good batch.

## Top tools

```bash
lookup.py --id mos_exp_run             # one-off
lookup.py --id mos_exp_queue_submit    # sweep
lookup.py --id mos_exp_queue_reconcile # reap + dispatch
lookup.py --id mos_exp_queue_status    # is the queue alive?
lookup.py --id mos_exp_gpu_pool_set    # reserve GPUs
```

## Discipline

- Always pass `log_path` as an **absolute path** under `branches/coder/`.
- `gpu_ids=[1]` is your 5-second probe-friendly default.
- For 30k-step grokking runs, `timeout_s ≥ 3600`.
- `mos_query_gpus(execution="local")` — `auto` is rejected.
- Don't reconcile in a defensive loop. Project_37596 burned 46 minutes
  "simmering" on bare reconciles that did nothing.

## Project venv vs MinionsOS venv

The Role process runs in MinionsOS uv env. Your project's `pandas` / `torch`
live in a separate venv. Either:
- `mos_exp_run(command="cd /path/proj && source .venv/bin/activate && python ...", execution="local")`
- or `mos_exp_run` with explicit interpreter path: `command="/proj/.venv/bin/python ..."`

Never `uv sync` from inside `branches/<role>/...` — creates a nested `.venv`
and breaks MCP servers (project_37596 / expert-mathematician hit `os error 17`).

## Full surface

```bash
lookup.py --domain experiments
```
