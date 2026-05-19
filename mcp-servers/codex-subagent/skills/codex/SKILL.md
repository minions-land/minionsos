---
name: codex
description: "Two-tier subagent dispatch. Tier 1 (Haiku alone) for trivial tasks. Tier 2 (Codex GPT-5.5 xhigh as the actor, wrapped in a thin Haiku Agent for first-class subagent plumbing) for everything else — Codex matches Opus 4.7 capability at lower cost than Sonnet, and the Haiku wrapper buys us run_in_background + wait_bg cache keepalive + clean summary. Triggers: /codex, user asks for codex / GPT-5.5 / second opinion / let GPT handle it / delegate this."
---

# /codex — Two-tier subagent dispatch

Usage: `/codex <task description>`

Example: `/codex Fix the race condition in src/server.ts — tests are flaky under concurrent load`

---

## Mental model: two tiers, no Sonnet default

The right model layering on this host is:

| Difficulty | Subagent | Mechanism |
|---|---|---|
| **Trivial** (lookup, format, simple edit, narrow Q&A) | Haiku | `Agent(model: "haiku")` direct — Haiku alone is enough |
| **Everything else** | **Codex GPT-5.5 xhigh** (the actor) | `Agent(model: "haiku")` as a thin shell that calls the `codex` MCP tool. The Haiku wrapper is plumbing — its only purpose is to expose Codex through Claude Code's first-class Agent infrastructure, so we get `run_in_background`, cache keepalive, and a clean summary. The thinking happens inside Codex |

**Sonnet is no longer a default.** It only appears as the degraded fallback when Codex itself is unreachable (Step 5).

If you are tempted to dispatch `Agent(model: "sonnet")` because the task is "kind of medium-hard" — that is exactly the case where Tier 2 (Codex wrapped in Haiku) wins on both capability and price. Use Tier 2.

---

## Step 0 — Pick a tier

Ask one question: **can a Haiku-class model alone produce the answer reliably?**

- **Yes** → Tier 1 (Step 1).
- **No, or unsure** → Tier 2 (Step 2 or 3 depending on length).

Examples that are Tier 1:
- "What does function X return when arg is None?"
- "Reformat this list of imports."
- "Pull the URLs out of this log file."

Examples that are Tier 2:
- "Refactor this module for clarity."
- "Why are the tests flaky? Find and fix."
- "Implement this feature given the spec."
- "Code-review this PR for race conditions."

When in doubt, Tier 2.

---

## Step 1 — Tier 1: Haiku alone (trivial tasks)

```
Agent(
  description: "<3-5 word summary>",
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: "<self-contained task with all needed context>",
  mode: "auto"
)
```

Foreground is fine for most Tier 1 calls — they finish in seconds. If a Tier 1 task somehow drags past ~2 min, escalate to Tier 2.

---

## Step 2 — Tier 2A: foreground codex (short tasks ≤ 2 min)

Direct call:

```
codex(
  task: "<clear task description>",
  cwd: "<absolute path>"
)
```

### Defaults (do NOT override):
- `model`: gpt-5.5
- `sandbox`: danger-full-access
- `reasoning_effort`: xhigh

### Optional parameters (only when needed):
- `sandbox: "read-only"` — for analysis in non-git directories
- `skip_git_check: true` — when cwd is not a git repo
- `add_dirs: [...]` — extra directories Codex can access
- `timeout_seconds: N` — only when explicitly asked. **If you set this >300, switch to Step 3.**

---

## Step 3 — Tier 2B: background Codex (wrapped in Haiku Agent shell, long tasks > 2 min)

Why this exists: the `codex` MCP tool is synchronous; if codex runs 7 minutes the main session sits idle and the 5-min prompt cache expires, costing tens of thousands of uncached input tokens on the next real turn. The fix is to **wrap codex inside an `Agent(model: "haiku", run_in_background: true)`**, which upgrades Codex from "synchronous MCP tool" to "first-class Claude Code subagent". The main session immediately gets a task_id and can run a `wait_bg` loop to keep its cache warm. Haiku is just the wrapper — Codex is doing the work.

Bonus: the Haiku wrapper trims codex's raw output into a small structured summary, so the main session's context stays clean.

When to use Step 3 instead of Step 2:
- Predicted runtime > 2 minutes
- User says "long / large / many files / refactor / many tests / big change"
- You set `timeout_seconds > 300`

If unsure between Step 2 and Step 3: **prefer Step 3**. Cost of an extra Haiku relay is small (~5-10k Haiku tokens); cost of a 7-min idle main session is a full prompt-cache cold start (~50k+ uncached tokens) plus dead-air UX.

### Dispatch:

The Haiku here is **plumbing, not a thinker**. Its only jobs are: call codex with the verbatim args, copy back the structured fields codex returns, and — if codex errors — apply a narrow handbook-driven retry before giving up. Do not ask Haiku to interpret, evaluate, or improve the task. Codex itself runs at `reasoning_effort: xhigh`, so any reasoning about the task belongs there.

```
Agent(
  description: "<3-5 word summary>",
  subagent_type: "general-purpose",
  model: "haiku",
  run_in_background: true,
  prompt: """
ROLE: You are a mechanical relay between the main agent and the codex MCP tool.
You do not think about the task; you do not evaluate codex's output; you do not
add commentary. You execute the steps below verbatim and stop.

STEP 1 — call codex MCP with these EXACT args:
  task: "<the user task — VERBATIM, no rewriting>"
  cwd: "<absolute path>"
  sandbox: "danger-full-access"
  reasoning_effort: "xhigh"
  timeout_seconds: <user-specified or 1800>

STEP 2 — branch on the result:

  IF codex.status == "success" AND codex.exit_code == 0:
    go to STEP 4 (success report).

  ELSE (error, timeout, or non-zero exit):
    go to STEP 3 (handbook lookup).

STEP 3 — handbook-driven recovery (max 2 retries total per dispatch):

  3a. Read ~/.claude/skills/codex/troubleshooting.md.
      (If that path is unreadable, fall back to
       <repo>/mcp-servers/codex-subagent/skills/codex/troubleshooting.md;
       if neither is readable, skip to STEP 5 with reason
       "handbook unreachable".)

  3b. Match the failure against the entries in order. Use the FIRST entry
      whose DETECT clause matches codex.message / status / exit_code. Always
      prefer CODEX_UNAVAILABLE / CODEX_ERROR prefix matches over substring
      matches inside codex.message.

  3c. If the matching entry has AUTO-FIX: NONE → skip to STEP 5.

  3d. If the matching entry has a concrete AUTO-FIX → apply it EXACTLY as
      written (only the args the entry names; never change task text,
      sandbox, or reasoning_effort). Re-call codex MCP. Track this as one
      retry.

  3e. After the retry, branch again:
      - success → STEP 4.
      - same failure mode → STEP 5 (do NOT retry the same fix twice).
      - new failure mode → repeat 3a-3d ONCE more (this is retry #2, the
        last allowed). After retry #2, regardless of outcome, go to STEP 4
        (if success) or STEP 5 (if still failing).

STEP 4 — SUCCESS report. Write these fields and nothing else:

  STATUS: success
  FILES_CHANGED: <codex.files_changed comma-joined, or "none">
  COMMANDS_RUN: <codex.commands_run length>
  TOKENS: input=<codex.tokens.input> output=<codex.tokens.output> cached=<codex.tokens.cached or 0>
  SUMMARY: <codex.message verbatim, truncate to 4 sentences if longer>
  KEY_FINDINGS: <if codex.message names specific files / functions / failures, list them as bullets; else "none">
  RETRIES_USED: <0, 1, or 2>
  RETRY_LOG: <if retries > 0, one line per retry: "retry N: <handbook entry name> applied <fix>"; else "none">

  End. Do not add anything after RETRY_LOG.

STEP 5 — FAILURE report. Codex could not be made to work for this dispatch.
Write these fields and nothing else. Do NOT add a recommendation about what
the main agent should do — that is the main agent's call.

  STATUS: <codex_unavailable | codex_error | codex_timeout — copy from the
           "STATUS to report" line of the matched handbook entry; if no
           entry matched, use codex_error>
  ROOT_CAUSE: <copy from the matched handbook entry; if no entry matched,
               use "unknown — see RAW_MESSAGE">
  HANDBOOK_ENTRY: <name of the matched entry, e.g. codex_cli_missing; or
                   "none" if nothing matched>
  ATTEMPTS: <count of codex invocations made: 1 if no retry, 2 or 3 if retried>
  RETRY_LOG: <one line per retry attempted: "retry N: <entry name> applied <fix> — outcome <success|same-failure|new-failure>">
  RAW_MESSAGE: <last 600 chars of codex.message from the final attempt>
  COMMANDS_RUN: <count of commands codex executed across all attempts; bounds
                 the blast radius — main agent uses this to decide whether
                 partial state needs cleanup>

  End. Do not add anything after COMMANDS_RUN. Do not include a NEXT_STEPS
  or RECOMMENDATION line — the main agent decides whether to fall back to
  Sonnet, split the task, surface a config error to the user, or abort.
""",
  mode: "auto"
)
```

After the Agent dispatch returns its task_id, follow the wait_bg loop:

1. `wait_bg(deadline_seconds=180, bg_ids=[<agent_task_id>])`
2. When wait_bg ticks, call `TaskOutput(<agent_task_id>)` to check status.
3. If still running: back to step 1.
4. If done: parse the structured summary the relay produced. The shape depends on which terminal step the relay hit:
   - **STEP 4 success** — fields starting with `STATUS: success` plus `FILES_CHANGED`, `SUMMARY`, `KEY_FINDINGS`, `RETRIES_USED`, `RETRY_LOG`. Treat the work as done and present results (Step 6).
   - **STEP 5 failure** — fields starting with `STATUS: codex_unavailable | codex_error | codex_timeout` plus `ROOT_CAUSE`, `HANDBOOK_ENTRY`, `ATTEMPTS`, `RETRY_LOG`, `RAW_MESSAGE`, `COMMANDS_RUN`. Go to Step 5 (fallback decision) below. Note the relay deliberately omits any `RECOMMENDATION` line — that decision is yours.

The `bg_keepalive_nudge` hook fires automatically when the Agent is dispatched in bg mode and reminds you of this loop. Trust it.

---

## Step 4 — Parallel splitting for complex tasks

When a task has 2+ independent sub-parts, split into multiple parallel calls instead of one serial mega-task.

**Default rule: one independent unit = one codex process.**

**How to split:**
- One codex call per independent work unit
- Launch all in parallel (multiple tool calls in the same response)
- Each gets a focused, self-contained prompt
- For long sub-tasks, each is its own Step-3 backgrounded Agent relay
- Merge results after all complete

**Example:** Three benchmark cases — baseline, nature-figure, scientific-figure-making:
- If each predicted < 2 min: three parallel codex MCP calls (Step 2)
- If each predicted > 2 min: three parallel Step-3 relays
- Never combine cases into a single call.

---

## Step 5 — Fallback when codex itself errors

This fires when:
- Step 2: `codex` returns `CODEX_UNAVAILABLE` or `CODEX_ERROR` directly to the main session.
- Step 3: relay's STEP 5 failure record arrives (`STATUS: codex_unavailable | codex_error | codex_timeout`). The relay has already exhausted handbook-allowed retries; do NOT re-dispatch another Haiku-wrapped codex call hoping for a different outcome.

**Hard rule: the main agent does not execute the task itself.** Tier 2 exists precisely because the main session should not be the actor for non-trivial work. When codex falls over, you still delegate — just to a different subagent. The only thing changing is the executor.

### Fallback decision (use ROOT_CAUSE from the relay's failure record):

| ROOT_CAUSE pattern | Action |
|---|---|
| `codex CLI not on PATH` / `codex auth missing or expired` / `API quota / billing block` | Surface this as a config issue to the user in the final summary AND dispatch a Sonnet subagent so the task still gets attempted. The user needs to know codex is broken at the install level, but the work shouldn't stall on it. |
| `cwd does not exist or is not accessible` | Stop. This is a caller error — confirm `cwd` with the user before any subagent dispatch. |
| `filesystem or sandbox permission denial` | Surface to the user; ask whether to retry with `add_dirs` or a different `cwd`. Do not silently fall back, because the permission wall likely also blocks Sonnet. |
| `cwd not a git repo, skip_git_check did not resolve` / `context length exceeded — task likely needs splitting` | Re-plan: split per Step 4, or restate the task. Do not blindly hand the same monolithic task to Sonnet. |
| `timeout or hang at <elapsed>s` | Decide: re-dispatch as Step 3 with a larger `timeout_seconds`, or split per Step 4. Consider the user's latency budget. |
| `API rate-limited` / `persistent upstream 5xx after one retry` | Wait briefly (the user is watching) and re-dispatch the same Step 3 call. If it fails twice in a row, fall back to Sonnet. |
| `unknown` / handbook had no entry | Fall back to Sonnet AND record the new failure mode at the end of the response so a handbook entry can be added later. |

### Sonnet subagent fallback dispatch:

```
Agent(
  description: "<3-5 word summary> (codex fallback)",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: "<same task prompt + specific files to read, commands to run, success criteria>",
  mode: "auto",
  run_in_background: <true if expected long, else omit>
)
```

For long fallback tasks, run the same wait_bg loop as Step 3.

In your final user-facing summary, note "codex unavailable (<ROOT_CAUSE>); fell back to Sonnet" so the user understands the executor swap. If the ROOT_CAUSE is a config issue (Entries 1, 2, 8 in the handbook), also tell the user explicitly what to fix — they likely want their codex install repaired even if the current task is now running on Sonnet.

---

## Step 6 — Present results

1. Summarize what was done in 2-3 sentences (use Haiku relay's SUMMARY field if Step 3 was used).
2. Show files changed and key findings.
3. If the task failed, explain why and suggest next steps.

---

## Tips for good task prompts (apply to all tiers)

- State the goal clearly in one sentence — be specific about scope and boundaries.
- Include what "done" looks like (tests pass, type-checks clean, file produced, etc.).
- Mention relevant files if the task is scoped.
- Include constraints (don't touch X, must be backwards-compatible, etc.).
- Keep prompts focused: a precise, well-bounded task finishes faster and more reliably than a vague one.
