---
slug: shelf-mcp
summary: Open when a decision needs structural graph context and the graphify MCP is available. Routes the seven mcp__graphify__* read tools to the right question. Optional — fall back to Book/Draft if graphify is not installed.
layer: scheduling
tools:
version: 3
status: active
references: eacn3-mcp, eacn-network-collaboration
provenance: human
---

# Skill — Graphify MCP (optional structural graph queries)

The graphify MCP is an **optional** per-role graph analysis tool. It is NOT
a system-level dependency — MinionsOS runs fine without it. When available,
it provides structural queries over a role's private workspace artefacts
(built on-demand at `branches/{role}/graphify-out/graph.json`).

The graphify graph answers questions that Draft and Book cannot answer
cheaply: *which concepts cluster together, which nodes are load-bearing,
and what is N hops away from a starting concept.* If your question is
"what does this report claim", read the Book page. If your question is
"where does this report sit in the project's intellectual structure" and
graphify is available, use this skill.

## Availability check

Before using any `mcp__graphify__*` tool, call `mcp__graphify__graph_stats`.
If the tool is not available (ToolSearch returns nothing, or the call errors),
fall back to `mos_book_query` / `mos_draft_query`. Never block on graphify
availability — it is optional infrastructure.

## When to invoke

Open this skill when the next decision benefits from structural context
AND graphify is confirmed available. Typical triggers:

- An Ethics audit choosing audit depth — community spread and god-node
  touch drive the call.
- A Role checking "blast radius" of changing a hypothesis.
- Writer finding hub concepts a section must mention for coherence.

If graphify is unavailable, use Book queries directly.

## Boundary with system memory layers

- **Draft (L1, `mos_draft_*`)** — process memory. System-level, always available.
- **Book (L2, `mos_book_*`)** — compiled knowledge. System-level, always available.
- **Shelf (L3, `mos_shelf_*`)** — Gru cross-project index derived from Book.
  System-level but V3-pending.
- **Graphify (`mcp__graphify__*`)** — optional per-role graph tool. NOT L3 Shelf.

## The seven tools, by question shape

| Tool | The question it answers |
|---|---|
| `mcp__graphify__query_graph` | "Which nodes match these terms?" — entry point. |
| `mcp__graphify__get_node` | "Full attributes for this node id." |
| `mcp__graphify__get_neighbors` | "What sits next to this node?" — one-hop. |
| `mcp__graphify__get_community` | "Who else is in this community?" |
| `mcp__graphify__god_nodes` | "Which nodes carry the most structural weight?" |
| `mcp__graphify__graph_stats` | "Is the graph populated?" — also serves as availability check. |
| `mcp__graphify__shortest_path` | "How are A and B connected?" |

## Procedure

1. Call `graph_stats`. If unavailable or `nodes == 0`, abandon and use Book/Draft.
2. Extract terms from your question. Call `query_graph` with them.
3. From matches, pick one structural follow-up: `get_neighbors` (local),
   `get_community` (cohort), `god_nodes` (centrality), `shortest_path` (path).
4. Record what you used: `[evidence: graphify/<node-id>]` for audit trail.

## Pitfalls

- **Treating graphify as required.** It is optional. Always have a fallback.
- **Treating the graph as authoritative.** It is derived from artefacts. Book is source of truth.
- **Querying for facts.** `get_node` returns structural attributes, not content.
- **Calling every tool.** Form the question first, pick one tool, call it.
