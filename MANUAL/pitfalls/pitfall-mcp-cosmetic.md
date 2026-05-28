---
id: pitfall-mcp-cosmetic
kind: pitfall
domain: debug
auth: ['*']
source: minions/tools/mcp/__init__.py:1
since: stable
keywords: [mcp, server, failed, cosmetic, footer, codex, keepalive]
related: []
status: stable
---

# pitfall: "4 MCP servers failed · /mcp" footer flashes for minutes

**Symptom (every role-*.log in project_37596):** the harness footer shows
`4 MCP servers failed · /mcp` for 30+ seconds at a time.

## Cause

Cosmetic. Usually one of `codex-subagent`, `keepalive`, or `playwright`
is briefly unreachable while the project boots. Your role's own
`minionsos` and `eacn3` are still up.

## Recipe

**Ignore unless YOUR specific tool actually fails.**

If a specific tool fails:
1. Try `ToolSearch(query="select:<tool_name>")` (deferred schema).
2. If still failing, file `mos_issue_report` with severity=P2 and the exact
   tool name + error.
3. Route around: ask another role via `eacn3_send_message` to do the work.

## Don't

- Don't restart your tmux session over a cosmetic MCP failure.
- Don't `claude mcp restart` — you'll lose your event queue position.
