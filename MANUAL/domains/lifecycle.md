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
lookup.py --id mos_project_revive
lookup.py --id mos_spawn_expert      # Read this BEFORE spawning experts.
lookup.py --id mos_project_set_phase
lookup.py --id mos_signboard_set     # callable by all EACN roles
```

## Project lifecycle rule

Create is only for a new project. Once a port has any project tree,
per-project bare repo, branch, worktree, backend, role metadata, or tmux
session, use revive/repair/role tools instead:

```bash
lookup.py --id mos_project_revive
./mos doctor
./mos project repair <port>
```

Do not repair lifecycle state by editing `projects.json`, deleting git
refs, or calling `minions.lifecycle.*` from ad-hoc Python.

## The slug rule

```python
mos_spawn_expert(name="theory-normalization")           # ok: becomes expert-theory-normalization
mos_spawn_expert(name="theory-normalization-expert")    # wrong: empty authz, every tool denied
```

`name` is the slug ONLY. The launcher prepends `expert-`. See
`pitfall-empty-authz` for the full recovery recipe.

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
