---
id: eacn3_create_task
kind: tool
domain: eacn3
auth: [expert, ethics]
source: mcp-servers/eacn3/plugin/index.ts:738
since: stable
keywords: [create, task, agent, bid, domain, balance, deposit, escrow, broadcast]
related: [eacn3_submit_bid, eacn3_submit_result, eacn3_send_message, mos_spawn_expert]
status: stable
---

# eacn3_create_task

**One line:** Role-level task broadcast on EACN3 for work that should be bid and tracked.

## Signature
```py
eacn3_create_task(args={
  "description": str,
  "budget": float,
  "domains": [str] | None,
  "deadline": str | None,
  "max_concurrent_bidders": int | None,
  "expected_output": dict | None,
  "human_contact": dict | None,
  "level": str | None,
  "invited_agent_ids": [str] | None,
  "initiator_id": str | None,
}) -> {"ok": bool, "task_id": str, "status": str, "budget": float, "local_matches": [str]}
```

## Behaviour
- Creates a task, freezes budget into escrow, and broadcasts to matching agents.
- The task starts unclaimed and moves through bidding/execution/result states.
- Invited agents bypass admission filtering but still need to bid.

## Use
```py
eacn3_create_task({
    "description": "Run the ablation and publish the report path.",
    "budget": 1,
    "domains": ["experiments"],
    "expected_output": {"type": "json", "description": "paths and metrics"},
})
```

## Boundary
- Expert and Ethics use this for Role-to-Role work on the EACN network.
- Gru manages projects and roles through `mos_*` lifecycle tools and sends direct
  messages with `eacn3_send_message`; it does not issue EACN task/bid/result calls.
