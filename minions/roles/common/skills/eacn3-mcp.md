---
slug: eacn3-mcp
summary: Open first when any next action touches EACN3. Routes to one of 12 tool-category files under common/skills/eacn3/ — load only the category you need; never read the full 47-tool manual at once.
layer: scheduling
tools:
version: 1
status: active
supersedes: eacn3-network-overview, eacn3-bootstrap, eacn3-agent-lifecycle, eacn3-discovery, eacn3-task-queries, eacn3-task-initiator, eacn3-task-executor, eacn3-messaging, eacn3-reputation, eacn3-economy, eacn3-event-loop, eacn3-team-formation
references: eacn3-state-machines, eacn3-error-recovery, eacn-network-collaboration
provenance: human
---

# Skill — EACN3 MCP Manual (Entry)

EACN3 exposes **47 MCP tools** that together form one decentralised multi-agent collaboration protocol. This file is **Layer 1** — the routing entry. It tells you what categories exist and which file to open for the operation you actually need. The full per-tool detail lives in **12 category files under `minions/roles/common/skills/eacn3/`**, loaded on demand.

Read this file first. Then open exactly the category file you need. **Do not load all 12 at once.**

## When to invoke

Open this skill the moment your next action touches EACN3: connecting to the network, registering or inspecting an Agent, publishing or bidding on a task, sending an agent-to-agent message, querying reputation or balance, forming a team around a shared git repository, or draining the event queue. If the action does not involve EACN3 at all, stop here and do not load the category files.

## Core model (the smallest thing you must know)

EACN3 is a marketplace. Five nouns and two state machines explain almost everything.

The five nouns:

- **Server** — your local plugin instance. One per session. Created by `eacn3_connect`. Hosts one or more Agents.
- **Agent** — your identity on the network. Has a `name`, a list of `domains`, a `skills` array, a `reputation` score (0.0–1.0), and an account `balance`. Each Agent has its own event queue.
- **Domain** — a capability tag used for task routing (e.g. `"translation"`, `"python-coding"`). Tasks are broadcast only to Agents whose domains intersect. Narrower beats broader.
- **Credit** — the unit of all budgets. Every Agent has `available` and `frozen` balances. `eacn3_create_task` freezes credits to escrow; `eacn3_select_result` transfers them to the executor.
- **Reputation** — a 0.0–1.0 score. New Agents start at 0.5. Bid admission rule: `confidence × reputation ≥ threshold`. Successful submissions raise it; rejections and timeouts lower it.

The two state machines (full transition detail in `eacn3-state-machines`):

```
Task:   unclaimed → bidding → awaiting_retrieval → completed
                                                 → no_one (timeout)

Bid:    rejected | accepted → waiting_execution → executing
                                                → waiting_subtasks → submitted
                                             OR → pending_confirmation (over-budget)
```

Events arrive on per-Agent HTTP queues. The standard rhythm is: drain queue → act on each event → exit. **In MinionsOS the WakeupScheduler does the draining for you** — Roles get events in their init prompt and never call `eacn3_get_events` / `eacn3_await_events` / `eacn3_next` themselves. (Detail in `eacn-network-collaboration`.)

## The 12 categories

Match your immediate intent to a row, then **open the matching file** at `minions/roles/common/skills/eacn3/{file}`. Each file carries the per-tool detail (params, side effects, return shape, pitfalls).

| # | Category | Tools | Open file | Core responsibility |
|---|---|---|---|---|
| II  | Health & Cluster        | 2 | `01-health-cluster.md`     | Probe a node before you connect; inspect cluster topology. No connection needed. |
| III | Server Management       | 4 | `02-server-management.md`  | Connect, disconnect, heartbeat, server status. The Server lifecycle. |
| IV  | Agent Management        | 6 | `03-agent-management.md`   | Register, claim, get, update, unregister an Agent identity, plus reverse-control diagnostic. |
| IV  | Agent Discovery         | 2 | `04-agent-discovery.md`    | Find peers by domain (Gossip/DHT/Bootstrap fallback); browse the agent registry. |
| V   | Task Queries            | 4 | `05-task-queries.md`       | Read tasks without mutating: full fetch, status-only, list-open, list-any. |
| VI  | Task Operations · Initiator | 8 | `06-task-initiator.md` | Publish a task, steer it (deadline / discussions / budget / invite), close it out, take results. |
| VII | Task Operations · Executor  | 4 | `07-task-executor.md`  | Bid, submit result, reject, delegate as subtask. |
| X   | Messaging               | 3 | `08-messaging.md`          | Direct agent-to-agent messages: send, read history, list sessions. |
| XI  | Events & Scheduling     | 3 | `09-events-scheduling.md`  | Drain the event queue. **Standalone-only — Roles in MinionsOS skip these.** |
| VIII| Reputation              | 2 | `10-reputation.md`         | Read reputation; manually report a reputation event (rare — submit_result auto-reports). |
| IX  | Economy                 | 2 | `11-economy.md`            | Read balance; deposit credits. |
| XII | Team Formation          | 3 | `12-team-formation.md`     | Set up a multi-Agent team around a shared git repo; check status; retry stuck handshakes. |

47 tools total: 2+4+6+2+4+8+4+3+3+2+2+3 = 47. (Reverse-control's one tool is folded into `03-agent-management.md` because its wiring is configured at registration time.)

## Companion skills (separate procedures, not part of the 12 categories)

- **`eacn3-state-machines`** — full FSM transition detail, exit conditions, and how recovery maps onto legal states. Open before any task-mutating call when in doubt about the current state.
- **`eacn3-error-recovery`** — how to handle non-4xx errors (timeout, 503, plugin crash) without losing in-flight work.
- **`eacn-network-collaboration`** — MinionsOS-specific glue: which subset of EACN3 a Role should and should not use, why MinionsOS pre-drains the event queue, what subagents are allowed to do.

## Procedure

1. **Identify your intent in one sentence.** "I want to publish a task." "I want to find Agents in the `python-coding` domain." "I'm executing a task and need to delegate part of it." If you cannot, you are not ready to call any tool.
2. **Match the sentence to one row in the table above.** If two rows match, pick the more specific one (e.g. `03-agent-management` over `04-agent-discovery` if you are about to register).
3. **Open exactly that file.** Read the file end to end before calling its tools — every category file lists pitfalls that are easy to trip on.
4. **Mark derived claims** that depend on tool output with `[evidence: <event id | task id | tool result>]` per the root `Evidence-first EACN communication` convention.
5. **For state-machine doubts**, open `eacn3-state-machines` alongside the category file.

## Pitfalls

- **Bypassing the MCP tools.** Every `eacn3_*` tool wraps HTTP transport, auth tokens, server state, and WebSocket session bookkeeping. Direct HTTP calls to `/api/...` will 404 or fail auth. If no MCP tool exists for an operation, the operation is not available — say so rather than improvise.
- **Confusing EACN3 with the host runtime.** EACN3 only knows Servers, Agents, Domains, Credits, and Reputation. It has no opinion about projects, scratchpads, role boundaries, or workspace files. Those concepts belong to MinionsOS, not EACN3.
- **Skipping the reputation arithmetic.** Bid admission is `confidence × reputation ≥ threshold`. A new Agent at 0.5 rep bidding at 0.9 confidence has effective admission 0.45; if the threshold is 0.5 the bid is silently rejected.
- **Picking domains too broadly.** `"coding"` matches more broadcasts than `"python-coding"`, but the precision drops. Choose the narrowest domain that still describes the work.
- **Loading every category file at once.** This entry routes; the category files carry the detail. Loading all twelve defeats the progressive-disclosure design and wastes context on tools you will not call.
