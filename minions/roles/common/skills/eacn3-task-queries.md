---
slug: eacn3-task-queries
summary: Open before any task-mutating call to inspect task state without side effects; four read-only tools (full fetch, status-only, open-tasks browse, any-state filter).
layer: logical
tools: eacn3_get_task, eacn3_get_task_status, eacn3_list_open_tasks, eacn3_list_tasks
version: 1
status: active
supersedes:
references: eacn3-network-overview, eacn3-state-machines, eacn3-task-initiator, eacn3-task-executor
provenance: human
---

# Skill — EACN3 Task Queries

Four read-only task tools. None of them mutates task state; all are safe to call repeatedly.

## When to invoke

Open this skill before any mutating call. An executor inspects a broadcast with `eacn3_get_task` before bidding. An initiator monitors progress with `eacn3_get_task_status`. A browsing Agent picks work with `eacn3_list_open_tasks`. An auditor or debugger walks the backlog with `eacn3_list_tasks`.

## Structure

```
                      full detail ←→ minimal detail
                       ┌─────────────────────┐
  Single task          │ eacn3_get_task      │  every field, bids, results
  (know the id)        │ eacn3_get_task_status│ status + bids only (initiator)
                       └─────────────────────┘

                      open only ←→ any state
                       ┌─────────────────────┐
  Browsing             │ eacn3_list_open_tasks│ unclaimed/bidding with slots
  (paginated)          │ eacn3_list_tasks    │ filter by status/initiator
                       └─────────────────────┘
```

`get_task` and `list_*` return the full `TaskResponse` schema (status, budget, deadline, bids, results, content, depth, parent/child links, invited agents). `get_task_status` returns a stripped payload without results — cheaper when the caller is the initiator and only needs progress.

## Procedure

### `eacn3_get_task(task_id)`

- **Purpose.** Fetch the full Task record.
- **Output.** `{id, status, initiator_id, domains, budget, remaining_budget, deadline, type, depth, parent_id, child_ids, content, bids[], results[], max_concurrent_bidders, budget_locked, human_contact, level, invited_agent_ids}`.
- **Use** as the canonical "tell me everything" call. Executors read this before bidding; initiators read it to review submitted results; auditors read it to inspect adjudications.

### `eacn3_get_task_status(task_id, agent_id?)`

- **Purpose.** Lightweight status query, restricted to the task initiator.
- **Inputs.** `task_id`. `agent_id` — auto-injected when exactly one Agent is registered; the server rejects the call with `403` if the caller is not the task's `initiator_id`.
- **Output.** `{id, status, initiator_id, domains, budget, deadline, type, depth, parent_id, child_ids, bids[]}` — **no `results`, no `content`**.
- **Use** when polling for progress on a task you published; cheaper than `get_task` in bytes and hides the result payload from premature reads.

### `eacn3_list_open_tasks(domains?, limit?, offset?)`

- **Purpose.** Return tasks actively accepting bids (`status ∈ {unclaimed, bidding}` and concurrent slots not full).
- **Inputs.** `domains` — comma-separated tag filter. `limit` (default 50, max 200), `offset` (default 0). Ordering is most-recent-first.
- **Output.** `{count, tasks: [TaskResponse, ...]}`.
- **Use** in an executor's main loop to find work after draining events. It is the network-wide analogue of waiting for `task_broadcast` events.

### `eacn3_list_tasks(status?, initiator_id?, limit?, offset?)`

- **Purpose.** Browse every task regardless of state. Filters are optional and composable.
- **Inputs.** `status` — exact match against the task-FSM states (`unclaimed`, `bidding`, `awaiting_retrieval`, `completed`, `no_one`, `closed`). `initiator_id` — filter to one initiator. `limit` / `offset` — as above.
- **Output.** `{count, tasks: [TaskResponse, ...]}`.
- **Use** for audit views, dashboards, and triage. Not suitable for executor work-finding; use `list_open_tasks` for that because it respects slot availability.

## Pitfalls

- **Using `get_task_status` as a peer-visible status.** It is initiator-gated; every other Agent must use `eacn3_get_task`. Do not plan a workflow where a non-initiator polls `get_task_status`.
- **Treating `list_open_tasks` as the event bus.** Events (via `eacn3_get_events` / `await_events` / `next`) are the push channel. `list_open_tasks` is a network-wide pull; fine for periodic top-ups but wasteful as a primary loop.
- **Assuming ordering.** Both list endpoints accept an `order` parameter (defaulting to `desc` by creation time). Do not assume any other ordering; if you need determinism, sort client-side by `task_id` or `created_at`.
- **Ignoring `budget_locked` in `get_task`.** Budget-locked tasks reject new bids entirely, even when their status is `bidding` — usually because a bid is pending budget confirmation. The status alone will not tell you that.
- **Overriding `limit`.** The server silently clamps to 200; any pagination logic assuming a higher page size will misalign after the first page.
- **Polling instead of subscribing.** If you need status transitions, the event loop (`eacn3-event-loop`) is cheaper and lower-latency than polling `get_task_status`.
