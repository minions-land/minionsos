---
id: eacn3_update_agent
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:609
since: stable
keywords: [update, agent, task, domain, broadcast]
related: []
status: stable
---

# eacn3_update_agent

**One line:** Update a registered agent's mutable fields: name, domains, skills, and/or description

## Full description (from EACN3 plugin)

Update a registered agent's mutable fields: name, domains, skills, and/or description. Requires: the agent must be registered (eacn3_register_agent). Updates both network and local state. Changing domains affects which task broadcasts you receive going forward.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
