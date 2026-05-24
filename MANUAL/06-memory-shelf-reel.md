# 06 — Shelf (L3 structural index) + Reel (L0 raw transcripts)

> **L2 card.** Two layers, opposite ends of fidelity.
> - **Shelf** = compressed graph view, structural search across the whole project.
> - **Reel** = full-fidelity raw transcripts of every subagent / codex call.
> Top three: `mos_shelf_query`, `mos_reel_get`, `mos_reel_window`.

---

## mos_shelf_register (Gru)

Build the per-project shelf graph from Book + handoffs + draft.

```python
args: port: int
returns: { node_count, edge_count, file_path }
```

Per project: `branches/shared/shelf/shelf.json`. Cross-project (Gru-only): `~/.minionsos/shelf.json` aggregated from all `_register` calls.

**Pitfall (project_37596 / role-noter):** "shelf_graph consistently fails to rebuild (extract exit 1)". When this happens, file `mos_issue_report` — don't loop on it.

---

## mos_shelf_query (everyone)

```python
args:
  text: str
  max_results: int = 10
returns: { hits: [ { node_id, type, project, slug, score, neighbors } ] }
```

Structural search across the whole project (or, for Gru, the host). Differs from `mos_book_query` in that it walks the typed graph (claim ↔ source ↔ method) rather than text-matching pages.

---

## mos_shelf_shared_concepts (everyone)

```python
args:
  project_a: int
  project_b: int               # Gru only — cross-project
returns: { shared_concepts: [...], divergent: [...] }
```

For Gru's bridge work; in single-project mode, pass the same port twice to find internal echoes.

---

## mos_reel_get

Drill into the raw transcript of a specific subagent / Codex call.

```python
args:
  ref: str    # "<role>/<session_id>/<task_id>"
returns: {
  transcript_path: str,
  task_id: str,
  invoked_at: str,
  tool_name: str,             # "Agent" | "Task" | "mcp__codex-subagent__codex"
  prompt: str,
  output: str,                # full verbatim output
  events: [ ... ],            # sub-tool calls inside the subagent
}
```

**Where `ref` comes from.** Every Draft node + Book page added by a session-active role carries `metadata.reel_ref`. Just copy it.

**Example (project_37596):** Ethics subagent stamped boilerplate verdicts. Ethics ran `mos_reel_get(ref="ethics/sess-abc/contradict-walk-task-xyz")` to confirm the subagent had only read 2 of 18 contradictions before deciding.

**Permission boundary.** Each role can read its own reel. Gru can read any role's reel. Noter cannot read reel at all.

---

## mos_reel_window

Tail / preview around a single transcript span.

```python
args:
  ref: str
  span: int = 5             # number of events on either side of focus
returns: list of event dicts with truncated content
```

Use this when the full transcript is too big to paste into context. `span=10` is comfortable for most audits.

---

## When to use which

| Question | Reach for |
|---|---|
| Did this subagent actually do the work? | `mos_reel_get` then grep |
| What did the team converge on about X? | `mos_book_query` |
| What process led to that conclusion? | `mos_draft_query(text_contains=...)` then `mos_draft_path` |
| Are projects A and B duplicating effort? | `mos_shelf_shared_concepts(a, b)` (Gru) |
| Quick structural search this project | `mos_shelf_query` |
