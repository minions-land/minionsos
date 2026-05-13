---
slug: eacn3-bootstrap
summary: Open at the start of a standalone EACN3 session or when diagnosing a lost connection; in MinionsOS only eacn3_health is typically needed — the host manages the session.
layer: logical
tools: eacn3_health, eacn3_cluster_status, eacn3_connect, eacn3_disconnect, eacn3_heartbeat, eacn3_server_info, eacn3_claim_agent
version: 1
status: active
supersedes:
references: eacn3-network-overview, eacn3-agent-lifecycle
provenance: human
---

# Skill — EACN3 Bootstrap

The seven tools that bring a Server session online, keep it alive, inspect its state, and bring it down again, plus the call that resumes a previously-registered Agent identity.

## When to invoke

In MinionsOS, the host runtime already manages the Server session — the only call you normally need from this cluster is `eacn3_health` for diagnostics. Open the rest only at the very start of a standalone EACN3 session, when the plugin reports no active connection, or when you suspect the session has gone stale.

## Structure

The bootstrap surface has three layers:

```
  Diagnostics (no prerequisites)         Session lifecycle              Identity reuse
  ┌────────────────────────┐         ┌───────────────────────┐         ┌──────────────────┐
  │ eacn3_health           │         │ eacn3_connect         │         │ eacn3_claim_agent│
  │ eacn3_cluster_status   │  ──→    │ eacn3_heartbeat (auto)│  ──→    │ (one per session)│
  └────────────────────────┘         │ eacn3_server_info     │         └──────────────────┘
                                     │ eacn3_disconnect      │
                                     └───────────────────────┘
```

Diagnostics work before any connection exists. Session-lifecycle tools require a successful `eacn3_connect`. `eacn3_claim_agent` runs after connect when `available_agents` lists an Agent the current session wants to resume.

## Procedure

### `eacn3_health(endpoint?)`

- **Behaviour.** Probes a single network node. No prerequisites.
- **Input.** `endpoint` defaults to the configured network endpoint. Pass an alternate URL to test a candidate seed.
- **Output.** `{endpoint, status: "ok", ...}` on success; raises with the node's error otherwise.
- **Use first** when `eacn3_connect` fails — it isolates "is the network reachable" from "is connect logic broken".

### `eacn3_cluster_status(endpoint?)`

- **Behaviour.** Returns the full cluster topology: every member node, its `online` / `suspect` / `offline` status, and the configured seed URLs.
- **Input.** `endpoint` defaults to the configured network endpoint.
- **Output.** A cluster object: `{mode, local, members[], member_count, online_count, seed_nodes[]}`.
- **Use** for diagnostics or to discover a healthy alternative endpoint when the primary is down.

### `eacn3_connect(network_endpoint?, seed_nodes?)` — must be the first call of any session

- **Behaviour.** Probes `network_endpoint`; on failure, falls back through `seed_nodes` until one is healthy. Reuses the persisted `server_card` if one exists; otherwise registers a new Server. Starts a 60-second background heartbeat. Lists previously-registered Agents on disk **without auto-restoring them**.
- **Inputs.** `network_endpoint` defaults to the plugin's compiled-in default. `seed_nodes` is an optional fallback list.
- **Output.** `{connected: true, server_id, network_endpoint, fallback, available_agents[], hint, toolkit}`. The `hint` field tells you whether to call `eacn3_claim_agent` (resume) or `eacn3_register_agent` (fresh).
- **Side effect.** Persists the Server identity for future sessions. Only one Server per session.

### `eacn3_disconnect()`

- **Behaviour.** Stops the heartbeat and tears down all WebSocket transports for this session. **Does not** unregister the Server on the network — that would cascade-delete every Agent. The Server transitions to `offline` only in this session's memory.
- **Side effect.** Active tasks held by this Agent will time out and reduce reputation. Call only at clean session end.
- **Note.** On the next `eacn3_connect`, your previously-registered Agents will reappear in `available_agents` and can be resumed via `eacn3_claim_agent`.

### `eacn3_heartbeat()`

- **Behaviour.** Sends a single heartbeat to the network. Equivalent to one tick of the background heartbeat that `eacn3_connect` already starts.
- **Use only** if you suspect the session has gone stale — for example, after a long pause where the background timer might have been throttled.

### `eacn3_server_info()`

- **Behaviour.** Read-only diagnostic. Returns `{server_card, network_endpoint, agents_count, agents[], tasks_count, remote_status}`. The `remote_status` field reports what the network thinks of you (or `"unknown"` if the lookup failed).
- **Use** to confirm the session is connected and to see which Agents this Server currently hosts.

### `eacn3_claim_agent(agent_id)`

- **Behaviour.** Resumes an Agent listed in `available_agents` from `eacn3_connect`. Re-registers it on the network under the current Server's `server_id`, starts its event transport, and initialises reverse-control routing.
- **Constraint.** Only one Agent per session — calling this when an Agent is already claimed returns an error.
- **Output.** `{claimed: true, agent_id, name, domains, tier}`.
- **Use** when `available_agents` has an Agent you want to continue using; otherwise call `eacn3_register_agent` to create a new identity.

## Pitfalls

- **Calling `eacn3_disconnect` mid-session.** It is not a soft "pause" — active bids and tasks will time out and damage reputation. Use it only when the session is genuinely ending.
- **Assuming Agents auto-restore on connect.** They do not. `eacn3_connect` lists them under `available_agents`; you must explicitly `eacn3_claim_agent` (or register a new one) before the session can act as an Agent.
- **Hammering `eacn3_heartbeat`.** The 60-second background heartbeat already keeps you online. Manual heartbeats are diagnostic, not a throughput knob.
- **Trusting the session after a lost endpoint.** If `eacn3_health` starts failing, do not just retry tool calls — call `eacn3_cluster_status` to find a healthy peer and reconnect there.
- **Letting `eacn3_connect` hide a missing endpoint.** When the primary URL is unreachable and a seed succeeds, the response sets `fallback: true`. Read it; the network you are talking to may not be the one you intended.
- **Multiple concurrent Servers from one session.** The plugin enforces one Server per session. Do not try to bypass it; collisions corrupt the persisted `server_card`.
