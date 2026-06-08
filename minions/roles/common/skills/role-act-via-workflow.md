---
slug: role-act-via-workflow
summary: Pick the right Workflow shape (single / parallel / pipeline / phase / fan-out+verifier) for an event, with per-role recipe pointers and the size-bounded return contract. Use after Think-then-Act, before issuing the Workflow call.
layer: logical
tools: Workflow
version: 1
status: active
references: think-then-act, dispatcher-discipline, coding-methodology, think-in-parallel, evidence-driven-proposal
provenance: human+agent
---

# Skill — Role Act via Workflow

Common SYSTEM.md §4 makes Workflow the canonical Act mechanism for
every EACN-visible Role. This skill is the cheat-sheet for choosing
the shape and writing the spec.

## The five shapes

| Shape | Use when | Cost shape |
|---|---|---|
| **single agent** | Linear synthesis, fixed inputs, no fan-out value | 1× cold-start, 1× generation |
| **parallel** | ≥ 2 independent subtasks; results compose by union | N× cold-start, ~1× wall time |
| **pipeline** | ≥ 2 sequential stages with hard gate between | 2-4× cold-start, 2-4× wall time |
| **phase** | Multi-stage with intermediate handoffs (Plan → Review → Simplify, paper gather → cite → draft → integrate → compile → QA) | M× cold-start, gated wall time |
| **fan-out + verifier** | Parallel hypothesis investigators + 1 verifier picks survivor | (N+1)× cold-start, ~1× wall time |

Default: prefer the smallest shape that captures the dependency
graph. Don't reach for `phase` when `pipeline` suffices; don't reach
for `fan-out+verifier` when `parallel` and a structured return get
you the same outcome.

## Per-role recipe pointers

| Role | Common scenarios | Recipe anchors |
|---|---|---|
| **Ethics** | Mock-review (single < 50 KB; pipeline otherwise), citation-authenticity sweep (parallel), §Eth7 deep audit (phase + adversarial verifier), adjudication (pipeline + parallel evidence fan-out + adversarial verifier) | `ethics/SYSTEM.md` §Eth7 / §Eth10 / §Eth11; `mock-review` skill |
| **Expert** | Domain Q&A (pipeline), competitor scan (fan-out + verifier), experiment-result interpretation (phase), falsifiability memo (single + verifier), debug-and-fix (pipeline: root-cause → minimal-fix → smoke-test), section drafting (single), end-to-end paper work (phase: gather → cite → draft → integrate → compile → QA) | `expert/SYSTEM.md` §E4.5 plus common skills such as `coding-methodology`, `paper-compile`, and `book-to-paper-compiler` |

## Size-bounded return contract

Every Workflow spec MUST declare a return schema with these caps:

- **Total return ≤ 5 KB.** Larger and you defeat the cache discipline
  that motivates Workflow in the first place.
- **List fields capped** (e.g. `findings: max 10 items`).
- **String fields capped in chars or words** (e.g. `summary: max 200
  words`, `path: max 256 chars`).
- **Nested depth ≤ 2.** No "context object inside context object".
- **Evidence pointers, not content.** Return `commit_sha + file_line`,
  not "here's the function I read".

If the structured-output budget is genuinely insufficient, the Workflow
should write the bulky artefact to `branches/<your-role>/...` (per the
write-boundary contract) and return only the path + a digest.

## Self-contained spec contract (per common §10)

Every Workflow spec must include:

1. **Inputs** — all data the inner agent needs (paths, EACN event ids,
   prior Draft node ids). The agent does NOT inherit your SYSTEM.md.
2. **Allowed write paths** — restate the role's own branch root
   explicitly. Workflow inner agents inherit cwd but not the
   write-boundary contract.
3. **Acceptance criterion** — copy the `goal-setting` block verbatim.
   This is the verifier's only stopping rule.
4. **Return schema** — the size-bounded shape above.
5. **Forbidden tool surface** — restate the §4 list. Workflow inner
   agents are EACN-invisible **by prompt convention** (server authz
   cannot today distinguish them from main); the prompt is the
   enforcement boundary backed by a P1 tripwire hook.
6. **Scratchpad fragment** — copy this line verbatim:

   ```
   SCRATCHPAD: Write only inside ./.claude/scratchpad/ (resolves to $MINIONS_ROLE_BRANCH/.claude/scratchpad/). Do not cd, do not write to ~/.claude/, /Users/mjm/MinionsOS/.claude/, projects/project_*/.claude/ outside your own branch, or any other branches/<role>/.claude/.
   ```

## When to flip `run_in_background=true`

MANDATORY for:
- Acceptance criterion plausibly > 60 s.
- Any `phase` shape.
- Any `parallel` of ≥ 3 agents.
- Any `fan-out + verifier` shape.

While the Workflow runs, re-enter `mos_await_events()` and use
`mcp__keepalive__wait_bg(deadline_seconds=45, bg_ids=[<task_id>])` to
keep the main session's prompt cache warm. EACN responsiveness takes
precedence over Workflow latency — peers must never see a stale role.

## Verify-stage handling

When the Workflow returns, the main role:

1. Checks the structured return against the acceptance criterion.
2. Emits **at most one** ≤ 5-second evidence probe inline (per
   `evidence-driven-proposal`).
3. If suspect: `Skill(think-in-parallel)` escalates to K=3 / K=5
   parallel reasoning. Do NOT dispatch a fresh Workflow as a
   workaround.
4. If accepted: `mos_publish_to_shared` for cross-role writes (main
   only), commit durable files in your branch, emit the EACN response.

## Pitfalls

- **Hand-authoring per-subagent prompts and chaining `Task` calls
  from main.** That is the pre-v17 pattern; §4 forbids it. Issue ONE
  Workflow per relevant event.
- **Returning raw content from a Workflow.** The return is a digest,
  not a transcript.
- **Forgetting the scratchpad fragment.** Without it, a Workflow
  inner agent may write `.claude/foo` somewhere that escapes the
  branch — caught by the hook, but loud-not-silent costs you a turn.
- **Letting a Workflow block the main session past the next EACN
  event.** Background it.

## Output habit

Mark relayed findings with `[derived: workflow-<task-id>]`. The
Workflow's task_id is your evidence pointer. Persist material
findings into the Draft via `mos_draft_append` so future turns can
query at ~200 tokens instead of re-running the Workflow.
