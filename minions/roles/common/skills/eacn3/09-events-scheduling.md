# Category XI — Events & Scheduling

Open this only for standalone EACN3 loops or when debugging the wrapper itself. Every tool here is drain-on-read: once an event is returned, it is gone from the queue. In MinionsOS Roles, drive the loop with `mos_await_events`; calling these tools directly bypasses the wrapper, drops the suggested-action annotations, and may steal events from a long-poll the wrapper is mid-flight on.

## When to invoke

- You are writing or operating a standalone EACN3 Agent outside MinionsOS.
- You are debugging MinionsOS scheduler plumbing itself, not doing normal Role work.
- You need to understand why an event loop chose a suggested tool or urgency.
- You are testing drain semantics in an isolated environment.
- If you are a normal MinionsOS Role, stop here; act on the events already in your wake prompt.

## The typical flow

1. Decide whether you need one event, all current events, or a long poll. Use `eacn3_next` for one prioritized action, `eacn3_get_events` for a batch, and `eacn3_await_events` for a bounded wait. The response field that matters first is `idle`, `count`, or `timeout`.
2. In standalone loops, prefer `eacn3_next`. Its `event`, `action`, `tool`, `params`, and `remaining` fields tell you exactly what to process and whether more events are queued.
3. When using `eacn3_await_events`, set `event_types` only when unrelated events must be preserved. The response `suggested_tool`, `suggested_params`, and `urgency` drive dispatch.
4. When using `eacn3_get_events`, persist the event IDs and task IDs before doing slow work. The batch is already consumed.
5. If `eacn3_next` returns `idle: true`, inspect `prompts[]`, `active_tasks[]`, `delegated_tasks[]`, and `unanswered_from[]`; idle does not mean there is no work.
6. Exit when the queue is empty or the current event has been handed to its category procedure.

## Decisions you'll face

- **`next` or batch?** Use `next` for normal loops. Batch only when you can process or persist every event immediately.
- **Long poll or return now?** Use `await_events` when the process exists only to wait. In interactive agents, return control instead of sleeping.
- **Filter event types?** Filter when a test or specialized worker needs one type; otherwise broad drains preserve priority ordering.
- **What does idle mean?** It means no new queue event. Base next action on `prompts[]`, not on a blind sleep.

## Pitfalls

- Calling these tools as a MinionsOS Role. The host already drained your events; your call consumes the next wake's input and makes the runtime look flaky.
- Treating the queue as replayable. Drain-on-read means a lost event is gone unless you persisted its content.
- Processing a batch synchronously without first recording IDs. A crash halfway through loses the rest of the batch.
- Sleeping after `eacn3_next` returns idle while `prompts[]` names unfinished work.
- Assuming `timeout_seconds: 120` is always wise. Long waits are for standalone daemons, not Role wakes.

## Worked example

```text
eacn3_next({agent_id: "agent-standalone-1"})
→ idle: false, action: "bid", tool: "eacn3_submit_bid",
  params: {task_id: "t-doc-fix"}, remaining: 2

eacn3_get_task({task_id: "t-doc-fix"})
→ status: "bidding", domains: ["technical-writing"]

eacn3_submit_bid({
  task_id: "t-doc-fix",
  confidence: 0.85,
  price: 25
})
→ status: "waiting_execution"
```

## Tool reference

For full per-tool detail (parameters, preconditions, side effects, return shape), open `references/09-events-scheduling-tools.md`.
