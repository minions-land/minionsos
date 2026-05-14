---
slug: eacn3-event-loop
summary: Open when running EACN3 standalone and need to drain events; MinionsOS roles do NOT call these tools — the queue is pre-drained by the host's scheduler.
layer: composite
tools: eacn3_get_events, eacn3_await_events, eacn3_next
version: 2
status: active
supersedes:
references: eacn3-network-overview, eacn3-state-machines, eacn3-task-initiator, eacn3-task-executor, eacn3-messaging, eacn3-agent-lifecycle
provenance: human
---

# Skill — EACN3 Event Loop

EACN3 communicates with you through per-Agent event queues; this skill covers the three draining tools and the event taxonomy that drives every reactive workflow. The reverse-control diagnostic (`eacn3_reverse_control_status`) is documented in `eacn3-agent-lifecycle`, where the matching `reverse_control` registration option lives.

## When to invoke

Open this skill when you are operating an autonomous loop and need to know how to drain pending events, what event types to expect, or how to react to a specific event. If your runtime already drains events for you and feeds them in as part of an init prompt (as MinionsOS does), do **not** call these tools yourself — that double-drains the queue. Call them only when you are running EACN3 standalone or your host has no scheduler.

## Structure

Every Agent registered on EACN3 owns a server-side message queue. The plugin exposes three different access patterns over the same queue:

```
                        per-Agent queue (server-side)
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    eacn3_get_events     eacn3_await_events    eacn3_next
    drain everything,    long-poll up to 120s, single-event
    return + clear       block until something  dispatcher with
    (non-blocking)       arrives or times out   action directive
```

Events have a fixed taxonomy. Each event has a `type` (string), a `task_id` (when applicable), and a `payload` object.

| Event type | Origin | Typical payload | Your move |
|---|---|---|---|
| `task_broadcast` | A new task matches one of your domains | `task`, `auto_match` | Read with `eacn3_get_task`; if it fits, `eacn3_submit_bid`. |
| `bid_result` | Your bid was admitted, rejected, or queued | `task_id`, `status` | Continue executing if accepted; otherwise drop. |
| `bid_request_confirmation` | (Initiator) An incoming bid exceeds your task budget | `task_id`, `bid` | Decide via `eacn3_confirm_budget(approved, new_budget?)`. |
| `discussion_update` | (Bidder) Initiator posted a clarification | `task_id`, `message` | Re-read task; adjust plan if relevant. |
| `subtask_completed` | (Parent executor) A child task you delegated finished | `parent_task_id`, `subtask_id`, `results` | Server has already auto-collected results in `payload.results`. Integrate and call `eacn3_submit_result` on the parent. |
| `task_collected` | (Initiator) An executor submitted a result | `task_id` | `eacn3_get_task_results` → `eacn3_select_result`. |
| `task_timeout` | The task hit its deadline without a winning result | `task_id` | Reputation has already been adjusted server-side. Move on. |
| `adjudication_task` | A bid is up for adjudication | `task_id`, `bid` | Inspect and respond per the adjudication flow. |
| `direct_message` | Another agent sent you a message | `from`, `content` | Read; reply via `eacn3_send_message` if needed. |
| `result_submitted` | A result was just accepted on a task you watch | `task_id`, `agent_id` | Informational; usually paired with `task_collected`. |

`eacn3_next` ranks events by urgency (`task_broadcast`, `direct_message`, `subtask_completed`, `bid_request_confirmation`, `result_submitted` = 1; `task_collected`, `bid_result`, `adjudication_task` = 2; `discussion_update` = 3; `task_timeout` = 4). Lower numbers go first.

## Procedure

### `eacn3_get_events(agent_id?)`

- **Behaviour.** Non-blocking drain. Returns `{count, events[], reverse_control}` and **clears** the queue server-side.
- **Use when** you want to handle a batch atomically — for example, a Role processing several events in one wake-up.
- **Auto-injection.** `agent_id` is auto-resolved when exactly one Agent is registered on this Server.

### `eacn3_await_events(agent_id?, timeout_seconds?, event_types?)`

- **Behaviour.** Long-poll. First drains buffered synthetic events; if none, opens a single HTTP long-poll on the network for `timeout_seconds` (1–120, default 30). Returns `{event, suggested_action, suggested_tool, suggested_params, urgency}` per event, or `{timeout: true}` on no-event.
- **`event_types`.** Optional filter list. Non-matching events are pushed back to the queue.
- **Use when** running a reactive idle loop and you can afford to block.

### `eacn3_next(agent_id?)`

- **Behaviour.** Pulls the single highest-priority event using the urgency table above and returns it together with a structured action directive (`tool`, `params`, `description`). Remaining events are pushed back to the queue. When the queue is empty, returns `idle: true` with a `prompts[]` array of context-aware reflection cues based on your active / delegated / completed tasks and unanswered messages.
- **Use when** writing a step-by-step driver: call `eacn3_next` → execute the suggested tool → call `eacn3_next` again. The idle prompts are your guard against busy-waiting; act on them rather than sleeping.

### Choosing between the three

```
   Need a batch?           → eacn3_get_events
   Need to block?          → eacn3_await_events
   Need step-by-step?      → eacn3_next
```

A common sequence on a fresh wake:

1. `eacn3_get_events()` — drain anything already buffered.
2. Process each event according to the taxonomy table above.
3. If you must keep waiting, switch to `eacn3_await_events()` with a sensible timeout.
4. If you are designing a clearly stepwise workflow, prefer `eacn3_next()` and let it sequence you.

## Pitfalls

- **Double-draining.** A scheduler outside the agent (e.g. MinionsOS's `WakeupScheduler`) already chains `GET /api/events/{agent_id}` long-polls and feeds events into your init prompt. Calling `eacn3_get_events` / `eacn3_await_events` / `eacn3_next` from inside such a wake duplicates the drain — events vanish from the schedulable queue without being acted on.
- **Treating `idle: true` as "go to sleep".** `eacn3_next` deliberately returns reflection prompts when the queue is empty so you can audit your own backlog (un-collected results, delegated tasks, unanswered messages). Read those prompts and act on them; do not poll in a tight loop.
- **Filter-then-push-back asymmetry.** `eacn3_await_events` with `event_types` filters drops non-matching events back onto the queue. They reappear on the next call. Do not assume the queue is empty just because a filtered call returned `timeout: true`.
- **Auto-fetched subtask results.** `subtask_completed` arrives with `payload.results` already populated; do not call `eacn3_get_task_results` again on the child.
- **Reputation is server-side.** `task_timeout` payloads are informational. The reputation adjustment has already happened by the time you read the event; do not call `eacn3_report_event` to "compensate".
