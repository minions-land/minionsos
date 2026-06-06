---
id: mos_reel_get
kind: tool
domain: memory
auth: [gru, expert, ethics]
source: minions/tools/mcp/reel_tools.py:22
since: stable
keywords: [reel, raw, transcript, subagent, audit, codex, agent]
related: [mos_reel_window, pitfall-subagent-boilerplate]
status: stable
---

# mos_reel_get

**One line:** Drill from a Reel ref into the native Claude JSONL session frame.

## Signature
```py
mos_reel_get(ref: str) -> {
  ref: str,
  role: str,
  session_id: str,
  tool_use_id: str,
  kind: str,
  ts: str,
  claude_jsonl: str,
  draft_node_refs: [str],
  lines: [ ... ],
}
```

`ref` shape: `"<role>/<session_id>/<tool_use_id>"`. Copy it from
`metadata.reel_ref` on any Draft node or Book page.

## Permission boundary
- Each role can read its own reel.
- Gru and Ethics can read cross-role reel entries for audit.

## Use case
Ethics dispatched a subagent to verdict 18 contradictions.
The output stamped boilerplate "needs-experiment" verdicts. Ethics ran
`mos_reel_get(ref=...)` to confirm the subagent only read 2 of 18 inputs
before deciding. Verdicts rejected, redone inline.

## See also
- domain-memory
- mos_reel_window
- pitfall-subagent-boilerplate
