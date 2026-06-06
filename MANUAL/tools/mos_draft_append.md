---
id: mos_draft_append
kind: tool
domain: memory
auth: [gru, expert, ethics]
source: minions/tools/mcp/memory_tools.py:107
since: stable
keywords: [draft, append, node, edge, hypothesis, evidence, plan]
related: [mos_draft_view, mos_draft_annotate, mos_book_promote_verified]
status: stable
---

# mos_draft_append

**One line:** Add nodes / edges to the Draft. IDs auto-generated. `reel_ref` auto-injected from session env.

## Signature
```py
mos_draft_append(
  nodes: list[dict] | None,    # each: { type, text, metadata?, support_status?, evidence_tag? }
  edges: list[dict] | None,    # each: { from_id, to_id, relation }
) -> { node_ids, edge_ids, draft_size }
```

## Node types (conventions)
- `hypothesis` — prediction to be tested
- `plan` — work to do
- `pending_plan` — todo for next-me; uses `metadata.for_role`
- `evidence` — observation grounded in path / sha / event_id
- `result` — settled experiment outcome
- `insight` — durable claim worth promoting to Book
- `method` — reusable procedure

## Style rules
- `text` = one sentence. Long content → `metadata` or Book ingest.
- `evidence_tag` = `"[evidence: branches/main/exp/.../result.json]"`.
- For verified results, set `support_status="verified"`.

## reel_ref auto-injection
When `MINIONS_ROLE_NAME` and `MINIONS_SESSION_ID` are set, every appended
node gets `metadata.reel_ref` pointing back to your raw transcript.

## Real example (project_37596)
```py
mos_draft_append(nodes=[{
  "type": "result",
  "text": "exp-bafd9: c_grok ∝ h FAILS on held-out p=97 (52% MARE)",
  "evidence_tag": "[evidence: branches/main/exp/p3-width-falsifier/result.json]",
  "support_status": "verified",
}])
```
