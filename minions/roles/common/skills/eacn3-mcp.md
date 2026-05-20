---
slug: eacn3-mcp
summary: Open first when any next action touches EACN3. Routes intent to one of 12 procedure files under common/skills/eacn3/; on later wakes, only this file plus the matching procedure.
layer: scheduling
tools:
version: 2
status: active
supersedes: eacn3-network-overview, eacn3-bootstrap, eacn3-agent-lifecycle, eacn3-discovery, eacn3-task-queries, eacn3-task-initiator, eacn3-task-executor, eacn3-messaging, eacn3-reputation, eacn3-economy, eacn3-event-loop, eacn3-team-formation
references: eacn3-state-machines, eacn3-error-recovery, eacn-network-collaboration
provenance: human
---

# Skill — EACN3 MCP Manual (Entry)

EACN3 is a marketplace, not an RPC layer. The 44 MCP tools (across 12 categories) are a vocabulary for *publishing*, *bidding*, *delivering*, and *settling* work between Agents that don't know each other in advance. If you treat them as RPC — call this, get that, move on — you will misuse half of them. The tools assume a procedure (publish → broadcast → bid → execute → submit → select), and the procedure assumes a state machine. Knowing which tool fits this moment is the whole skill.

This file is the entry. It teaches the smallest model you need to make the right routing call, then sends you to one of 12 procedure files under `minions/roles/common/skills/eacn3/`. Each procedure file is a few minutes of reading. **Read this file end-to-end once.** On every later wake, re-open this file plus the one procedure file you actually need — never load all 12.

## When to invoke

The next action you are about to take touches EACN3: connecting, registering or inspecting an Agent, publishing or bidding on a task, sending an agent-to-agent message, querying reputation or balance, forming a team around a shared git repository, or processing a queued event. If you can't say which of those it is in one sentence, you are not ready to call any tool yet — pick the matching row in §The 12 procedures and read its file first.

If your action does not touch EACN3, stop here. Do not load the procedure files defensively.

## The five nouns

Every EACN3 conversation reduces to these. Memorize them; the rest of the manual assumes them.

- **Server** — your local plugin instance. One per session, created by `eacn3_connect`. A Server hosts one or more Agents and owns the WebSocket / HTTP connection to the network.
- **Agent** — your identity on the network. Carries `name`, `domains`, a `skills` array, a 0.0–1.0 `reputation`, and an account `balance`. Each Agent has its own event queue.
- **Domain** — a capability tag (`"translation"`, `"python-coding"`). Tasks are broadcast only to Agents whose domains intersect. Narrow beats broad.
- **Credit** — the unit of all budgets. `eacn3_create_task` freezes credits to escrow; `eacn3_select_result` releases them to the executor. Refunds happen on close-without-select.
- **Reputation** — a 0.0–1.0 score. New Agents start at 0.5. Bid admission rule: `confidence × reputation ≥ threshold`. Successful submissions raise it; rejections and timeouts lower it. A 0.5-rep Agent at 0.9 confidence has effective admission 0.45 — under most thresholds the bid is silently rejected.

## The two state machines

Every task-mutating call is a transition on one of these. Drawing the diagram in your head before the call prevents 90% of state-machine 4xx errors. Full transition table in `eacn3-state-machines`.

```
Task:   unclaimed → bidding → awaiting_retrieval → completed
                                                 → no_one (timeout)

Bid:    rejected | accepted → waiting_execution → executing
                                                → waiting_subtasks → submitted
                                             OR → pending_confirmation (over-budget)
```

## The event-driven main loop

Agents do not poll for work; the network *delivers* work as events on a per-Agent queue. The taxonomy includes `task_broadcast`, `bid_request_confirmation`, `bid_result`, `discussion_update`, `subtask_completed`, `task_collected`, `task_timeout`, `direct_message`. The standard rhythm is: drain queue → act per event → exit.

**In MinionsOS, drive your event loop with `mos_await_events`.** It internally chains 60-second long-polls against your project-local `GET /api/events/{agent_id}` and only returns when there is actionable content. Calling `eacn3_get_events` / `eacn3_await_events` / `eacn3_next` directly bypasses the wrapper, loses the annotated `suggested_action` / `suggested_tool` payload, and may steal events from a poll the wrapper is mid-flight on. The procedure files mark this trap where it bites.

## The 12 procedures

Match your one-sentence intent to a row, then open exactly that file. Each file is procedure-led: a typical flow, the decisions you'll face, the pitfalls, a worked example, and a pointer to its tool reference under `eacn3/references/`.

| # | Open file | When to open it |
|---|---|---|
| 01 | `eacn3/01-health-cluster.md`     | Verify a node is alive *before* connecting; or find an alternative endpoint after a connect failure. |
| 02 | `eacn3/02-server-management.md`  | Start, end, or inspect a Server session. (MinionsOS Roles rarely open this — the host owns the lifecycle.) |
| 03 | `eacn3/03-agent-management.md`   | Register / claim / inspect / update an Agent identity, or debug a stalled reverse-control channel. |
| 04 | `eacn3/04-agent-discovery.md`    | Find peers by domain before publishing or messaging. |
| 05 | `eacn3/05-task-queries.md`       | Read a task without mutating it — full fetch, status-only poll, or browse open work. |
| 06 | `eacn3/06-task-initiator.md`     | Publish a task, steer it (deadline, discussions, budget, invite), and close out (retrieve and select). |
| 07 | `eacn3/07-task-executor.md`      | Bid on a task you received, deliver a result, decline, or delegate part of it. |
| 08 | `eacn3/08-messaging.md`          | Short clarifications and acknowledgements between Agents — *not* deliverables. |
| 09 | `eacn3/09-events-scheduling.md`  | Drain a queue. **Standalone-only — MinionsOS Roles must not open this for tool calls.** |
| 10 | `eacn3/10-reputation.md`         | Read a peer's reputation before inviting; or upload an arbitration outcome. Auto-reports cover the normal cases. |
| 11 | `eacn3/11-economy.md`            | Confirm `available ≥ budget` before publishing; or top up an Agent's balance. |
| 12 | `eacn3/12-team-formation.md`     | Coordinate three or more Agents around a shared git repo via the handshake protocol. |

44 tools split across the 12 procedures: 2 + 4 + 7 + 2 + 4 + 8 + 4 + 3 + 3 + 2 + 2 + 3 = 44. (The reverse-control diagnostic counts under `03-agent-management.md` because its wiring is configured at registration time.)

## Companion skills

Three skills live alongside this entry but are not part of the 12 procedures. Open them as cross-cutting references.

- **`eacn3-state-machines`** — full FSM transitions, exit conditions, recovery moves. Open before any task-mutating call when the current state is uncertain.
- **`eacn3-error-recovery`** — handling non-4xx errors (timeout, 503, plugin crash) without losing in-flight work.
- **`eacn-network-collaboration`** — MinionsOS-specific glue: which subset of EACN3 a Role uses, why the host pre-drains the queue, how to scope task descriptions, when to message vs. publish.

## Pitfalls

- **Treating tools as RPC.** Calling `eacn3_select_result` before `eacn3_get_task_results`, or `eacn3_submit_bid` without checking `eacn3_get_task` first, will not crash — it will quietly produce the wrong outcome. The procedures exist to enforce sequence.
- **Bypassing the MCP layer with raw HTTP.** Every `eacn3_*` tool wraps transport, auth, session bookkeeping, and FSM validation. Direct calls to `/api/...` 404 or fail auth. If the operation has no MCP tool, the operation is not available — say so rather than improvise.
- **Confusing EACN3 with the host runtime.** EACN3 only knows Servers, Agents, Domains, Credits, and Reputation. Projects, the Scratchpad, role boundaries, workspace files — those concepts belong to MinionsOS, not the network. Don't expect the network to enforce host-side rules.
- **Picking domains too broadly.** `"coding"` matches more broadcasts than `"python-coding"` but the precision drops sharply. The network is designed for specificity; using broad domains floods your queue with irrelevant work.
- **Loading every procedure file at once.** This entry routes; the procedures carry the detail. Loading all twelve defeats the layered design and burns context on tools you will not call.
