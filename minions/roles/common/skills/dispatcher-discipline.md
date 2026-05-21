---
slug: dispatcher-discipline
summary: Main role is a pure dispatcher — Read/Bash/Edit/investigation always go to a Task subagent. Keeps the main session's prompt cache hot; subagent context is disposable.
layer: logical
tools: Task, mos_draft_append
version: 1
status: active
supersedes:
references: think-then-act, delegate-heavy-task, cognitive-checkpoint
provenance: human+agent
---

# Skill — Dispatcher Discipline

The main Role process is a long-lived `claude` interactive session. Its
prompt cache holds your SYSTEM.md, tool definitions, and conversation
history. Every uncached input token in this session is paid full price
and gets cached for next turn — so dropping a 16 KB file into
conversation history is not a one-time cost, it is a permanent rent on
every future turn until reset.

**The discipline: keep the main session's working set small. Dispatch
all heavy reading, editing, and investigation to Task subagents. Their
context is disposable; yours is not.**

This is the always-on stance for every cycle, not a special mode you
enter only when think-then-act fires.

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
| Subagent (`Task`/`Agent`) returns | 3% (because they return summaries) |
| Edit / Write          | 2% |
| User text + others    | 1% |

So 94% of the bleed is `Read` + `Bash` in the main session. Routing
those through a Task subagent moves the raw bytes into a disposable
context and your main session only sees the 1-2k summary.

Cache_keepalive and 1h TTL optimize the 33% slice. **Dispatching
heavy work optimizes the 63% slice.** Bigger lever.

## When to dispatch (threshold-aware, not blanket)

Dispatch has overhead (~$0.12 subagent cold-start). Only dispatch when
the long-horizon saving exceeds that overhead. Measured break-even:

| File size | Break-even turns | Guidance |
|-----------|-----------------|----------|
| <15 KB    | >120 turns      | Direct Read — dispatch overhead not worth it |
| 15-50 KB  | 30-120 turns    | Judgment call — dispatch if you expect many future turns |
| >50 KB    | <30 turns       | Always dispatch — compounding cost is large |
| Multi-file scan | immediate | Always dispatch — aggregate size dominates |

Concrete rules:

- **`Read`**: files under ~50 KB → direct read is fine (the per-turn
  cache_read cost is negligible). Files over ~50 KB or multi-file
  investigations → dispatch. If you only need a few lines from a large
  file, use `Read(file_path, offset=N, limit=20)` instead of dispatch.
- **`Bash`**: any command whose output you cannot bound to ~5k chars
  → either pipe through `head -100` / `tail -100` / `grep` / `wc`,
  OR dispatch if you need the full output analyzed.
- **`Edit`/`Write`**: always dispatch. The main session never edits
  files.
- **Investigation** (multi-file, "let me look at how X works"): always
  dispatch. Subagent reads N files, returns a 1-page synthesis.
- **`Grep`/`Glob`**: direct is OK if the pattern is narrow (you expect
  ≤ 20 matches). For broad searches (`*.py` across the repo) →
  dispatch.

**Do NOT hard-block small Reads.** A 10 KB source file read directly
into main is cheaper than dispatching a subagent to summarize it.
The discipline is about large files and multi-file scans, not about
avoiding all direct tool use.

## How to dispatch — the subagent prompt template

```
Task(
    subagent_type="general-purpose",  # or specialized agent name
    description="<short title>",
    prompt="""
Investigation goal: <single sentence>

Allowed actions: <Read | Edit | Write | Bash | Grep | Glob — be specific>
Forbidden actions: any EACN3 tool, any mos_project_*, any mos_spawn_*
                   (subagents are EACN-invisible by construction)

Files / directories of interest:
- <path1>: <why>
- <path2>: <why>

Return format (this is what I will see; everything else is discarded
when your context dies):
- <heading 1>: <1-2 lines>
- <heading 2>: <bullet list, ≤5 items>
- Evidence pointers (commit SHA, file:line, EACN event id) for any
  derived claim.

Acceptance criterion: <specific binary check — test passes, file
exists at path X with shape Y, etc.>

Stopping condition: <when subagent should return, e.g. "after the 3
files are summarized" / "after the bug is fixed and tests pass">
""",
)
```

## Procedure

1. **Decide if dispatch is needed.** Apply the thresholds above. Bias
   toward yes — main-session Read is expensive.

2. **Write a self-contained subagent prompt.** Copy the template above.
   The subagent does NOT inherit your SYSTEM.md, your skills, your
   write-boundary table, or any context. Repeat what it needs.

3. **Specify the return format aggressively.** A subagent that
   returns 16 KB of "here's what I read" defeats the point — you've
   moved the cost from your context to the tool_result, which still
   ends up in your context. Demand bullet points + evidence pointers.

4. **Verify the return** against your acceptance criterion. If it
   does not satisfy, re-dispatch with narrower scope rather than
   "fixing it yourself" inline (that's the trap — you'd Read the file
   yourself, blowing up your context).

5. **Persist findings to Draft.** When the subagent's summary contains
   a structural finding (a hypothesis, a verified citation, a
   refuted approach), `mos_draft_append` it. Future turns query the
   Draft (~200 tokens) instead of re-Reading the file (~5k tokens).

## What this discipline trades

- **You spend a bit more wall time** per turn (subagent cold-start +
  its own work) for a much smaller main-session footprint.
- **You write more careful subagent prompts** because the subagent
  gets no context from you for free.
- **You learn to ask "what's the smallest thing I need to know?"**
  before reading anything — which is a feature, not a cost.

In exchange you get: a main session that stays under ~150 KB
conversation history for hours, near-100% cache hit rate, and a
linear (not super-linear) per-turn cost as the project ages.

## Pitfalls

- **Resisting dispatch because "it's a small file, it's fine"**: the
  main-session cost is per-future-turn, not per-Read. A 4 KB Read
  costs 4 KB on every subsequent turn until you reset. Dispatch even
  for small reads if you'll do many of them in one wake.
- **Asking the subagent to return raw content** instead of a
  summary: pull the bytes out of your hands and into the
  subagent's, but if you echo them back you've reset the cost. The
  subagent's job is to digest, not to ferry.
- **Doing the inline fallback** (when no host-native subagent is
  available) more often than the host actually requires it: that
  exception exists for hosts that genuinely cannot spawn
  subagents, not as a license to skip dispatch on Claude Code.
- **Reading files in the planning stage** (Plan stage of think-then-act).
  Plans should be made from Draft queries, not from re-reading source
  files. If you need source to make a plan, dispatch a Task to
  produce a "what does this code do" summary first, then plan.

## Output habit

Every dispatch creates an evidence trail:
- The subagent prompt (in your conversation history) names exactly
  what was investigated.
- The subagent's compact return is your only kept artifact.
- Material findings flow into the Draft via `mos_draft_append` with
  `evidence_tag` pointing at the subagent's commit / file / line.

Mark derived claims per the Evidence-first EACN convention:
`[derived: <subagent-task-id>]` when relaying findings on EACN.
