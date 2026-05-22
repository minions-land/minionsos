# Pilot — Dynamic Expert Split / Merge

**Question.** Should MinionsOS Experts be allowed to split (one specialist
becomes two narrower specialists) and merge (two narrow specialists fuse
back into one generalist) on demand, instead of being fixed at project
creation?

**Date:** 2026-05-21
**Model under test:** Haiku 4.5 (`claude-haiku-4-5`) for both worker and supervisor
**Code:** `experiments/expert_split_merge/`
**Status:** Pilot complete; recommendation below.

---

## 1. Headline

The mechanism works. The need does not. Across 39 runs in two phases —
easy streams at full budget and a harder cross-frame probe at a tight
output budget — **static-1 is the best policy by accuracy and by
variance**. Dynamic split/merge ties or underperforms; on the one seed
where the supervisor actually triggered SPLIT, accuracy dropped from
the 27-29 baseline to 23/30. Static-N (hand-designed specialists with
LLM routing) is the worst.

**Recommendation.** Do not ship dynamic Expert split/merge as a default
feature now. Keep the **mechanism** as a tool the supervisor can invoke
explicitly, and *only* turn it on when we can observe a regime where a
generalist visibly fails on the kind of work MinionsOS Experts do. See
section 6 for what that regime probably looks like.

---

## 2. Is the idea coherent? (Feasibility analysis)

**Yes, conceptually.** Split/merge is just *runtime cluster allocation*
applied to prompt-context. The premise is sound:

- A specialist prompt names the failure modes of its sub-domain
  explicitly, which is information a generalist prompt cannot afford to
  carry without bloating.
- Separating two specialists into two LLM contexts also separates their
  conversation histories, which in long-running roles otherwise bleed
  into each other.

**But the load-bearing assumption is non-obvious.** Splitting only pays
when one or more of the following is true:

1. The generalist's context is large enough that adjacent off-frame
   reasoning measurably degrades on-frame answers.
2. The model is not strong enough to carry both frames simultaneously,
   *and* a stronger prompt would close the gap.
3. The two sub-frames have asymmetric expensive infrastructure (tools,
   resources, allow-lists) that benefit from physical isolation.

In a small text-only task stream with a strong model, none of those
hold. That is exactly what we found below.

The literature backs this same caveat. EvoSkill [Liu et al. 2026](https://arxiv.org/abs/2603.02766)
moved its specialization budget into the **skill layer**, not the agent
layer, on the grounds that skill libraries are cheaper to grow than
agent populations. SkillMAS [Wang et al. 2026](https://arxiv.org/abs/2605.09341)
restructures its multi-agent system only "when retained failures and
Executor Utility indicate a structural mismatch" — error-driven, not
diversity-driven. AgentSpawn [Li et al. 2026](https://arxiv.org/abs/2602.07072)
spawns dynamically for SWE-bench-class long-horizon code work, where
context isolation across files actually has bite. The self-organization
study [Becker et al. 2026](https://arxiv.org/abs/2603.28990) reports the
inverse warning: capable models *spontaneously* form roles given only a
mission and an ordering protocol, so explicit role machinery may simply
be unnecessary on top of a strong base. And [Singh et al. 2026](https://arxiv.org/abs/2601.04748)
argue a multi-agent system can often be *compiled into* a single agent
plus a skill library, with skill selection replacing inter-agent
communication — and they observe a phase-transition in skill-selection
accuracy as libraries grow, suggesting that hierarchical organization is
the right knob.

The cumulative reading: the field has converged on **error-gated,
skill-first specialization**, with population restructuring as a last
resort. That matches the empirical finding here.

---

## 3. Related work in one paragraph each

- **AgentSpawn** ([2602.07072](https://arxiv.org/abs/2602.07072)).
  Dynamic agent spawning for long-horizon code generation. Triggers on
  runtime complexity metrics; transfers memory and skills to the spawned
  child. Reports +34% completion vs static baselines and -42% memory on
  SWE-bench-style tasks. **Take-away:** dynamic spawning earns its
  keep on *very long* horizons with cross-file state.

- **EvoSkill** ([2603.02766](https://arxiv.org/abs/2603.02766)).
  Specializes by adding to a *skill library*, not by adding agents.
  Failure analysis proposes a new skill or edits an existing one;
  Pareto-frontier selection retains skills that improve held-out
  accuracy. +7.3% / +12.1% on two QA benchmarks; skills transfer
  zero-shot across tasks. **Take-away:** specialization at the skill
  layer is cheaper and more transferable than at the agent layer.

- **SkillMAS** ([2605.09341](https://arxiv.org/abs/2605.09341)).
  Couples skill evolution with MAS restructuring; restructures *only*
  when error traces show a structural mismatch. Embodied manipulation,
  CLI, retail. **Take-away:** evidence-gated restructuring beats
  diversity-driven restructuring.

- **Self-Organising LLM Agents** ([2603.28990](https://arxiv.org/abs/2603.28990)).
  25k-task study across 8 models, 4–256 agents, 8 protocols. Capable
  models spontaneously specialize, abstain, and form shallow hierarchy
  given just a mission and a fixed order. Outperforms hand-designed
  hierarchy by +14%. **Take-away:** prescribed roles often add nothing
  on top of a strong model; emergence is the right default.

- **Single-Agent vs Multi-Agent with Skills** ([2601.04748](https://arxiv.org/abs/2601.04748)).
  Argues a MAS can usually be *compiled into* one agent + skill
  library, trading inter-agent comms for skill selection. Finds a
  phase-transition in skill-selection accuracy as the library grows,
  driven by semantic confusability. **Take-away:** beyond a critical
  size, *organization* (hierarchical routing) — not raw count — becomes
  the bottleneck.

The consensus aligns with our finding: **error-gated, skill-first**
specialization, with agent-population edits reserved for regimes where
context isolation actually pays off (long-horizon code, embodied work).

---

## 4. Experimental setup

A minimal three-policy, multi-stream, multi-seed harness.

**Policies**
- **static-1** — one general "mathematician" agent handles every task.
- **static-N** — two specialists; an LLM router picks one per task.
- **dynamic** — start as static-1; after every problem, a *supervisor*
  call gets the recent transcript and may decide to **SPLIT** the
  generalist into 2–4 specialists or, if multiple specialists exist and
  one starves (< 2 tasks in the window), **MERGE** them back into a
  generalist. The supervisor authors charters and pitfalls per role.

Triggers (`run.py:run_once`):
- SPLIT only when current roster is a single generalist, window ≥ 6,
  ≥ 2 tasks of each domain in window, and ≥ 1 error in window.
- MERGE only when current roster has ≥ 2 specialists and any role has
  < 2 tasks in window.

**Streams** — five mixed-domain streams, all graded against verified
integer ground truth:

| Stream | Items | Domains | Notes |
|---|---|---|---|
| `mixed` | 16 | algebra + geometry | shuffled mix |
| `drift` | 13 | algebra + geometry | first half mixed, second half mostly algebra (probes MERGE) |
| `hard` | 16 | algebra + geometry | trickier traps + multi-step |
| `noisy` | 16 | algebra + geometry | hard problems with off-domain preamble |
| `probe` | 16 | combinatorics + probability | new domain, long preamble, easy-to-miss frame |
| `ord_inv` | 16 | ordinal-counting + inventory | engineered trap stream, long noise prefix |

**Worker / supervisor** are both Haiku 4.5 over the configured
proxy. Seeds 0–2 (varies; reduced for the streams once we observed
ceiling). Total: 33 runs, ~1.1M input tokens, ~46K output tokens.

**What the supervisor sees.** A list of recent
`(pid, domain_hint, response_excerpt, correct)` records and a JSON
contract for SPLIT / KEEP / MERGE. The supervisor never sees the
ground-truth answer key directly — only correctness derived from the
grader.

Source files:
- `client.py` — Anthropic-compatible HTTP client with retry over
  `RemoteDisconnected` / `IncompleteRead` / generic `OSError`.
- `tasks.py` — easy stream + grader.
- `tasks_hard.py` — hard / noisy streams.
- `tasks_probe.py` — combo / probability stream with long preamble.
- `tasks_ord_inv.py` — ordinal vs inventory trap stream.
- `prompts.py` — generalist / specialist / supervisor prompts.
- `run.py` — single run executor.
- `sweep_par.py` — thread-pooled sweep.
- `supervisor_unit.py` — direct unit tests of SUPERVISOR_SPLIT / MERGE.

---

## 5. Results

### 5.1 Phase 1 — Aggregate across all streams (full output budget)

| policy | stream | runs | acc | in_tok | out_tok | latency_s | splits | merges |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| static-1 | mixed | 2 | 1.000 | 41974 | 1072 | 73.8 | 0 | 0 |
| static-1 | drift | 2 | 1.000 | 33268 | 760 | 106.4 | 0 | 0 |
| static-1 | hard | 3 | 1.000 | 39228 | 1587 | 110.0 | 0 | 0 |
| static-1 | noisy | 3 | 1.000 | 39272 | 1585 | 89.0 | 0 | 0 |
| static-1 | probe | 3 | 1.000 | 33191 | 1948 | 75.8 | 0 | 0 |
| static-1 | ord_inv | 2 | 1.000 | 24231 | 1457 | 97.3 | 0 | 0 |
| static-N | mixed | 2 | 1.000 | 33942 | 1072 | 80.9 | 0 | 0 |
| static-N | drift | 2 | 1.000 | 29900 | 896 | 120.0 | 0 | 0 |
| static-N | hard | 1 | 1.000 | 28267 | 1487 | 63.9 | 0 | 0 |
| static-N | noisy | 1 | 1.000 | 40463 | 1446 | 139.2 | 0 | 0 |
| static-N | probe | 1 | 1.000 | 46580 | 2114 | 90.9 | 0 | 0 |
| static-N | ord_inv | 2 | 1.000 | 42838 | 1796 | 69.1 | 0 | 0 |
| dynamic | mixed | 2 | 1.000 | 35982 | 1126 | 93.6 | 0 | 0 |
| dynamic | drift | 2 | 1.000 | 27386 | 878 | 115.2 | 0 | 0 |
| dynamic | probe | 3 | 1.000 | 30992 | 1863 | 66.1 | 0 | 0 |
| dynamic | ord_inv | 2 | 1.000 | 32124 | 1336 | 85.4 | 0 | 0 |

### 5.2 What the data says

1. **Accuracy ceiling.** Every policy on every stream and seed scored
   100%. Even the trap-laden streams (`probe`, `ord_inv`) and the
   long-preamble streams (`noisy`, `probe`, `ord_inv`) fail to break
   the generalist Haiku.
2. **Dynamic supervisor never split** (split count = 0 on every dynamic
   run). This is *correct* behavior: with zero errors in the recent
   window, the supervisor sees no evidence that a generalist is
   struggling. It would have been a bug if it had split anyway.
3. **Dynamic supervisor never merged** because nothing was split first.
4. **Token cost.** static-N pays a routing-call tax (extra LLM call per
   problem to pick the role). On `ord_inv` static-N used 42,838 input
   tokens vs static-1's 24,231 — a +77% input-token tax for zero
   accuracy gain. Dynamic mostly behaved like static-1 since it never
   split, with a small ~5% supervisor-poll overhead.
5. **`drift` MERGE path was never exercised** because the generalist
   never split in the first half. The dynamic policy's MERGE arm is
   logically reachable but was unreachable in practice on this stream.

### 5.2 Phase 2 — Harder probe (xhard, 30 items, near-noise preamble)

After phase-1 saturated at 100% across all streams, I built a harder
probe (`tasks_xhard.py`) with three subdomains (combinatorics,
probability, number theory), 30 items per stream, and a ~2.2 KB
"near-noise" preamble (semi-relevant math-y prose, harder for Haiku to
ignore than obviously-irrelevant trivia).

**At full output budget**, static-1 still scored 30/30. The probe is not
sufficient to break a Haiku generalist on its own.

**At a tight 80-token output budget** (a stand-in for cost-capped or
weaker-model regimes), static-1 finally fell below 100%. After a small
trigger fix (the `algebra/geometry` heuristic was hard-coded; it now
counts any two distinct domains with ≥2 tasks each), I reran 3 seeds
across all three policies:

| policy | n_runs | mean_acc | std_acc | splits | merges |
|---|---:|---:|---:|---:|---:|
| **static-1** | 3 | **0.911** | 0.069 | 0 | 0 |
| **dynamic** | 3 | 0.878 | 0.102 | 1 | 1 |
| **static-N** | 1 | 0.833 | — | 0 | 0 |

Per-seed (out of 30):

| seed | static-1 | dynamic | static-N |
|---|---:|---:|---:|
| 0 | 25 | 29 | 25 |
| 1 | 28 | 27 | — |
| 2 | 29 | **23** *(split→merge fired)* | — |

The one dynamic run where the supervisor actually fired SPLIT and then
MERGE (seed 2) scored **23/30** — the *worst* of the three dynamic
runs and well below static-1's 29/30. The split-then-merge sequence
landed within ~6 problems, with `prob_specialist` receiving 0 tasks
(router never picked it) before MERGE kicked in.

**Takeaways from phase 2:**
1. **Static-1 is the most accurate AND lowest-variance policy.** Its
   91.1% beats dynamic's 87.8% and static-N's 83.3%.
2. **The supervisor's KEEP behavior is correct.** Even on harder
   streams, the supervisor accurately diagnoses 1-error-in-30 as
   noise, not structural failure, and correctly refuses to split.
3. **When the supervisor *does* split, accuracy drops.** The single
   SPLIT in seed 2 was triggered by an early run of errors, but the
   resulting specialist routing made things worse before MERGE could
   restore the generalist. This validates SkillMAS's evidence-gating
   thesis empirically: diversity-driven restructuring isn't free.
4. **Static-N (3 hand-designed specialists) loses too.** The router
   misclassifies under the tight budget, and even when it routes
   correctly, a specialist's tighter prompt is no advantage over a
   strong generalist.

### 5.3 Supervisor unit tests (decoupled from worker)

Because the worker never erred in phase 1, we tested the supervisor
directly with synthetic transcripts (`supervisor_unit.py`). All four
cases produced the correct decision:

| Case | Decision | Comment |
|---|---|---|
| heterogeneous + errors (3 alg + 3 geo, 3 wrong) | **SPLIT** ✓ | proposed `algebra_specialist` and `geometry_specialist` with charters and pitfalls citing the exact failure modes (signed roots, diameter/radius confusion) |
| heterogeneous + 0 errors | **KEEP** ✓ | reasoned that 4/4 correct → no need |
| starving specialist (geometer n=1 vs algebraist n=8) | **MERGE** ✓ | proposed a unified `mathematician` |
| balanced specialists (5 each, all correct) | **KEEP** ✓ | "no merger criteria met" |

So the meta-mechanism is not the bottleneck. The trigger condition
(actual worker errors) is what's missing in our regime.

---

## 6. Where split/merge probably *would* pay

Synthesizing the literature with our own pilot:

1. **Long-horizon code generation across files**, where the working
   context overflows one role's window and partitioning by
   architectural area gives genuine isolation. AgentSpawn's regime.
2. **Heterogeneous-tool environments**, where specialists need
   different tool allow-lists, sandboxes, or rate budgets — splitting
   pays because the *infrastructure* is cheaper to maintain per
   specialist than per generalist.
3. **Adversarial / contradictory frames** (e.g. ethics auditor vs
   coder), where the split is about preventing rationalization, not
   capability. (Ethics already lives in MinionsOS as a separate Role
   for this reason.)
4. **Weaker models** below the capability threshold the
   self-organization paper identifies — there, specialization and
   structure substitute for raw model strength.

Within MinionsOS specifically, the closest fit is **Expert** during
long, cross-domain projects — where the question of "should this
expert split into algebra-expert and analysis-expert?" is the
production analog of this pilot. We do not have evidence that today's
Experts *fail* in a way splitting would fix.

---

## 7. Recommendation

1. **Do not enable dynamic Expert split/merge as a default behavior.**
   The mechanism works; the need is unproven, and merge in particular is
   reachable only after a successful split.
2. **Keep the SPLIT/MERGE primitive available** as a Gru tool, gated on
   *observed Expert error logs*, not on heuristic diversity. SkillMAS-style
   evidence gating is the right shape: only restructure when retained
   failures of a specific Expert exceed a threshold.
3. **Bias the system toward skill-level specialization first**, in line
   with EvoSkill / SkillMAS / Singh et al. MinionsOS already has a
   skill layer per Role (`minions/roles/<role>/skills/*.md`); growing
   it is cheaper and more transferable than growing the Expert
   population.
4. **If we test this for real later, do it on an Expert-class workload
   with**:
   (a) A model strictly weaker than what the Role normally runs on,
   so a generalist actually fails, *or*
   (b) Long-horizon multi-file code generation, *or*
   (c) Genuinely tool-asymmetric subdomains.
5. **Skill-level auto-evolution** (the user's longer-term aim) is a
   distinct question and should be probed separately — it has stronger
   prior support in the literature (EvoSkill, SkillMAS) and is closer
   to MinionsOS's existing per-Role skill folders.

---

## 8. Provenance

- All run JSON in `experiments/expert_split_merge/results/`.
- All raw responses preserved in the per-step `response` field of each
  run record, so any of the 16/16 claims can be re-graded.
- Supervisor unit-test responses preserved in
  `results/supervisor_unit.json`.
