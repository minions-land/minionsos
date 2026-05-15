# Category II — Health & Cluster

Open this when the problem is below the EACN3 session layer: the node may be down, the configured endpoint may be stale, or a seed may be healthier than the primary. These tools do not connect you, authenticate you, or prove task traffic will work. They answer one narrow question: where can the next `eacn3_connect` safely point?

## When to invoke

- Before a manual `eacn3_connect` against an endpoint you have not used in this session.
- After a connect failure, to decide whether to retry the same endpoint or switch to a seed.
- When a cluster outage is suspected and you need member counts, online nodes, or seed URLs.
- When a role reports "network down" but you need evidence before changing configuration.
- If you are already connected and only need session state, stop here; open `02-server-management.md` instead.

## The typical flow

1. Decide whether you are testing one URL or the topology. Call `eacn3_health` for one endpoint; call `eacn3_cluster_status` when you need alternatives. The field that drives the next step is `status` for health and `online_count` / `seed_nodes` for topology.
2. If `eacn3_health` returns `status: "ok"`, keep the endpoint and move to `eacn3_connect` in `02-server-management.md`. Do not keep probing just because the cluster has other nodes.
3. If health fails, call `eacn3_cluster_status` against the same endpoint or a configured seed. Pick a member whose `status` is online and whose `endpoint` is reachable.
4. If `online_count` is zero or no member endpoint responds, treat this as a network incident, not an Agent problem. Do not register, claim, bid, or drain events until a node is alive.
5. Exit when you have either a specific endpoint for `eacn3_connect` or a clear "no healthy node" diagnosis.

## Decisions you'll face

- **Health or topology first?** Use `eacn3_health` for a single suspect URL; use `eacn3_cluster_status` when a failed primary needs fallback. Base this on whether you already have a candidate endpoint.
- **Retry or switch?** Retry once for transient transport errors. Switch endpoints when `cluster_status.members[]` shows another online node.
- **Is "ok" enough?** For connection routing, yes. For task health, no; task behavior belongs to Server, Agent, and Task procedures.
- **Which endpoint should win?** Prefer an online member over a seed-only URL when both are available, because the member record carries current status.

## Pitfalls

- Treating `status: "ok"` as a full network readiness check. It only proves one node answered a health probe; escrow, discovery, and event delivery can still fail later.
- Re-running topology checks on every wake. Once connected, the session heartbeat and `eacn3_server_info` are the cheaper evidence.
- Calling `eacn3_connect` repeatedly after a health failure without changing endpoints. That just repeats the same bad assumption with more noise.
- Diagnosing Agent registration from cluster status. Cluster tools know nodes, not AgentCards.
- Using seed URLs as permanent configuration without checking `members[]`. Seeds are fallback anchors, not always the best active endpoint.

## Worked example

```text
eacn3_health({
  endpoint: "http://eacn-primary.local:8080"
})
→ error or no ok status

eacn3_cluster_status({
  endpoint: "http://eacn-seed.local:8080"
})
→ online_count: 2, members: [{endpoint: "http://eacn-node-2.local:8080", status: "online"}]

eacn3_health({
  endpoint: "http://eacn-node-2.local:8080"
})
→ status: "ok"; use this endpoint for eacn3_connect
```

## Tool reference

For full per-tool detail (parameters, preconditions, side effects, return shape), open `references/01-health-cluster-tools.md`.
