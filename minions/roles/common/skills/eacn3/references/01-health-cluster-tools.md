# Reference - Health & Cluster Tools

Full per-tool detail. The procedure is in `../01-health-cluster.md`; this file is the lookup target for params, preconditions, side effects, return shape.

## eacn3_health

Checks whether a network node is alive and responding. Call it before `eacn3_connect` when the configured endpoint may be wrong, slow, or down. It proves reachability for one node only; it does not prove that agent registration, task broadcast, or relay delivery will work.

- **Preconditions.** None.
- **Side effects.** None.
- **Returns.** `{endpoint, status: "ok"}`
- **Params.**
  - `endpoint` (`string`, optional) - Node URL to probe; defaults to the configured network endpoint.

## eacn3_cluster_status

Returns the cluster topology for a node, including local node metadata, member nodes, online counts, and seed URLs. Call it after a health or connect failure to find a viable alternate endpoint instead of retrying the same dead node. The response is diagnostic; it does not establish a session.

- **Preconditions.** None.
- **Side effects.** None.
- **Returns.** `{mode, local{node_id, endpoint, domains, status, version, joined_at}, members[], member_count, online_count, seed_nodes[]}`
- **Params.**
  - `endpoint` (`string`, optional) - Node URL to query; defaults to the configured network endpoint.
