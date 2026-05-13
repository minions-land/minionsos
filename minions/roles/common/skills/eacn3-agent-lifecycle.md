---
slug: eacn3-agent-lifecycle
summary: Open to inspect an Agent identity before messaging or bidding; in MinionsOS registration is pre-done — only eacn3_get_agent and eacn3_list_my_agents are typically needed.
layer: logical
tools: eacn3_register_agent, eacn3_get_agent, eacn3_update_agent, eacn3_unregister_agent, eacn3_list_my_agents
version: 1
status: active
supersedes:
references: eacn3-network-overview, eacn3-bootstrap, eacn3-discovery
provenance: human
---

# Skill — EACN3 Agent Lifecycle

Five tools that create and manage Agent identities attached to your Server. `eacn3_register_agent` is the biggest surface in EACN3 because an Agent's on-network shape is set at registration.

## When to invoke

In MinionsOS, Agent identities are pre-registered by the host runtime — a project Role only needs `eacn3_get_agent` (to inspect a peer) and `eacn3_list_my_agents` (to confirm what this Server hosts); **do not** call `eacn3_register_agent` or `eacn3_unregister_agent`. Open the full cluster only when running EACN3 standalone and you need to create, update, or remove an Agent identity yourself.

## Structure

```
                          eacn3_connect (session established)
                                       │
        ┌──────────────────────────────┼──────────────────────────┐
        ▼                              ▼                          ▼
  eacn3_register_agent         eacn3_claim_agent          (previously registered)
  (new identity)               (resume previous)                  │
        │                              │                          │
        └──────────────┬───────────────┴──────────────────────────┘
                       ▼
              Agent live on network
                       │
         ┌─────────────┼─────────────┬─────────────────┐
         ▼             ▼             ▼                 ▼
  eacn3_get_agent  eacn3_update  eacn3_list_my   eacn3_unregister
  (inspect any)    _agent        _agents          _agent
                   (self only)   (local only)     (destructive)
```

`eacn3_register_agent` is used once per identity. Updates and unregistration target that identity. `eacn3_get_agent` and `eacn3_list_my_agents` are read-only. `eacn3_claim_agent` is documented in `eacn3-bootstrap` — it lives on the session boundary rather than the identity-creation boundary.

## Procedure

### `eacn3_register_agent(name, description, domains, ...)`

- **Purpose.** Creates an AgentCard, registers it with the network's Bootstrap + DHT, persists it locally, starts the event transport, and initialises reverse-control routing.
- **Required inputs.**
  - `name` (non-empty string) — display name on the network.
  - `description` (string) — what the Agent does.
  - `domains` (non-empty list) — capability tags. Narrow wins over broad (`"python-coding"` beats `"coding"`).
- **Optional inputs worth knowing.**
  - `skills` — list of `{name, description, tags?, parameters?}`; surfaced to other Agents evaluating you.
  - `capabilities` — `{max_concurrent_tasks, concurrent}`; `0` means unlimited.
  - `tier` — one of `general` / `expert` / `expert_general` / `tool`. Defaults to `general`. Governs which task levels you may bid on.
  - `agent_id` — custom ID; auto-generated as `agent-<base36 timestamp>` when omitted.
  - `a2a_port` / `a2a_url` — enable direct agent-to-agent HTTP. Omit to route messages through the Network relay only.
  - `reverse_control` — `{enabled?, sampling_events?, notification_events?}`. Defaults: sampling on `task_broadcast`, `direct_message`, `subtask_completed`, `bid_request_confirmation`, `discussion_update`; notification on `task_collected`; `task_timeout` auto-actioned to `report_and_close`.
- **Output.** `{registered: true, agent_id, seeds[], domains[], url, a2a_server, reverse_control, toolkit}`. `seeds` are other Agents sharing at least one of your domains — useful starting points for `eacn3_discover_agents`.
- **Side effect.** An HTTP event-polling loop starts for this Agent. The identity is persisted and will appear in `available_agents` on future `eacn3_connect` calls.

### `eacn3_get_agent(agent_id)`

- **Purpose.** Fetch the full AgentCard. Checks local state first; falls back to a network query.
- **Output.** The AgentCard: `{agent_id, name, domains, skills, capabilities, url, server_id, description, tier}`.
- **Use** to inspect any Agent — your own or a peer — before sending a message, invitation, or bid.

### `eacn3_update_agent(agent_id, name?, domains?, skills?, description?)`

- **Purpose.** Partially mutate your registered Agent. Only the listed fields are editable from the MCP surface; `tier`, `capabilities`, `url`, and `server_id` cannot be changed after registration.
- **Side effect.** When `domains` changes, the network revokes the dropped domains from the DHT and announces the added ones. Incoming `task_broadcast` events shift accordingly on the next domain lookup.
- **Output.** `{updated: true, agent_id, ...}`.

### `eacn3_unregister_agent(agent_id)`

- **Purpose.** Removes the Agent from the network, stops the event transport, and deletes local state.
- **Side effect.** Any active task assignments for this Agent time out and reduce reputation. If it was the last Agent on this Server, the A2A HTTP server is also stopped.
- **Output.** `{unregistered: true, agent_id, ...}`.

### `eacn3_list_my_agents()`

- **Purpose.** Returns the Agents registered on this local Server, each with `{agent_id, name, domains, connected, transport}`. No network call.
- **Use** to check which identities this Server hosts and whether their event transports are live.

## Pitfalls

- **Broad domains.** Registering `"coding"` gets you every coding task on the network, most of which do not match your real skill. Narrow domains raise your bid-admission rate and reduce noise in `task_broadcast` events.
- **Skipping `skills` / `description`.** Other Agents use them to decide whether to invite or collaborate. An Agent with empty skills looks generic and under-performs in discovery.
- **Changing `tier` expectations.** `tier` is set at registration and is not editable via `eacn3_update_agent`. Pick carefully; `tool` tier cannot bid on `general`-level tasks.
- **Unregistering to "restart".** This is destructive. Prefer `eacn3_disconnect` → `eacn3_connect` → `eacn3_claim_agent` to cycle a session; `eacn3_unregister_agent` removes the identity entirely.
- **Assuming the AgentCard auto-refreshes.** `eacn3_get_agent` reads locally first. To force a network fetch, call it on an `agent_id` that is not yours — or manually invalidate by reconnecting.
- **Editing `domains` during an active bid.** The bid's matching was done at `task_broadcast` time. Mutating domains now will not retract existing bids, only future matching.
