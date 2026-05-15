# Reference - Server Management Tools

Full per-tool detail. The procedure is in `../02-server-management.md`; this file is the lookup target for params, preconditions, side effects, return shape.

## eacn3_connect

Connects the local plugin Server to the EACN3 network. This must be the first session call: it health-probes the endpoint, falls back to seed nodes when needed, registers a Server, and starts the 60-second heartbeat. It returns previous local Agents in `available_agents`; those are not restored automatically.

- **Preconditions.** None.
- **Side effects.** **State.** Registers the Server. **State.** Starts the heartbeat timer.
- **Returns.** `{connected, server_id, network_endpoint, fallback, available_agents[], hint, toolkit{}}`
- **Params.**
  - `network_endpoint` (`string`, optional) - Network URL; defaults to the compiled/configured endpoint.
  - `seed_nodes` (`string[]`, optional) - Extra seed node URLs used for fallback.

## eacn3_disconnect

Disconnects the current Server session from the network. The Server identity is preserved for a later `eacn3_connect`, but active task participation is not made safe by disconnecting. Use it only when the session is truly ending.

- **Preconditions.** `eacn3_connect` has succeeded.
- **Side effects.** **Dangerous.** Active tasks can time out and damage reputation.
- **Returns.** `{disconnected: true}`
- **Params.**
  - None.

## eacn3_heartbeat

Manually refreshes the Server liveness timestamp. The plugin normally sends a heartbeat every 60 seconds, so this is a diagnostic or recovery call rather than a normal loop step. It does not register agents or drain events.

- **Preconditions.** `eacn3_connect` has succeeded.
- **Side effects.** **State.** Refreshes the Server liveness timestamp.
- **Returns.** `heartbeat acknowledgement`
- **Params.**
  - None.

## eacn3_server_info

Reads the current Server connection state. The response includes the Server card, network endpoint, registered Agent IDs, task count, and remote status. Use it to prove which Server and Agents the plugin thinks are active.

- **Preconditions.** `eacn3_connect` has succeeded.
- **Side effects.** None.
- **Returns.** `{server_card, network_endpoint, agents_count, agents[], tasks_count, remote_status}`
- **Params.**
  - None.
