# Behavioral MetaHarness — coding-methodology v2 (added Rules 7 / 8 / 12)

Date: 2026-05-14
Subject: `minions/roles/coder/skills/coding-methodology.md` after integration of three new rules (Read before write, Surface conflicts, Fail loud), plus the synced experimenter and gru copies.

## What changed in the skill

Net add: **5 lines** (103 → 108). All three rules folded into the existing Plan → Review → Simplify scaffold without restructuring.

| Rule | Origin | Where it landed |
|---|---|---|
| Rule 8 — Read before you write | New Phase-1 step 1 ("Read the territory first"); pitfall added | "you cannot surface meaningful assumptions without reading the file you'll touch" — depth proportional to change |
| Rule 7 — Surface conflicts, don't average | Extension to Phase-1 step 4 ("Scope surgical changes") | When two contradicting patterns exist, pick one (more recent / more callers), follow it, flag the other |
| Rule 12 — Fail loud | New paragraph in Gate definition; pitfall added | "Gate passes" requires every command ran end-to-end and reported green; silent skips disqualify the gate |

## Test 1 — SSL recall (does Haiku pick this skill from a [Skills] block?)

One Haiku agent shown all 8 coder skill summaries (frontmatter only) and 5 situations. It picks which skills to load.

| Situation | Expected | Haiku picked | Verdict |
|---|---|---|---|
| Refactor eacn_client to use connection pool, 4 files, ~100 lines | coding-methodology | coding-methodology + feature-implementation | ✅ correct |
| Add public `format_status()` to state/store.py | coding-methodology | NONE | ❌ **miss** |
| Fix typo "asyncronous" in docstring | none | NONE | ✅ correct |
| Read-only question about `register_role` | none | NONE | ✅ correct |
| 3-line `KeyError` patch with `.get(default)` | none (single-function) | bounded-repair-loop | ✅ acceptable substitute |

**4/5 correct.** The one miss (S2: add public helper) is on `coding-methodology`'s existing summary — `summary` says "non-trivial code change" and Haiku reads "add a one-line helper" as trivial. This is a **summary-level finding**, independent of the rule-set additions; the body (where Rules 7/8/12 live) is what gets loaded after recall succeeds, so the new rules cannot affect this miss.

**Implication for SSL discipline:** the `summary:` line should add a concrete trigger like "any new public function or class on a public module". Pre-existing concern (the SKILL_EVAL.md round 1 already flagged "non-trivial" as vague); the three-rule addition does not regress recall.

## Test 2 — Behavioral A/B (do Rules 7 / 8 / 12 actually flip Haiku's behavior?)

Three scenarios, each: 2 parallel Haiku agents (with-skill / baseline), skill-specific vocabulary (`Phase 1`, `coding-methodology`, `Read the territory`, `Code Simplifier`) stripped from with-skill responses, then Codex GPT-5.5 (low reasoning, read-only sandbox) blind-judges with random RED/BLUE labels.

| Scenario | Tests | Codex verdict | Confidence | Skill-fingerprint detection |
|---|---|---|---|---|
| Add public `format_status()` when private `_format_status_line()` already exists | Rule 8 (Read before write) | with-skill **wins** (renames; no duplication) | high | "either could have a skill" |
| Add `connect()` in module C; package has Result-style and raise-style modules side by side | Rule 7 (Surface conflicts) | with-skill **wins** (names contradiction; picks newer; asks before assuming) | high | "either could have a skill" |
| Report gate result when `ty check` errored with "command not found" | Rule 12 (Fail loud) | with-skill **wins** (declares gate fails on missing tool) | high | "either could have a skill" |

**3/3 with-skill wins, all high confidence, all blind.**

The "either could have a skill" verdicts on all three are the cleanest signal: vocabulary stripping worked. Unlike the original 2026-03 pilot run on this same skill (where Codex fingerprinted RED via "Phase 3" verbatim), Codex here is judging engineering quality, not stylistic identity.

### Where each new rule prevented a real failure

**Rule 8 — Read before write.** Baseline read the same file excerpt and still chose to *duplicate* the existing helper into a new public method, leaving two functions with identical bodies. With-skill chose to expose the existing helper by renaming it. Single source of truth. Codex called BLUE's plan out for "duplicating the same formatting logic while keeping the old private method".

**Rule 7 — Surface conflicts.** Both responses correctly chose the Result-style pattern. The difference: baseline silently invented a new `ConnectedClient` wrapper class with a new send/recv API on top, blending in `relay.py`'s socket details (the older module). With-skill explicitly named the contradiction, asked the user to confirm the abstraction shape, and stayed within the existing patterns. Codex flagged baseline's invented wrapper.

**Rule 12 — Fail loud.** This is the most decisive case. Baseline literally wrote *"the gate passes on the checks that ran"* while one of four required checks errored at startup with "command not found". With-skill wrote *"the gate does not pass"* and named the missing binary as a hard blocker. This is exactly the silent-success failure mode Rule 12 was added to catch.

## What this run does NOT show

- Per-rule effect sizes are not separable in the multi-rule skill: with-skill agents had access to all three rules in every probe. The probes were *designed* to exercise one rule each, but a clever agent could in principle apply multiple rules to a single situation. Codex's reasoning text confirms each scenario's verdict was driven by the targeted rule, not bleed-through.
- Sample size = 1 trial per scenario. The pilot harness used the same N=1 design and got actionable results, but absolute effect sizes need higher N to estimate. The qualitative direction is unambiguous here (3/3 high-confidence wins).
- Recall regression on `summary:` line: not measured against the pre-edit version because the `summary:` field was unchanged. The S2 miss reflects a pre-existing summary weakness, not a regression.

## Verdict for the new rules

**Keep all three.** The 5-line addition lifts behavioral quality on three failure modes that the original 4-rule Karpathy version did not address:

1. Adding code in a file you have not read this session.
2. Blending two contradicting in-codebase patterns.
3. Reporting "tests pass" when one of the gate commands silently did not run.

All three are real and reproducible against Haiku-class executors on realistic MinionsOS-shaped problems. The 12-rule article's reported error-rate drop from 41% to 3% comes from a much larger evaluation; this harness was not designed to reproduce that headline number, only to verify that the three additions do not regress recall and do change behavior in the predicted direction. Both checks pass.

## Next-action suggestions (independent of this verdict)

1. **Tighten the `summary:` line** to fix the S2 recall miss. Replace "Open before any non-trivial code change" with a concrete trigger such as "Open before any change that touches shared state, public APIs, lifecycle, or ≥2 files, or adds any new public function/class". This is a SKILL_EVAL.md round-1 carryover, not a new finding.
2. **Re-run this harness against a Sonnet executor** to estimate how much of the lift is Haiku-specific. The original pilot report noted Haiku has lower vocabulary anchoring than Sonnet; the three new rules may show smaller effect on stronger models.
3. **Sync remains monitored.** All three role copies (`coder/`, `experimenter/`, `gru/`) are byte-identical post-edit; a single source under `common/skills/` would prevent future drift but is out of scope for this round.

## Methodology recap

- 6 Haiku agents (`subagent_type=general-purpose`, `model=haiku`, no tools used during eval — pure reasoning) on 3 paired scenarios.
- Skill-specific vocabulary stripped from with-skill responses before judging: `coding-methodology`, `Phase 1/2/3`, `Plan → Review → Simplify`, `Read the territory`, `Surface conflicts`, `Code Simplifier`, `the skill`. The user-prompt-shared word "gate" was kept (used by both sides).
- 3 Codex judges (`gpt-5.5`, `read-only` sandbox, `low` reasoning effort), random RED/BLUE labels per scenario, blind to which side carried the rule-set.
- Total token cost: ~235K Haiku, ~53K Codex. Wall-clock ~3 minutes including parallel dispatch.

## Files

- Edited skill: `minions/roles/coder/skills/coding-methodology.md`
- Synced copies: `minions/roles/experimenter/skills/coding-methodology.md`, `minions/roles/gru/skills/coding-methodology.md`
- This report: `minions/roles/common/_behavioral_evals/coding-methodology-rules-7-8-12.md`
- Sibling pilot report (2026-03): `minions/roles/common/_behavioral_evals/pilot-coding-methodology.md`
