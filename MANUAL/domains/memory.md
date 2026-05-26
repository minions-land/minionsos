---
id: domain-memory
kind: domain
domain: memory
auth: ['*']
source: minions/tools/mcp/memory_tools.py:1
since: stable
keywords: [draft, book, reel, memory, hot, hypothesis, status, ratify, open_question, dead_end]
related: [mos_draft_summary, mos_book_query, mos_book_hot_get, mos_reel_get, mos_book_ratify, mos_book_open_question, mos_book_dead_end]
status: stable
---

# Domain: Memory (Draft / Book / Shelf / Reel)

Four layers, top-down:

| Layer | What | Who writes | File |
|---|---|---|---|
| **L0 Reel** | flat index → native Claude/Codex session jsonl | hook (auto) | `branches/<role>/reel-index.jsonl` |
| **L1 Draft** | process graph: hypotheses, plans, evidence, support edges | every EACN role | `branches/shared/draft/draft.json` |
| **L2 Book** | durable compiled knowledge, citation-shaped | Noter only | `branches/shared/book/sources/*.md` |
| **L3 Graphify** | per-role structural graph (optional) | role builds on demand | `branches/<role>/graphify-out/graph.json` |

## Top tools

```bash
lookup.py --id mos_draft_summary       # FIRST call after wake
lookup.py --id mos_draft_append        # record a hypothesis / result
lookup.py --id mos_draft_annotate      # mark verified / refuted
lookup.py --id mos_book_query          # find a Book page
lookup.py --id mos_book_hot_get        # the rolling cache
lookup.py --id mos_reel_get            # drill into a subagent trace
```

## Rules

- `mos_draft_summary` BEFORE `mos_await_events`. The summary surfaces
  `pending_plan` nodes left by your previous self before context reset.
- Draft `text` field: one sentence. Long content goes in `metadata` or a Book ingest.
- Use `evidence_tag: "[evidence: <path|sha|event_id>]"` on every result node.
- Book pages with no inbound `[[wikilink]]` keep flagging `ORPHAN_PAGE`.
  Either link via `mos_book_save_synthesis` or accept the lint warning.
- `mos_book_promote_verified` only picks Draft nodes (insight / method / result)
  with `support_status=verified` AND ≥ 2 `supports` edges AND age ≥ 7 days.

## Noter contract (L1 Draft)

Noter's **primary mode** is `mos_draft_annotate` (update another role's node) and
`mos_draft_append(edges=[...])` (close motif patterns across roles).

Creating new first-class nodes (`mos_draft_append(nodes=[...])`) is **rare** and
requires `metadata.motif_kind` set to one of `triangle`, `star`, `cycle`, or `close`.
`motif_kind="none"` signals the node should have been an annotate call instead.

Motif kinds:
- **triangle** — A→B→C→A closing loop (e.g. theory→experiment→result→theory)
- **star** — hub with ≥3 independent supports from different roles
- **cycle** — reasoning chain that closes back on a decision
- **close** — explicitly resolves a `PENDING-*` plan node

`_is_motif_authorized(node)` returns True when `metadata.ratified_by=="ethics"` OR
`motif_kind != "none"`. Used as a gate in `mos_book_ratify` (TODO: `[[mos_book_ratify]]`).

ANTI-PATTERN: do not mirror another role's node with `author_role="noter"`. Use
`mos_draft_annotate` to update their node's `support_status` / `evidence_tag` / `confidence`.

## Project_37596 lessons

- Subagents producing 18 contradiction verdicts in one shot wrote boilerplate
  rationales. Always `mos_reel_get(ref)` before accepting bulk verdicts.
  See `pitfall-subagent-boilerplate`.
- `mos_book_hot_update` schema is deferred. Run `ToolSearch(query="select:mos_book_hot_update")` once per session.

## Permission matrix

Who can read and write each memory layer:

| Layer | Self | Other Role | Noter | Ethics | Gru |
|---|---|---|---|---|---|
| **Reel-Index (L0)** | RW | — | — | R (cross-role) | R (cross-role) |
| **Draft (L1)** | RW own nodes | R (all nodes) | RW nodes + edge writes + status annotates | R + status writes (ratify) | R |
| **Book (L2)** | R | R | W (sole writer) | R + ratify (`mos_book_ratify`) | R |
| **Shelf (L3, cross-proj)** | — | — | — | — | RW |

### Prose clarifications

- **Reel-Index reads beyond self** are restricted to Ethics and Gru. Peer roles (Coder reading Expert reel) are denied. Noter has no reel access at all — it observes the project through `events/*.jsonl` and the Draft/Book surfaces.
- **Draft** is fully readable team-wide. Any EACN-visible role appends nodes and edges for their own work via `mos_draft_append`. Notable write distinctions: Noter writes `pending_plan` nodes and graph edges as first-class operations; Ethics writes `support_status` fields (ratification/refutation) on any node via `mos_draft_annotate`.
- **Book** is single-writer: only Noter ingests pages and saves syntheses. Ethics gates knowledge promotion via `mos_book_ratify` (Stream 3). All other roles read via `mos_book_query` / `mos_book_hot_get`.
- **Shelf** is cross-project Gru territory. It is out of scope for single-project memory operations.
- **Wake-up reading habit (not an authz boundary):** Roles SHOULD prefer Book over Draft at wake-up — Book is the progressive-disclosure distillation of Draft conclusions. But the authz rule is "Book is readable by all"; it is not enforced as a required read order.

## Full surface

```bash
lookup.py --domain memory
```
