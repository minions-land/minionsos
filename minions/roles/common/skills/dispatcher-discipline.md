---
slug: dispatcher-discipline
summary: Cache discipline (advisory). The main session's working set is precious; large reads / multi-file scans / heavy edits should land inside Workflow agents (common §4) where the disposable context absorbs the bytes. This skill is the cost rationale that motivates Workflow.
layer: logical
tools: Workflow, Task, mos_draft_append
version: 2
status: active
supersedes:
references: think-then-act, role-act-via-workflow, cognitive-checkpoint
provenance: human+agent
---

# Skill — Cache Discipline (advisory)

The main Role process is a long-lived `claude` interactive session. Its
prompt cache holds your SYSTEM.md, tool definitions, and conversation
history. Every uncached input token in this session is paid full price
and gets cached for next turn — so dropping a 16 KB file into
conversation history is not a one-time cost, it is a permanent rent on
every future turn until reset.

**This skill is advisory.** Common §4 makes Workflow the canonical Act
mechanism, and Workflow agents are the disposable context that absorbs heavy
reads. The cost decomposition + break-even tables below explain why §4 routes
substantive work through Workflow.

## Why (measured, not theoretical)

Real session jsonls show the cost decomposition:

| component        | share of total cost |
|------------------|---------------------|
| uncached input   | 62.8% (median 31.6k tokens / turn) |
| cache_read       | 31.3% |
| cache_create     | 1.8% |
| output           | 4.2% |

And uncached input by source:

| source                | share of uncached input |
|-----------------------|-------------------------|
| `Read` tool results   | **51%** (mean 4.6k, p95 16k tokens / call) |
| `Bash` tool results   | **43%** |
| Subagent / Workflow returns | 3% (because they return summaries) |
| Edit / Write          | 2% |
| User text + others    | 1% |

So 94% of the bleed is `Read` + `Bash` in the main session. Routing
those through a Workflow agent moves the raw bytes into a disposable
context and your main session only sees the size-bounded structured
return (≤ 5 KB per common §4).

Cache_keepalive and 1h TTL optimize the 33% slice. **Routing heavy
work through Workflow optimizes the 63% slice.** Bigger lever.

## Break-even thresholds

Workflow has overhead (~$0.12 cold-start per agent). Only route
inline-replaceable work through Workflow when the long-horizon saving
exceeds that overhead. Measured break-even:

| File size | Break-even turns | Guidance |
|-----------|-----------------|----------|
| <15 KB    | >120 turns      | Direct Read in main is fine |
| 15-50 KB  | 30-120 turns    | Judgment call — Workflow if you expect many future turns |
| >50 KB    | <30 turns       | Always inside Workflow — compounding cost is large |
| Multi-file scan | immediate | Always inside Workflow — aggregate size dominates |

These are the same thresholds Workflow internals follow. The point is
that **§4 already routes substantive work through Workflow**; you do
not need to re-justify the choice for each event. Use the table below
when deciding what the main session may still do directly versus what
must move into the Workflow agent.

| Action | Main directly? | Inside Workflow? |
|---|---|---|
| `Read` < 50 KB single file | yes | yes (agent's own discretion) |
| `Read` ≥ 50 KB or multi-file scan | no | yes |
| `Bash` whose output you can bound to ≤ 5k chars | yes (with `head`/`tail`/`grep`) | yes |
| `Bash` whose output you cannot bound | no | yes |
| `Edit` / `Write` | no (Verify-stage helpers excepted; see common §4) | yes |
| Investigation ("how does X work") | no | yes |
| `Grep` / `Glob` narrow (≤ 20 matches) | yes | yes |
| `Grep` / `Glob` broad | no | yes |
| ≤ 5-second evidence probe | yes (one per Verify) | yes |

## Workflow Return Discipline

The Workflow spec contract lives in common §4 and the
`role-act-via-workflow` skill. Return **size-bounded structured data, not raw
content**. A Workflow that returns 16 KB of "here's what I read" defeats cache
discipline; demand bullets + evidence pointers per the §4 schema cap (≤ 5 KB
total, nested depth ≤ 2, list and string fields each capped).

## Persist findings to Draft

When the Workflow's structured return contains a structural finding (a
hypothesis, a verified citation, a refuted approach), `mos_draft_append`
it. Future turns query the Draft (~200 tokens) instead of re-Reading
the file (~5k tokens).

## After dispatching with `run_in_background: true`

Long Workflows must run with `run_in_background=true` per common §4.
Don't fill the wait window with `mos_await_events()` — that is the
EACN event-loop tool. Use the keepalive MCP server instead:

```
wait_bg(deadline_seconds=45, bg_ids=[<task_id>])
# When it ticks, check early_exit:
#  - early_exit=True  → TaskOutput(<task_id>) and process the result
#  - early_exit=False → TaskOutput(<task_id>) to check progress, then loop
```

`wait_bg` keeps the main session's prompt cache warm during the wait
and returns early as soon as the Workflow finishes. Confirm the tool
is visible by name — every Role has it from the `keepalive` MCP
server.

## Pitfalls

- **Treating this skill as a hard rule again.** It is advisory in v17;
  §4 is the rule. If you find yourself authoring per-subagent prompts
  from main, you are bypassing Workflow — re-read §4.
- **Asking a Workflow agent to return raw content** instead of a
  structured summary. The size-bounded return is the whole point.
- **Reading files in the planning stage.** Plans should be made from
  Draft queries, not from re-reading source files. If you need source
  to make a plan, run a single-agent Workflow first that returns
  "what does this code do" as a summary, then plan.
- **Doing the inline fallback** more often than common §4's host-
  fallback ladder allows. Inline is layer 4 of the ladder, not the
  default.

## Output habit

Every Workflow dispatch creates an evidence trail:
- The Workflow spec (in your conversation history) names exactly what
  was investigated and the verifier criterion.
- The Workflow's compact structured return is your only kept artifact.
- Material findings flow into the Draft via `mos_draft_append` with
  `evidence_tag` pointing at the Workflow's task_id / commit / file
  line.

Mark derived claims per the Evidence-first EACN convention:
`[derived: workflow-<task-id>]` when relaying findings on EACN.
