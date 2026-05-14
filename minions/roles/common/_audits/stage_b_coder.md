# Stage B Coherence — coder cluster (7 skills)

## Bucket summary

| Skill | Bucket | Confidence |
|---|---|---|
| bounded-repair-loop | COHERENT | high |
| build-playground | COHERENT | high |
| feature-implementation | NEEDS POLISH | medium |
| silent-failure-audit | COHERENT | high |
| static-type-check | COHERENT | high |
| test-coverage-review | COHERENT | high |
| type-design-review | COHERENT | high |

Counts: COHERENT 6, NEEDS POLISH 1, NEEDS REWRITE 0, STITCHED-TOGETHER 0.

## Per-skill verdicts

### coder/bounded-repair-loop — COHERENT

**Evidence:**
- Summary: "Iterate on a failing local check in a controlled diagnose-fix-verify loop with a fixed iteration bound".
- Pitfall: "Resetting the iteration counter after a partial pass to 'give it one more try' — the bound exists precisely to prevent this drift".

**Diagnosis:** One trigger (a local check fails deterministically), one core move (bounded diagnose-fix-verify with a hard iteration cap). Structure names three gates; Procedure walks exactly those gates; Pitfalls target the failure modes specific to this loop (counter reset, scope creep into Experimenter territory, hiding failure). The "GPU jobs / sweeps belong to Experimenter" carve-out appears in both When-to-invoke and Pitfalls — slight repetition, but it reinforces the same boundary, not a different topic. Voice is consistently procedural throughout.

**Action:** None.

### coder/build-playground — COHERENT

**Evidence:**
- Summary: "Build a self-contained interactive HTML explorer (controls + live preview + generated config) when visual configuration is hard to express in text".
- Structure: "One HTML file with embedded CSS and JS. Three surfaces: real controls ... a live preview ... and a copyable generated prompt or configuration".

**Diagnosis:** Sharp single purpose. Trigger (visual or structural choice prose can't pin down) maps cleanly to the artifact (one HTML file with three surfaces). Procedure is what you'd actually do given that trigger: pick target, pick path, make self-contained, expose controls, show live output, handle production handoff. Pitfalls are pitfalls *of building this kind of artifact* (marketing page, decorative visuals hiding state, treating prototype as production). No drift.

**Action:** None.

### coder/feature-implementation — NEEDS POLISH

**Evidence:**
- Structure: "Smallest viable implementation in Coder-owned paths. **Five phases**: read the task, explore precedent, choose architecture, implement, verify, simplify, hand off."
- Procedure has seven numbered steps (`1. Read the task ... 7. Handoff with evidence`).

**Diagnosis:** Single coherent purpose (translate accepted feature task into a small integrated implementation). The trigger, procedure, and pitfalls cooperate on that one story. The defect is internal counting: Structure announces "Five phases" then lists seven items, and the Procedure delivers seven numbered steps. Also, the "Adding an abstraction is justified only when..." sentence in Structure is then re-stated almost verbatim as Procedure step 3 — duplication rather than build-up. Not stitched-together; just sloppy where the skill is otherwise tight.

**Action:** Polish, not rewrite. Either (a) change Structure to "Seven phases" matching the Procedure, or (b) collapse Procedure to five real phases and fold "simplify" + "handoff" into "verify" / final reporting. Either way, drop the duplicated abstraction sentence from Structure and let it live only in step 3.

### coder/silent-failure-audit — COHERENT

**Evidence:**
- Summary: "Audit error paths for honesty — find places where errors are swallowed, downgraded, or converted into misleading success".
- Structure introduces a tight three-way classification: "**verified** ... **patched** ... or **accepted fallback**".

**Diagnosis:** One trigger (error-path-touching changes, or a Reviewer/Ethics/Gru honesty question), one core move (classify each fallback). Procedure walks search → classify → check observability → preserve useful tolerance → patch → verify negative path → report — every step feeds the classification. Pitfalls target audit-specific anti-patterns (over-tightening, secret leakage in diagnostics, raising in cleanup). Voice consistent.

**Action:** None.

### coder/static-type-check — COHERENT

**Evidence:**
- Summary: "Use Python type information to catch contract drift before runtime — coherent public types, honest None handling, structured state/config in sync".
- Procedure: "**Prefer configured tools.** Run `uv run ty check minions` ... against the narrowest useful scope first."

**Diagnosis:** Tightly scoped to "run the type tool against the local change surface". Trigger (shape-mismatch-smelling changes), core move (run `ty`, check boundary conversions, fix real mismatches). Pitfalls cover the right anti-patterns: type checks as test substitute, broad `Any`/ignore noise, unauthorized tooling install, persisted-state drift. Distinct from `type-design-review` (which is about invariants); the references frontmatter acknowledges the neighbor without bleeding into it.

**Action:** None.

### coder/test-coverage-review — COHERENT

**Evidence:**
- Tagline: "One focused behavior test beats chasing line coverage."
- Pitfall: "Testing implementation details instead of observable behavior."

**Diagnosis:** One purpose, consistently delivered. Structure names a priority gap order (lifecycle transitions → persisted state → role boundaries → EACN payloads → config defaults → CLI behavior → dashboard read-only). Procedure carries that priority through. The fake-launcher detail (`MINIONS_FAKE_CLAUDE=1`, fake Codex binaries) is concrete project context, not tangent — it answers a real question Coder would have when adding tests for agent-host paths. Pitfalls all reinforce "behavior over lines, fast over slow, no machine-state coupling".

**Action:** None.

### coder/type-design-review — COHERENT

**Evidence:**
- Tagline: "A good type makes invalid states hard to create and easy to detect at project boundaries."
- Structure verdict scheme: "`strong` ... `adequate` ... `convention-only` ... or `unsafe`".

**Diagnosis:** One trigger (changed types at a real boundary), one core move (verdict per type on invariant enforcement). Procedure walks exactly that: identify boundary → name invariants → check enforcement → check serialization → simplify → patch → report. Pitfalls are correctly *type-design* pitfalls (theoretical elegance, breaking persisted state without migration, secrets-in-repr, `Any` hiding uncertainty), not generic dev advice. Cleanly distinct from `static-type-check`: this one is design-side (do the types encode invariants), the other is enforcement-side (does the type checker complain).

**Action:** None.

## Cross-cutting observations

1. **Common template is well-applied.** All seven follow the same H1 → tagline → When to invoke → Structure → Procedure → Pitfalls shape. The shape doesn't feel forced anywhere.
2. **The three "review-flavored" skills do not collapse into each other.** `static-type-check` (run the tool), `type-design-review` (invariant verdicts), and `test-coverage-review` (behavioral coverage gaps) each have a distinct trigger and a distinct artifact. The frontmatter `references:` chain (static-type-check ↔ type-design-review; test-coverage-review ↔ feature-implementation; silent-failure-audit ↔ test-coverage-review) reads as deliberate cross-linking rather than overlap-by-accident.
3. **No 缝合怪 in this cluster.** Nothing reads as 2-3 skills duct-taped under one slug; nothing has an out-of-character philosophical aside; no "if A do this, if B do that" branching where the branches should be separate skills.
4. **One small numbering inconsistency** in `feature-implementation` ("Five phases" vs seven procedure steps and seven items in the same Structure sentence). This is the only place a section visibly drifts from another section in the same file.
5. **Boundary discipline is consistent.** Five of seven skills explicitly carve out non-Coder territory (no GPU/sweep work; no Writer/Reviewer/Ethics artifacts; no productionizing prototypes; no live external services in tests; no unauthorized tooling install). That repetition is a feature, not stitching — it is the same boundary applied to different procedures.
