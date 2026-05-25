---
id: domain-lifecycle
kind: domain
domain: lifecycle
auth: [gru]
source: minions/tools/mcp/project_tools.py:1
since: stable
keywords: [project, role, spawn, dismiss, phase, signboard, gru]
related: [mos_spawn_expert, mos_project_set_phase, mos_signboard_set, pitfall-empty-authz]
status: stable
---

# Domain: Lifecycle (Gru only)

Spawning, sleeping, killing, waking projects + roles + signboards.

## Top tools

```bash
lookup.py --id mos_project_create
lookup.py --id mos_spawn_expert      # Read this BEFORE spawning experts.
lookup.py --id mos_project_set_phase
lookup.py --id mos_signboard_set     # callable by all EACN roles
```

## The slug-SUFFIX trap (P0 from project_37596)

```python
mos_spawn_expert(name="theory-normalization")           # ✓ becomes expert-theory-normalization
mos_spawn_expert(name="theory-normalization-expert")    # ✗ slug-SUFFIX → empty authz, every tool denied
```

`name` is the slug ONLY. The launcher prepends `expert-`. See
`pitfall-empty-authz` for the full incident write-up.

## Phase transitions

`mos_project_set_phase(port, phase, reason)` — `reason` becomes the single
source of truth in `meta.json`. Make it a paragraph, not a word. Example:
```
P1 verification consensus-complete: 3 signs raised (ethics + expert-mathematician
+ expert-dl-arch); ethics re-audit eeb5b8c confirms all 7 P1 gates PASS.
Advancing to P2 experiment phase.
```

## Signboard (everyone can raise; Gru consumes)

```python
mos_signboard_set(port, topic, position, rationale, evidence_refs=[...])
mos_signboard_evaluate(port, topic) -> {verdict, support, oppose, neutral}
mos_signboard_consume(port, sign_id)   # Gru only
```
