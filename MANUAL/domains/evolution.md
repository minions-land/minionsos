---
id: domain-evolution
kind: domain
domain: evolution
auth: [gru]
source: minions/tools/mcp/role_evolution_tools.py:1
since: stable
keywords: [split, merge, dismiss, role, evolution, governance]
related: [mos_role_evolve_evaluate, mos_role_split, mos_role_merge, mos_role_evolve_dismiss]
status: stable
---

# Domain: Role evolution (Gru only)

Roles aren't fixed in number. Gru can SPLIT a strained role, MERGE two
converging roles, or DISMISS a starved role. **Evidence-gated, audit-logged,
recommend-only by default.**

## Top tools

```bash
lookup.py --id mos_role_evolve_evaluate    # read-only; recommend
lookup.py --id mos_role_split              # apply SPLIT (evidence_refs required)
lookup.py --id mos_role_merge              # apply MERGE (convergence-only)
lookup.py --id mos_role_evolve_dismiss     # apply DISMISS (starvation-only)
```

## Triggers (defaults from `gru.yaml`)

| Action | Trigger |
|---|---|
| SPLIT | ≥5 attributable failures in window, ≥2 labeled subdomain clusters, each ≥3 large |
| MERGE | active-role pair with Jaccard(artifact basenames) + dir-prefix overlap ≥0.75 |
| DISMISS | role active ≥6h with ≤1 task in window |

## Cooldowns

SPLIT: 12 h. MERGE / DISMISS: 6 h. Default `gru.yaml: role_evolution_auto_apply: false`
— operator inspects the JSONL log and applies manually.

## Audit trail

`branches/shared/governance/role_evolution.jsonl` — every recommendation and
every apply event writes one line.
