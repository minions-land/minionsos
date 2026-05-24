# 04 — Draft (L1 process memory)

> **L2 card.** The Draft is the team's process graph: hypotheses, plans, evidence, support edges. Every EACN role reads + writes; only Noter (and Gru) commit it to the shared branch.
> Top three: `mos_draft_summary` (cold-start), `mos_draft_append` (record), `mos_draft_annotate` (verify/refute).
> File on disk: `branches/shared/draft/draft.json`. Committed by Noter every ~3 min.

---

## mos_draft_summary

**Always your first call after wake.** Gives `pending_plan` nodes left by your previous self before a context reset.

```python
args: {}
returns: {
  recent_nodes: [ { node_id, type, text, author_role, ts } ],
  pending_plan_for_me: [ ... ],          # 🔑 these are todos from your past self
  active_hypotheses: [ ... ],
  recently_verified: [ ... ],
  recently_refuted: [ ... ],
}
```

---

## mos_draft_query

Filter the Draft.

```python
args:
  node_type: str | None      # "hypothesis" | "plan" | "evidence" | "result" | "insight" | ...
  support_status: str | None # "open" | "verified" | "refuted" | "needs_evidence"
  author_role: str | None
  text_contains: str | None
  related_to: str | None     # node_id; returns connected subgraph
  limit: int = 50
returns: { nodes: [...], edges: [...] }
```

**Pattern:** `mos_draft_query(text_contains="kappa_LL")` to find every node touching a topic before adding more.

---

## mos_draft_append

Add nodes / edges. IDs auto-generated if omitted.

```python
args:
  nodes: list[dict] | None   # each: { type, text, metadata?, support_status?, evidence_tag? }
  edges: list[dict] | None   # each: { from_id, to_id, relation }
returns: { node_ids, edge_ids, draft_size }
```

**`reel_ref` auto-injection:** when `MINIONS_ROLE_NAME` and `MINIONS_SESSION_ID` env are set (always true inside a Role), every appended node gets `metadata.reel_ref` pointing to your raw transcript. Auditors can follow back.

**Style:** keep node `text` short (one sentence), put long content in metadata or as a Book ingest. Use `evidence_tag` like `[evidence: branches/shared/exp/exp-abc/result.json]`.

---

## mos_draft_annotate

```python
args:
  node_id: str
  support_status: str | None      # "verified" | "refuted" | "needs_evidence"
  evidence_tag: str | None
  metadata_update: dict | None
returns: { node_id, updated_fields }
```

When you verify or refute a hypothesis, **annotate the existing node** rather than appending a new one. The Book promoter (`mos_book_promote_verified`) only picks up nodes that reached `support_status=verified` and accumulated ≥ 2 `supports` edges.

---

## mos_draft_path

```python
args:
  target_node_id: str
  from_node_id: str | None         # default = root
returns: [ ancestor_node_ids... ]
```

Trace why a node exists. Useful when reviewing whether a hypothesis is still load-bearing.

---

## mos_draft_decay_compute (Noter / Gru)

```python
returns: { candidates: [ { node_id, decay_score, reason } ] }
```
Computes which nodes are stale. Doesn't delete — it's a recommendation. Noter usually pairs this with `mos_book_crystallize_session` or just ignores leaves that decay naturally.

---

## mos_draft_commit_shared (Noter / Gru)

```python
args:
  message: str | None      # default: "noter: draft flush <iso-ts>"
returns: { commit_sha, files_changed }
```

Noter calls this on its 3-min timer. Other roles **don't** call it manually — your `mos_draft_append` already buffers to disk; the next Noter wake commits it.

---

## Pattern: a clean record after running an experiment

```python
exp_id = mos_exp_run(command=..., log_path=...)["exp_id"]
result = mos_exp_get(exp_id)
mos_publish_to_shared(role="coder", src_path=result["bundle"],
                     dst_subpath=f"exp/exp-{exp_id}/result.json",
                     commit_message=f"coder: exp-{exp_id} result")

mos_draft_append(nodes=[{
  "type": "result",
  "text": f"exp-{exp_id}: c_grok ∝ h FAILS at 52% MARE",
  "evidence_tag": f"[evidence: branches/shared/exp/exp-{exp_id}/result.json]",
  "support_status": "verified",
}])
```
