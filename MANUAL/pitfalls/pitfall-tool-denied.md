---
id: pitfall-tool-denied
kind: pitfall
domain: debug
auth: ['*']
source: minions/tools/mcp/_common.py:217
since: stable
keywords: [denied, allowed, role, authz, whitelist, forbidden]
related: [pitfall-deferred-schema, pitfall-empty-authz, mos_issue_report]
status: stable
---

# pitfall: "tool X is not allowed for role 'Y'"

**Symptom:**
```
tool 'mos_query_gpus' is not allowed for role 'expert-mathematician'
```

## Three possible causes — diagnose before reacting

| Diagnosis | Test | Fix |
|---|---|---|
| Deferred schema | `ToolSearch(query="select:mos_query_gpus")` returns the schema | call after ToolSearch |
| Truly not in your role's whitelist | source check below | route via another role |
| Role's authz is empty (slug-suffix bug) | `ls project_*/issues/issues.jsonl` for an empty-authz P0 | see `pitfall-empty-authz` |

## Source check

Whitelist tables live in `minions/config/__init__.py:_SERVER_AUTHZ`.
```python
# at the role process:
import minions.config as c
print(sorted(c.resolve_whitelist("expert", "main")))
```

If the tool genuinely isn't in your whitelist:
- Don't retry — the harness will keep rejecting.
- Route via DM to a role that DOES have it (`eacn3_send_message`).
- File `mos_issue_report` if the gap looks like a config bug, not policy.

## Project_37596 evidence

- `mos_get_events` denied for ethics — Ethics worked around by reading
  `events/*.jsonl` directly.
- `mos_query_gpus(execution="auto")` rejected — pass `execution="local"`.
