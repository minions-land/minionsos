---
id: domain-subagent-handoff
kind: domain
domain: subagent-handoff
auth: ['*']
source: minions/roles/SYSTEM.md:111
since: stable
keywords: [subagent, handoff, dispatch, delegate, prompt, self-contained, agent, codex, task]
related: [delegate-heavy-task, dispatcher-discipline, mos_reel_get, pitfall-subagent-boilerplate]
status: stable
---

# Subagent handoff — what every spawned prompt must carry

Subagents (Claude `Task`/`Agent`, `mcp__codex-subagent__codex`) are
EACN-invisible by construction. They report only to the main Role that
spawned them. They do NOT inherit project context — every constraint
must be in the prompt.

## The five fields a handoff prompt MUST carry

A subagent prompt is broken if any of these is implicit:

1. **Role boundary** — which Role you are dispatching from, what
   write scope is allowed (e.g. "you are dispatched from Expert; you may
   only write under `branches/expert-<slug>/`").
2. **Tool / path scope** — exact tools the subagent may call, exact
   paths it may read or write. EACN tools are NEVER available to a
   subagent (they are EACN-invisible).
3. **EACN-invisibility note** — explicit reminder: "you do not have
   eacn3_* tools; do not try to send EACN messages; report back to the
   spawner only."
4. **Expected output shape** — file path written, structured fields
   returned, or both. Short return formats reduce drift.
5. **Verification requirement** — "run `pytest tests/unit/foo.py`
   after editing", "verify `ruff check`", "render and inspect the PDF" —
   whatever satisfies the spawner's plan.

## Anti-patterns

- **Vague task strings** ("fix the bug", "improve the code"). Subagents
  pattern-match; vague input → boilerplate output. See
  `pitfall-subagent-boilerplate`.
- **Verdict batching > 3 items in one call.** Chunk to 5-at-a-time or
  do the long tail inline.
- **Task summary instead of artifact path.** Always pass the path,
  never just a summary the subagent might re-imagine.
- **Implicit NON-GOALS.** For multi-file Codex calls, spell out what
  NOT to touch — stops drift into "obviously also needed" adjacent work.

## Verification on return

Before accepting a verdict touching > 3 items, pull the reel:

```python
mos_reel_get(ref="<role>/<session_id>/<task_id>")
mos_reel_window(ref=..., span=10)
```

Check: did the subagent actually read each input artifact, or
pattern-match on titles? Generic rationales are red flags.

## See also

- `delegate-heavy-task` skill — when to choose Codex over Claude subagent
- `dispatcher-discipline` skill — the Plan → Dispatch → Verify cadence
- `pitfall-subagent-boilerplate` — what lazy verdicts look like
