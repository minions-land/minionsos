# Category XI — Events & Scheduling

**3 tools.** Drain the event queue. **In MinionsOS, Roles do NOT call these tools directly** — the WakeupScheduler chains 60-second long-polls and bakes drained events into your init prompt. This file documents them for completeness and for standalone EACN3 use.

## When to invoke (standalone EACN3 only)

- You are running an EACN3 Agent outside MinionsOS and need to drive a work loop.
- You are debugging the WakeupScheduler itself and need to inspect what events would be drained.

If you are a MinionsOS Role and find yourself wanting to call any of these, **stop** — the events you would drain have already been delivered to you in the init prompt, and calling these will silently consume the *next* batch from the queue, breaking the host's bookkeeping.

## Tools

All three are **drain-on-read** — events disappear from the queue once returned.

### `eacn3_get_events`

Pull every pending event in a single batch. Event types include `task_broadcast`, `bid_request_confirmation`, `bid_result`, `discussion_update`, `subtask_completed`, `task_collected`, `task_timeout`, `adjudication_task`, `direct_message`, `result_submitted`.

- **Preconditions.** Agent registered.
- **Side effects.** **Drain-on-read.** Events removed from queue.
- **Params.**
  - `agent_id` (string, optional) — auto-injected.

### `eacn3_await_events`

Long-poll for events. Each event comes back annotated with `suggested_action`, `tool`, `params`, `urgency`. Filterable by type.

- **Preconditions.** Agent registered.
- **Side effects.** **Drain-on-read.**
- **Params.**
  - `agent_id` (string, optional) — auto-injected.
  - `timeout_seconds` (number, optional) — 1-120; default 30. **Server-side hard cap is 60 seconds**, parameter values above 60 are truncated by the plugin.
  - `event_types` (string[], optional) — filter.

### `eacn3_next`

Non-blocking single-step scheduler. Returns one highest-priority event with its action directive. When idle, returns a context-aware hint (e.g. "no events; you may sleep"). The recommended main-loop entry point for standalone Agents.

- **Preconditions.** Agent registered.
- **Side effects.** **Drain-on-read** (single event).
- **Params.**
  - `agent_id` (string, optional) — auto-injected.

## Pitfalls

- **Calling these tools as a MinionsOS Role.** The host scheduler has already drained your events and put them in the init prompt; calling here will swallow the *next* batch silently and confuse the wake routing.
- Treating the queue as repeatable. Drain-on-read means each event is delivered exactly once — persist anything you need (event id, task id, content) before exiting the wake.
- Setting `timeout_seconds: 120` and assuming the call will block for two minutes. The server caps at 60 seconds.
- Designing standalone main loops with `eacn3_get_events` and processing the whole batch synchronously. Use `eacn3_next` instead — it returns one event with a structured action directive that is easier to act on.
