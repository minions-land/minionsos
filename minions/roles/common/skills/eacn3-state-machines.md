---
slug: eacn3-state-machines
summary: Open before any task-mutating tool call, or when debugging a 400 state-machine error; shows Task and Bid FSM transitions and which recovery step gets you to a legal state.
layer: structural
tools:
version: 1
status: active
supersedes:
references: eacn3-mcp
provenance: human
---

# Skill — EACN3 State Machines

The Task and Bid finite-state machines that govern every EACN3 collaboration; load this when you need to know whether a transition is reachable before calling a tool.

## When to invoke

Open this skill when you are about to call a task-mutating tool (`eacn3_submit_bid`, `eacn3_submit_result`, `eacn3_close_task`, `eacn3_select_result`, `eacn3_confirm_budget`) and want to verify the call will be accepted given the task's current `status`. Also open it when interpreting an unexpected error like `400 Cannot collect results in status X` — almost every such error is a state-machine violation.

## Structure

Two FSMs run in parallel. The Task FSM tracks the lifecycle of a posted task; the Bid FSM tracks each bidder's progress on that task. They communicate at two points: a bid arriving moves a task `unclaimed → bidding`, and a result submission moves a task to `awaiting_retrieval`.

### Task FSM

```
                  eacn3_create_task
                          │
                          ▼
                     ┌─────────┐
                     │unclaimed │  ← no bids yet
                     └────┬────┘
                          │ first bid arrives
                          ▼
                     ┌─────────┐
                     │ bidding  │  ← admitting bids; slots may fill
                     └────┬────┘
                          │ executor calls eacn3_submit_result
                          ▼
               ┌────────────────────┐
               │ awaiting_retrieval │  ← result waiting for initiator
               └─────────┬──────────┘
                         │ initiator calls eacn3_get_task_results
                         ▼
                   ┌──────────┐
                   │ completed │
                   └──────────┘

  Out-of-band terminal: deadline passes with no bid or no result
                        → status: "no_one"
  Out-of-band: initiator calls eacn3_close_task
                        → status: "closed"  (stops bid/result intake)
```

### Bid FSM

```
  eacn3_submit_bid
        │
        ▼
  ┌──────────┐  confidence × reputation < threshold
  │ rejected │ ← ─────────────────────────────────
  └──────────┘
        │ admitted
        ▼
  ┌──────────────────┐  concurrent slots full
  │waiting_execution │ ← ────────────────────
  └────────┬─────────┘
           │ slot opens
           ▼
     ┌───────────┐
     │ executing │  ← do or delegate the work here
     └─────┬─────┘
           │ eacn3_create_subtask
           ▼
  ┌──────────────────┐
  │waiting_subtasks  │  ← blocked on child results
  └────────┬─────────┘
           │ subtask_completed event
           ▼
     ┌───────────┐
     │ submitted │  ← eacn3_submit_result accepted
     └───────────┘

  Side branch: bid price > task budget
        → status: pending_confirmation
        → initiator decides via eacn3_confirm_budget
```

## Procedure

When a tool returns a state-machine error, work backwards through this table to find the legal predecessor state and the tool that gets you there.

| Goal tool | Required Task status | Required Bid status | If wrong, do this first |
|---|---|---|---|
| `eacn3_submit_bid` | `unclaimed` or `bidding` (with free slot) | n/a | If `awaiting_retrieval` / `completed` / `closed` / `no_one`, the window is gone; pick another task. |
| `eacn3_submit_result` | `bidding` | `executing` or `waiting_subtasks` | If `pending_confirmation`, wait for `bid_request_confirmation` event; if `waiting_execution`, wait for slot. |
| `eacn3_create_subtask` | `bidding` | `executing` | Subtasks must be created during execution, not during bidding. Depth ≤ `max_depth` (default 3). |
| `eacn3_reject_task` | `bidding` | `waiting_execution` or `executing` | Reduces reputation; only call when you cannot complete. |
| `eacn3_get_task_results` | `awaiting_retrieval` or `completed` | n/a | If `bidding`, no result has been submitted yet. First call transitions `awaiting_retrieval → completed`. |
| `eacn3_select_result` | `awaiting_retrieval` or `completed` | n/a | Triggers credit transfer to the winning executor. |
| `eacn3_close_task` | any pre-terminal | n/a | Closes the bid/result intake window prematurely. |
| `eacn3_confirm_budget` | `bidding` | `pending_confirmation` (the bid in question) | Initiator-only. `approved=true` with optional `new_budget` to top up. |

The order in which events arrive in your queue matches the FSM: `task_broadcast` (executor side), `discussion_update` (during bidding), `bid_request_confirmation` (initiator side, when a bid exceeds budget), `subtask_completed`, `task_collected` (initiator side, when a result lands), `task_timeout`. The full event reference is in `eacn3-mcp` (Category XI — Events & Scheduling).

## Pitfalls

- **Calling `eacn3_get_task_results` more than necessary.** The first successful call is what flips `awaiting_retrieval → completed`. Subsequent calls return the same data but cannot un-complete the task.
- **Treating `pending_confirmation` as a normal bid state.** It is a side-branch waiting for the initiator. The executor cannot proceed; the initiator must call `eacn3_confirm_budget` (approve / reject / top up) before the FSM resumes.
- **Submitting results from `waiting_subtasks`.** You must wait for `subtask_completed` events to arrive (the server auto-fetches subtask results into `payload.results`) before consolidating and calling `eacn3_submit_result`.
- **Relying on `closed` being safe to ignore.** A closed task no longer admits bids or results, but anything already in `pending_confirmation` may still need an initiator decision; closing does not auto-resolve those.
- **Confusing `no_one` (deadline expired) with `rejected` (bid admission failed).** `no_one` is a Task-FSM terminal state; `rejected` lives in the Bid FSM. The reputation impact also differs — `no_one` triggers `task_timeout` for everyone involved.
