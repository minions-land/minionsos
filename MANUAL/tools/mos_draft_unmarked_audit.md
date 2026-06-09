---
id: mos_draft_unmarked_audit
kind: tool
domain: memory
auth: [gru, ethics]
source: minions/tools/mcp/memory_tools.py:141
since: stable
keywords: [draft, audit, evidence, unmarked, claims, ethics]
related: [mos_draft_view, mos_draft_annotate, mos_book_audit_walk]
status: stable
---

# mos_draft_unmarked_audit

**One line:** Compute each role's unmarked-claim ratio over Draft nodes.

## Signature
```py
mos_draft_unmarked_audit(threshold: float = 0.2) -> {
  threshold: float,
  per_role_unmarked: {role: float | None},
  flagged_roles: [str],
}
```

## Args
- `threshold` is the advisory ratio above which a role appears in `flagged_roles`.

## Pitfalls
- Advisory only. The tool does not mutate Draft nodes and does not auto-trigger retraction.
- Roles with too few claim-bearing nodes report `None` and are not flagged.

## See also
- domain-memory
