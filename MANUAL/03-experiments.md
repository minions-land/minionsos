# 03 — Experiments (Coder)

> **L2 card.** Coder owns this surface. Other roles do not run experiments — they request via EACN message.
> Top three: `mos_exp_run` (one-off), `mos_exp_queue_submit` (sweep), `mos_exp_queue_reconcile` (reap+dispatch).
> **Read PITFALLS § P-3 BEFORE submitting any sweep.** project_37596 burned ~3 hours of GPU on a `{project_workspace}` substitution bug.

---

## mos_exp_run — one-off, blocking-ish

```python
args:
  command: str                # full shell command
  cwd: str | None             # absolute path; defaults to coder branch root
  execution: "local" | "ssh" | "auto"
  ssh_target: str | None
  gpu_ids: list[int] | None
  timeout_s: int | None       # default ~7200; raise for long training
  log_path: str | None        # absolute path; never `{project_workspace}` literal
  env: dict[str,str] | None
returns: { exp_id, started_at, log_path }
```

**Discipline.**
- Always pass `log_path` as an absolute path under `branches/coder/` or `experiments/logs/`.
- `gpu_ids=[1]` is a 5-second probe-friendly default — verify CUDA propagation before launching real training.
- `timeout_s` includes startup. For 30k-step grokking runs, set ≥ 3600.

---

## mos_exp_status / mos_exp_tail / mos_exp_get / mos_exp_list

| Tool | What | Cost |
|---|---|---|
| `_status(exp_id)` | `{state, exit_code, started_at, finished_at, gpu_ids}` | cheap |
| `_tail(exp_id, n=50)` | last N stdout lines | cheap |
| `_get(exp_id)` | full result bundle (incl. metrics summary) | medium |
| `_list(filter)` | list experiments matching filter | medium |

**Pitfall (project_37596):** `_status` may report `state=failed exit_code=-9` even when training succeeded. Always cross-check `metrics.csv` on disk before flagging a run as failed.

---

## mos_exp_wait / mos_exp_kill

```python
_wait(exp_id, timeout_s) -> { state, exit_code, ... }   # blocks
_kill(exp_id) -> { state }                              # SIGTERM then SIGKILL
```

---

## mos_exp_put / mos_exp_get

Stage / fetch artifacts:
```python
_put(src_path, dst_subpath)                             # into project's exp store
_get(exp_id, artifact_path) -> { content, sha, ... }
```

---

## mos_query_gpus

```python
_query_gpus(execution="local") -> [ { index, name, free_mem_mb, util_pct } ]
```
**Pitfall (PITFALLS § P-7):** `execution="auto"` is rejected. Always pass `"local"`.

---

## Queue: mos_exp_queue_submit

Submit a Cartesian sweep into the project's persistent SQLite queue.

```python
args:
  cells: list[dict]            # each cell = full param dict + computed log_path
  max_retries: int = 2
  priority: int = 0
  group: str | None
returns: { submitted, rejected, queue_state }
```

**Critical preflight (PITFALLS § P-3):**
1. Render every cell once locally and check `cell["log_path"]` is an **absolute path**, not a string containing `{project_workspace}`.
2. `max_retries` carries OVER between reconciles. If yesterday's run hit the cap, today's submission of the same cell starts at `attempts=cap` and goes straight to `failed`. Bump `max_retries` if you're re-submitting after a reaper bug fix.

---

## mos_exp_queue_reconcile

Reap finished cells, dispatch the next wave to the GPU pool.

```python
args:
  port: int
  max_dispatch: int | None     # cap new launches this call
returns: { reaped, dispatched, queue_state }
```

**Don't:**
- Don't reconcile defensively in a loop. project_37596's coder spent **46 minutes simmering** because every wake started with a bare reconcile that did nothing.
- Don't reconcile while the dead-launch FP bug is unresolved — you'll burn retry budget. File `mos_issue_report` first.

---

## mos_exp_queue_status / mos_exp_queue_plan

```python
_queue_status(port) -> { running, pending, no_capacity, done, failed, cells: [...] }
_queue_plan(port) -> { dispatch_plan, gpu_packing, est_completion_iso }
```

`_status` is your "is the queue alive?" probe. project_37596's ISS-37596-18 was filed as a "zombie scheduler" suspect, but the status showed 28 done / 8 attempting / 88 pending — the queue was healthy. **Always inspect `_status` before claiming the queue is dead.**

---

## mos_exp_gpu_pool_set / mos_exp_gpu_pool_get

```python
_gpu_pool_set(port, gpu_ids=[0,1], max_concurrent=2)
_gpu_pool_get(port) -> { gpu_ids, current_load, ... }
```
The pool is the queue's resource budget. Set it small for pilots, expand once stable.

---

## Real example (project_37596 P2 sweep)

```python
# 1. Build cells (108 = 3 eps × 3 β1 × 3 β2 × 4 seeds)
cells = build_eps_beta_cells(...)

# 2. Preflight: spot-check log_path expansion (would have caught ISS-37596-10)
assert "{project_workspace}" not in cells[0]["log_path"]

# 3. Reserve GPUs
mos_exp_gpu_pool_set(port=37596, gpu_ids=[0,1], max_concurrent=2)

# 4. Submit
mos_exp_queue_submit(port=37596, cells=cells, max_retries=3, group="p4-eps-beta")

# 5. Drive on each wake (NOT in a tight loop)
mos_exp_queue_reconcile(port=37596)
status = mos_exp_queue_status(port=37596)
# inspect status.failed for FP candidates BEFORE redispatching
```
