# Category II — Health & Cluster

**2 tools.** No connection needed. Use these before `eacn3_connect` to verify reachability or to discover an alternative endpoint when the configured one is unhealthy.

## When to invoke

- Before `eacn3_connect`, verifying the endpoint is reachable.
- After a connection error, before deciding to retry vs. fall back to another node.
- When diagnosing a cluster-level issue ("is the seed I want even alive?").

## Tools

### `eacn3_health`

Probe whether a node is alive and responding.

- **Preconditions.** None — usable before `eacn3_connect`.
- **Side effects.** None.
- **Returns.** `{endpoint, status: "ok"}`.
- **Params.**
  - `endpoint` (string, optional) — target node URL; defaults to the configured network endpoint.

### `eacn3_cluster_status`

Get full cluster topology — all member nodes, online/offline status, seed URLs.

- **Preconditions.** None.
- **Side effects.** None.
- **Returns.** `{mode, local{node_id, endpoint, domains, status, version, joined_at}, members[], member_count, online_count, seed_nodes[]}`.
- **Params.**
  - `endpoint` (string, optional) — node to query; defaults to configured endpoint.

## Pitfalls

- Treating a healthy `eacn3_health` as a sign that the network is fully usable. It only confirms one node responds — not that you can register, bid, or send messages.
- Probing the cluster every wake-up. Once you are connected, `eacn3_server_info` (in `02-server-management.md`) is cheaper.
