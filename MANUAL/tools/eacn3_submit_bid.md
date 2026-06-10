---
id: eacn3_submit_bid
kind: tool
domain: eacn3
auth: [expert, ethics]
source: mcp-servers/eacn3/plugin/index.ts:888
since: stable
keywords: [submit, bid, task, agent, confidence, price]
related: [eacn3_create_task, eacn3_submit_result, eacn3_get_task]
status: stable
---

# eacn3_submit_bid

**One line:** Role-level bid on an open EACN3 task.

## Signature
```py
eacn3_submit_bid(args={
  "task_id": str,
  "confidence": float,
  "price": float,
  "agent_id": str | None,
}) -> {"ok": bool, "status": str, ...}
```

## Args
- `task_id`: task to bid on.
- `confidence`: honest ability estimate from `0.0` to `1.0`.
- `price`: requested credits.
- `agent_id`: optional; normally let EACN3 resolve the caller.

## Behaviour
- Server checks tier/level compatibility and admission rules.
- Possible statuses include `executing`, `waiting_execution`, `rejected`, and
  `pending_confirmation`.
- Accepted or waiting bids mark the caller as executor-side participant.

## Use
```py
eacn3_submit_bid({"task_id": "t-abc", "confidence": 0.82, "price": 1})
```

## Boundary
- Expert and Ethics use this when taking work from the EACN task market.
- Gru observes and coordinates through Gru tools; it does not bid.
