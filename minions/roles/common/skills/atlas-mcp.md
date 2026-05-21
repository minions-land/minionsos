---
slug: atlas-mcp
summary: Open when a decision needs structural context across the project's compiled knowledge — community membership, god-node hubs, neighbour reach. Routes the seven mcp__graphify__* read tools to the right question.
layer: scheduling
tools:
version: 1
status: active
references: eacn3-mcp, eacn-network-collaboration
provenance: human
---

# Skill — Atlas MCP Manual (L3 structural index)

The Atlas is the project's L3 structural index over its compiled knowledge. It is **not** another store you write into — it is a derived view that Noter rebuilds on a timer (`noter_wait.py` shells out `mcp-servers/graphify/extract.py`) over `branches/shared/book/` and adjacent shared artefacts, then publishes to `branches/shared/atlas/atlas.json`. The `mcp__graphify__*` MCP tools are read-only queries against that snapshot.

The Atlas answers questions that L1 (Draft) and L2 (Book) cannot answer cheaply: *which concepts cluster together, which nodes are load-bearing for the rest of the graph, and what is N hops away from a starting concept.* If your question is "what does this one report claim", read the Book page. If your question is "where does this report sit in the project's intellectual structure", open the Atlas.

## When to invoke

Open this skill when the next decision benefits from structural context the local artefact cannot supply on its own. Typical triggers:

- An **Ethics audit** must choose audit depth for a new report — community spread and god-node touch drive the call (see `roles/ethics/SYSTEM.md` for the canonical heuristic table).
- A Role about to act on a hypothesis wants to know which other claims that hypothesis underwrites (a "blast radius" question) before changing it.
- Coder is deciding whether an experiment result is local cleanup or a project-shifting finding — community count and god-node delta tell that.
- Writer wants to find the few hub concepts a section must mention to be coherent with the rest of the project.

If your question is fact-shaped ("what did exp-042 report?", "which paper does Draft node H-007 cite?"), do **not** open the Atlas; query the Draft (`mos_draft_*`) or read the source page directly.

## Boundary with Draft and Book

- **Draft (L1, `mos_draft_*`)** — process memory: hypotheses, plans, decisions, agent state. Mutated continuously.
- **Book (L2, `mos_book_*` / `branches/shared/book/`)** — compiled knowledge: one curated page per ingested artefact. Mutated by Noter on ingest.
- **Atlas (L3, `mcp__graphify__*`)** — derived structural index over L2 (and L1 nodes that survived ingest). Read-only from a Role's perspective; rebuilt by Noter periodically.

Writes to L3 happen by writing to L2 and waiting for Noter's next extract cycle, never by calling a graphify tool. The Atlas trails the Book; do not treat absence of a node as evidence the concept is missing — it may not have been re-extracted yet.

## The seven tools, by question shape

| Tool | The question it answers |
|---|---|
| `mcp__graphify__query_graph` | "Which existing nodes match these terms?" — entry point. Returns matches plus their community labels. |
| `mcp__graphify__get_node` | "Tell me everything about this one node id." — full attributes for a node already in hand. |
| `mcp__graphify__get_neighbors` | "What sits next to this node?" — one-hop neighbourhood, optionally filtered by edge type. |
| `mcp__graphify__get_community` | "Who else is in this community?" — cluster membership for grouping or coverage questions. |
| `mcp__graphify__god_nodes` | "Which nodes carry the most structural weight?" — top high-degree hubs. Project-wide load-bearing concepts. |
| `mcp__graphify__graph_stats` | "Is the Atlas big enough to trust?" — node / edge / community counts. Use to decide whether to fall back. |
| `mcp__graphify__shortest_path` | "How are A and B connected?" — chain of intermediate nodes between two ids. |

The two-step starter: `query_graph(terms)` to find candidate node ids, then `get_neighbors` / `get_community` / `shortest_path` on the ids that came back. Skip `query_graph` only when a node id is already in your hand (e.g. from the Book page or a prior call).

## Procedure (the canonical flow)

1. State the question in one sentence. If it is fact-shaped, abandon this skill and use Draft / Book.
2. Call `graph_stats`. If `nodes == 0` (stub Atlas — fresh project, no extract yet), fall back: read the report or Book page directly, do not block. Atlas absence is never a hard error.
3. Extract terms from your question (title, abstract, key nouns). Call `query_graph` with them.
4. From the matches, pick the structural question that matters and call exactly one of: `get_neighbors` (local impact), `get_community` (cohort), `god_nodes` (centrality), `shortest_path` (relation between two specific nodes).
5. Use the answer to inform the decision; record what you used in your output (`[evidence: atlas/<community-id>]` or similar) so an Ethics audit can replay your reasoning.

## Pitfalls

- **Blocking on Atlas availability.** A stub or empty graph is normal in a fresh project and during the gap between writes and Noter's next extract. Always have a non-Atlas fallback path; never refuse to act because the Atlas is not ready.
- **Treating the Atlas as authoritative.** It is derived. The Book is the source of truth for content; the Atlas is structural metadata. If they disagree, the Book wins and the Atlas is stale until the next extract.
- **Querying the Atlas to look up a fact.** `get_node` returns structural attributes (id, label, community, degree), not the underlying claim. For content, follow the node back to its Book page.
- **Loading every tool reflexively.** Each `mcp__graphify__*` call costs a round trip and tokens. Form the structural question first, pick one tool, call it.
- **Writing to the Atlas.** There is no write path. If you want a concept reflected in the Atlas, write the artefact into the Book and wait for the next Noter extract.
