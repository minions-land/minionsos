---
id: pitfall-deferred-schema
kind: pitfall
domain: debug
auth: ['*']
source: minions/tools/mcp/_common.py:1
since: stable
keywords: [tool, not, found, deferred, schema, ToolSearch, denied, eacn3]
related: [mos_await_events, eacn3_send_message, pitfall-empty-authz]
status: stable
---

# pitfall: tool reports "No such tool available" but it's whitelisted

**Symptom (project_37596 / role-coder + role-ethics + role-noter logs):**
```
●The eacn3 tools are not in the deferred-tools index of THIS session
●Error: ... eacn3_send_message — No such tool available
```
Coder spent ~15 min thrashing. Ethics filed an issue. Noter looped on `mos_book_hot_update`.

## Cause

The tool IS in your whitelist, but its **schema is deferred** in this session.
Calling it without first loading the schema fails with "No such tool".

## Recipe

```bash
ToolSearch(query="select:eacn3_send_message")    # exact tool name in select:
```

After ToolSearch returns the schema, the call works. Do this **once per session**
for any deferred tool you intend to use.

## How to tell deferred-vs-actually-denied

| ToolSearch returns the schema | Just deferred — call now works |
|---|---|
| ToolSearch returns nothing for that name | Truly not in your whitelist; file `mos_issue_report` |

## Tools known to be deferred in many sessions (project_37596 evidence)

- `eacn3_send_message`, `eacn3_create_task`, `eacn3_submit_bid`, `eacn3_submit_result`
- `mos_book_hot_update`
- `mos_publish_to_shared` (sometimes)

## Don't

- Don't retry the same call hoping the harness will load the schema. It won't.
- Don't fall back to writing JSON files manually with `Bash` — that bypasses the
  flock + audit trail (project_37596 / expert-dl-arch did this and ended up with
  inconsistent message state).
