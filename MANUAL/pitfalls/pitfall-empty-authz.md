---
id: pitfall-empty-authz
kind: pitfall
domain: debug
auth: [gru]
source: minions/config/__init__.py:517
since: v15.0
keywords: [authz, denied, expert, slug, suffix, prefix, P0, role]
related: [mos_spawn_expert, mos_issue_report, pitfall-tool-denied]
status: stable
---

# pitfall: spawned Expert has empty `server_authz` — every tool denied

**Symptom:**
```
Role 'theory-normalization-expert' has empty server_authz —
every MCP tool denied, event loop unrunnable
```

The role was registered as `theory-normalization-expert` (slug-SUFFIX) but
`_normalise_role_name()` only collapses `expert-<slug>` (slug-PREFIX) to the
`expert` authz key. So `resolve_server_authz()` falls through, logs a warning,
returns `[]`, and `_require_tool_allowed` rejects every call.

## Cause

`mos_spawn_expert(name=...)` was called with the suffix form `<slug>-expert`.
The launcher prepends `expert-` for you — passing a name that already ends
in `-expert` produces double-suffix corruption.

## Recipe

```python
mos_spawn_expert(name="theory-normalization")            # ok: expert-theory-normalization
mos_spawn_expert(name="theory-normalization-expert")     # wrong: every tool denied
```

If you find an existing expert in the broken shape:
```python
mos_dismiss_role(port=<port>, role="theory-normalization-expert", reason="bad slug shape")
mos_spawn_expert(port=<port>, name="theory-normalization", domain=...)
```

## Fallback when the broken role needs to file the issue

`mos_issue_report` is in `_KEEPALIVE_TOOLS + _ISSUE_REPORT_TOOLS` spread into
every authz list — but those universals are spread INTO each list, so if the
list is empty the universals are also lost. The role must write directly to
`project_<port>/issues/issues.jsonl` from a `Bash` tool.

## Source

`minions/config/__init__.py:_SERVER_AUTHZ` table, `_normalise_role_name` at
~line 791, `_require_tool_allowed` in `minions/tools/mcp/_common.py:217-221`.
