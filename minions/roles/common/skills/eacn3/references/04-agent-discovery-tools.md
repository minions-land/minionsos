# Reference - Agent Discovery Tools

Full per-tool detail. The procedure is in `../04-agent-discovery.md`; this file is the lookup target for params, preconditions, side effects, return shape.

## eacn3_discover_agents

Searches for Agents matching a capability domain through the discovery cascade: Gossip, then DHT, then Bootstrap fallback. Call it before publishing a domain-targeted task when you need evidence that executors exist. The response is intentionally narrow: it returns matching IDs for the requested domain.

- **Preconditions.** `eacn3_connect` has succeeded.
- **Side effects.** None.
- **Returns.** `{domain, agent_ids[]}`
- **Params.**
  - `domain` (`string`, required) - Capability domain to search.
  - `requester_id` (`string`, optional) - Requesting Agent ID for Gossip-priority routing.

## eacn3_list_agents

Browses the registered Agent index directly, with optional domain or Server filters. It is faster than discovery because it does not perform the Gossip/DHT cascade, but an empty result only means the queried registry has no indexed match. Use it for dashboards, pagination, and quick local views.

- **Preconditions.** `eacn3_connect` has succeeded.
- **Side effects.** None.
- **Returns.** `{count, agents[]}`
- **Params.**
  - `domain` (`string`, optional) - Filter by capability domain.
  - `server_id` (`string`, optional) - Filter by Server ID.
  - `limit` (`number`, optional, default `20`) - Page size.
  - `offset` (`number`, optional) - Pagination offset.
