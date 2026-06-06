---
id: mos_spawn_expert
kind: tool
domain: lifecycle
auth: [gru]
source: minions/tools/mcp/spawn_tools.py:60
since: stable
keywords: [spawn, expert, role, slug, domain, agent]
related: [mos_spawn_role, mos_dismiss_role, pitfall-empty-authz]
status: stable
---

# mos_spawn_expert

**One line:** Spawn a domain Expert role. **`name` is the SLUG only — never `<slug>-expert`.**

## Signature
```py
mos_spawn_expert(
  port: int,
  name: str,                    # slug ONLY (e.g. "theory-normalization")
  domain: str | None,           # path to minions/domains/*.md pack
  config: dict | None,
) -> { role, session_name, agent_id, registered_role_name }
```

## The slug rule (P0 from project_37596)

```py
mos_spawn_expert(name="theory-normalization")           # ✓ → expert-theory-normalization
mos_spawn_expert(name="theory-normalization-expert")    # ✗ slug-SUFFIX → empty authz
```

The launcher prepends `expert-` for you. Passing a name that already ends in
`-expert` produces a double-suffix that `_normalise_role_name()` doesn't
collapse → empty `server_authz` → every MCP tool denied → P0 incident.

If you find an Expert in the broken shape:
```py
mos_dismiss_role(port=37596, role="theory-normalization-expert", reason="bad slug")
mos_spawn_expert(port=37596, name="theory-normalization", domain=...)
```

## See also
- pitfall-empty-authz
- mos_dismiss_role
- domain-lifecycle
