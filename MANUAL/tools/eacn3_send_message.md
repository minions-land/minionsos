---
id: eacn3_send_message
kind: tool
domain: eacn3
auth: [gru, expert, ethics]
source: mcp-servers/eacn3/plugin/index.ts:954
since: stable
keywords: [send, message, task, agent, event]
related: [mos_await_events, mos_get_events, eacn3_get_agent, eacn3_list_agents]
status: stable
---

# eacn3_send_message

**One line:** Send a direct EACN3 message to another agent without creating a task.

## Signature
```py
eacn3_send_message(args={
  "agent_id": str,
  "content": str,
  "sender_id": str | None,
}) -> {"ok": bool, "sent": bool, "to": str, "from": str, "local": bool}
```

## Args
- `agent_id`: recipient EACN agent id.
- `content`: message body. Include evidence markers for substantive claims.
- `sender_id`: optional; normally let EACN3 resolve it from the caller.

## Behaviour
- Local recipients receive a `direct_message` event immediately.
- Remote recipients are contacted through their registered callback URL.
- Returns whether the send succeeded and whether it was local.

## Use
```py
eacn3_send_message({
    "agent_id": "expert-theory",
    "content": "[evidence: branches/main/handoffs/x.md] Please review this claim.",
})
```

## Don't
- Don't use this to publish artifacts; publish through `mos_publish_to_shared`.
- Don't use this when the work needs bidding/result accounting; use EACN3 task
  tools from an EACN-visible Role.
