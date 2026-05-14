# Stage B Coherence — expert + gru + noter + reviewer (12 skills)

Read-only audit. No skill files modified.

## Bucket summary

| Skill | Bucket | Confidence |
|---|---|---|
| expert/dialectics | COHERENT | high |
| expert/first-principles | COHERENT | high |
| gru/feature-intake | COHERENT | high |
| gru/project-automation-audit | COHERENT | high |
| gru/role-skill-design | COHERENT | medium-high |
| noter/role-session-diff-timeline | COHERENT | high |
| reviewer/aspect-review | COHERENT | high |
| reviewer/code-validity-review | NEEDS POLISH | medium |
| reviewer/publish-review-result | COHERENT | high |
| reviewer/revision-delta | COHERENT | high |
| reviewer/run-review-round | COHERENT | high |
| reviewer/simulate-reviewer-instance | COHERENT | high |

Counts: 11 COHERENT, 1 NEEDS POLISH, 0 NEEDS REWRITE, 0 STITCHED-TOGETHER.

## Per-skill verdicts

### expert/dialectics — COHERENT

One reasoning move (thesis → antithesis → contradiction inventory → synthesis → verify). Frontmatter summary, "When to invoke," "Structure," "Procedure," and "Pitfalls" all push the same idea: a synthesis that predicts new things. The four dialectic patterns (scale / distribution / metric / short-long) live inside Structure as supporting taxonomy, not as a parallel skill.

Evidence:
- "Every strong position contains its own limitation. Surfacing the limitation before you commit is how you avoid overfitting to a single frame."
- "A genuine synthesis makes new predictions. If none, it is a compromise, not a synthesis."

No stitched seams. Output habit (`[derived: dialectical synthesis of <thesis> vs <antithesis>]`) matches the body.

### expert/first-principles — COHERENT

Same shape as dialectics. Single move (strip → reduce → rebuild → name divergence). Voice stays principled-reasoning throughout; no drift into checklist territory.

Evidence:
- "The most valuable output is the specific assumption the standard practice smuggled in that your reconstruction drops."
- "First-principles reasoning that rejects the field's accumulated evidence without new data is almost always wrong."

The `references: dialectics` link is appropriate; the two skills are siblings, not duplicates. Pitfalls correctly guard against over-application and crank mode.

### gru/feature-intake — COHERENT

Single trigger (author request / coordination / decomposition). Single core move (intake → bounded role-owned tasks with observable acceptance criteria). The six steps cohere as one workflow. Does not creep into "implementation," "budget approval," or "dashboard updates" — pitfalls explicitly call out turning intake into implementation.

Evidence:
- "Gru owns intake and coordination; Coder, Writer, Experimenter, and Reviewer own execution. Intake is not implementation."
- "Asking which language / framework to use when the repo is already Python with a clear stack…"

### gru/project-automation-audit — COHERENT

Single trigger (project stabilized, automation question). Single move (read-only scan with bounded recommendations). The "≤2 per category" cap and the install-now / draft / backlog / reject classification are part of the same procedure, not bolted-on extras.

Evidence:
- "Read-only scan… Up to two recommendations per category… Each recommendation classified `install now` / `draft skill` / `backlog` / `reject`."
- "Recommending a hook or MCP server because it sounds useful, without an EACN history entry or role log line that shows the friction it would solve."

### gru/role-skill-design — COHERENT (mild)

Single trigger (adding/refactoring a role skill, or a recurring role mistake). Single move (author a Markdown skill at the right ownership layer). Procedure delegates to `_skill_template.md` and `SKILLS.md` rather than restating layout — that keeps it from bloating into an essay.

Evidence:
- "Sharpen decisions; do not duplicate the role's SYSTEM prompt."
- "Copy the template… Follow `minions/roles/common/SKILLS.md` for frontmatter semantics."

Mild observation: 8-step procedure with two near-meta steps ("Validate discovery", "Report") makes it slightly longer than its Expert siblings, but every step still belongs to the same authoring task. Not stitched.

### noter/role-session-diff-timeline — COHERENT

Procedural skill, voice held throughout. Single trigger (every Noter wake). Single core move (diff archived role session jsonl → append to `timeline.md`). The cursor file machinery (`.session-scan-cursor.json`, atomic `.tmp` + rename) is integral to the procedure, not a separate skill.

Evidence:
- "Observation must be **read-only**. Never call `eacn3_get_events`, `eacn3_await_events`, or `eacn3_next` — those drain the network queues and steal events from the roles they belong to."
- "Don't write into role branches. Branches belong to their owning roles; your write scope is `artifacts/notes/` only."

Importantly, this is *not* the "diff timeline + summary writing + EACN reporting" trio that would constitute a stitched-together Noter skill — it is just the diff/timeline step. Cadence summaries and EACN reporting are correctly excluded.

### reviewer/aspect-review — COHERENT

Single move (one aspect, one stance, evidence-backed aspect-note). The aspect menu table is supportive taxonomy. Boundary text (local-only, EACN-invisible, read-only on review history during Pass A) is on-task — it is what makes an aspect subagent an aspect subagent.

Evidence:
- "One narrow aspect, one assigned stance, evidence-backed notes for the parent reviewer instance. Local-only and EACN-invisible by design."
- "Reading `artifacts/reviews/**`, author rebuttals, changelogs, or previous summaries during Pass A."

### reviewer/code-validity-review — NEEDS POLISH

Internally coherent — one move (code as evidence; bind every finding to a claim) — but it overlaps non-trivially with aspect-review's `experiments` and `reproducibility` aspects, and the trigger leaves the relationship implicit.

Evidence (this skill):
- "Reviewer assigns a `Code validity` or `Experiment validity` subspect."
- Validity-risk checklist: "data leakage, train / test mixups, hardcoded results, benchmark shortcuts, stale baselines, seed contamination, cherry-picking, metric mismatch, unreported filtering."

Evidence (aspect-review):
- `experiments` aspect: "baselines, controls, metrics, seeds, variance, ablations, protocol validity"
- `reproducibility` aspect: "code, scripts, environment, datasets, checkpoints, leakage, command-level reconstruction"

The overlap with `experiments` + `reproducibility` is roughly 70%. As written, code-validity-review reads like a third territory, but operationally it is a deeper-zoom aspect note. Recommendation: either (a) reposition this as a *zoom-in* of the `experiments` / `reproducibility` aspect when a paper claim's evidence chain demands a code-trace, with an explicit note "this is the deep-trace variant of `experiments` + `reproducibility`," or (b) fold it into aspect-review as a callable mode. Pick one. Right now a Reviewer main reading both at wake-up cannot tell whether to invoke `aspect-review` with `experiments` or `code-validity-review`.

This is the only skill in the cohort with a partition problem. It is not stitched-together internally; the issue is *cross-skill ambiguity*.

### reviewer/publish-review-result — COHERENT

Single trigger (after `consolidated.md` is complete). Single core move (publish one self-contained packet via Local EACN). The decision → next-action table belongs to the publish step (it is what the consolidated packet is *for*), not a separate concept.

Evidence:
- "One self-contained markdown packet the project team can act on…"
- "Sending only the decision label without the individual reviews."

### reviewer/revision-delta — COHERENT

Single trigger (Pass B/C when prior summary exists). Single core move (independent revision check, blind to current reviewer reports). The two-phase reading split (Pass B = previous summary only; Pass C = current revision materials) is internal to this skill and is *the* core move, not two skills mashed together.

Evidence:
- "Independent revision-check state. The revision-delta subagent is deliberately blind to current-round reviewer reports to preserve that independence."
- "Looking at current-round reviewer reports. This breaks the independent revision-check state."

### reviewer/run-review-round — COHERENT

Pure orchestration. Delegates correctly: spawn reviewer instances per `simulate-reviewer-instance`, spawn revision-delta subagent per `revision-delta`, publish per `publish-review-result`. Does not duplicate sub-skill procedures — it just sequences and bounds them. The "grow from 3 to 5" rule and the round-directory layout belong here, not in the sub-skills.

Evidence:
- "**Pass A** — 3–5 independent reviewer instances see current submission only. No prior summaries, prior reviews, rebuttals, changelogs, or Reviewer-main paraphrases."
- "Treating `fresh.md` as a synthesis. It is a direct concatenation of individual reviews."

### reviewer/simulate-reviewer-instance — COHERENT

Single move (one reviewer instance = composite of aspect subagents with mixed stances). Delegates aspect work to `aspect-review`. Trigger ties cleanly to `run-review-round` Pass A. The aspect mix and stance mix rules belong here, not in aspect-review (each instance picks the mix; aspect-review just executes one).

Evidence:
- "One reviewer instance is a *composite*: several aspect subagents, each inspecting a different part of the submission with a different stance."
- "Giving all aspect subagents the same stance. The dynamic mix is intentional."

## Reviewer cluster partition analysis

### Pass A isolation

Clean. Pass A's "no history" rule is enforced in three layered places, which is the right number:

- `run-review-round` Structure declares the rule for the whole pass: "current submission only. No prior summaries, prior reviews, rebuttals, changelogs, or Reviewer-main paraphrases."
- `simulate-reviewer-instance` inherits it (Pass A is its only orchestrated trigger) and forbids aspect subagents from reading review history.
- `aspect-review` Pitfalls explicitly forbid `artifacts/reviews/**`, rebuttals, changelogs, or previous summaries during Pass A.

No leakage between Pass A and Pass B/C: revision-delta is the only Pass B/C path and it explicitly forbids looking at current-round reviewer reports.

### Sub-skill overlap

One real overlap: **aspect-review (`experiments` + `reproducibility` aspects) ↔ code-validity-review**. Both cover seeds, leakage, baselines, metrics, code-traceable evidence. The trigger boundary ("Code validity or Experiment validity subspect") is asserted but not visibly distinct from how aspect-review handles `experiments` / `reproducibility`. See the per-skill verdict above for the recommended fix.

No overlap between the other sub-skills: simulate-reviewer-instance owns the *composition* of aspects; aspect-review owns *one aspect*; revision-delta owns *prior-summary-vs-current-revision*; publish-review-result owns *EACN delivery*. These are partitioned cleanly.

### run-review-round delegation

run-review-round delegates rather than duplicates. It hands off:

- Pass A reviewer-instance creation → `simulate-reviewer-instance` (which then hands off → `aspect-review`).
- Pass B/C → `revision-delta`.
- Final publish → `publish-review-result`.

What run-review-round keeps for itself, correctly: round-directory layout, reviewer count growth rule (3 → 4 → 5), `fresh.md` concatenation rule, the meta-review packet structure, and the rolling summary write.

The orchestrator is not redoing sub-skill work. The cluster's overall partitioning is sound; the only seam to tighten is the code-validity-review vs aspect-review boundary.
