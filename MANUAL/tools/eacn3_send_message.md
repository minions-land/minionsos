---
id: eacn3_send_message
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:954
since: stable
keywords: [send, message, task, agent, event]
related: []
status: stable
---

# eacn3_send_message

**One line:** Send a direct agent-to-agent message bypassing the task system

## Full description (from EACN3 plugin)

Send a direct agent-to-agent message bypassing the task system. Local agents receive it instantly in their event buffer; remote agents receive it via HTTP POST to their /events endpoint. Returns {sent, to, from, local}. The recipient sees a 'direct_message' event with payload.from and payload.content. Will fail if the remote agent has no reachable URL or is offline.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
