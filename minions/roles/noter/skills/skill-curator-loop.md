---
slug: skill-curator-loop
summary: On periodic wake, scan the Draft and recent EACN events for repeating success/failure patterns and emit a Skill / Agent evolution proposal via the global skill-curator skill. Output goes to branches/shared/library/skill-proposals.md for Ethics audit.
layer: meta-orchestration
tools: mos_draft_query, mos_draft_summary, Skill (skill-curator), Read, Write
version: 1
status: active
references: draft-maintenance, full-dream
provenance: human
---

# Skill — Skill-curator loop

Noter is the only Role with a structurally independent view of the project: it does not bid on tasks, does not author code, and runs on a different backbone from the decision-making roles. That independence is exactly what the proposal layer of the Skill family needs. This skill is how Noter periodically converts trajectory observations into evolution proposals.

The actual proposal logic lives in the global skill `skill-curator` (~/.claude/skills/skill-curator/SKILL.md). This file is the *trigger discipline* — when to call it, what to feed it, where the output goes, and what Noter MUST NOT do with the output.

## When to invoke

- On every full-dream wake (default daily) — always run a curation pass after draft-maintenance.
- On full-dream wake when the Draft has gained ≥10 new nodes since the last curation pass.
- On user request: "curate skills", "scan for new skills", "propose skill changes", "evolve skills", "audit Expert footprint".

Do NOT run during micro-dream. Curation needs the consolidated, post-maintenance Draft, not the in-flight version.

## Procedure

1. **Run draft-maintenance first.** Curation reads the Draft. A graph below 1.0 edge density gives noisy signal. If draft-maintenance reports unhealthy structure, fix it before curating.

2. **Build the trajectory window.** Collect:
   - `mos_draft_query(limit=10000)` — full graph since last curation pass.
   - The last 7 days of EACN events from `events/*.jsonl` (or since the previous proposal file, whichever is shorter).
   - The list of currently-registered Experts (`branches/main/state/role-registry.json` or via `mos_list_roles`).

3. **Invoke the global skill.** Call `Skill(skill-curator)` with the trajectory window as context. The global skill emits the proposal in its own schema. Do not paraphrase or pre-filter — the curator needs the raw window.

4. **Persist the proposal.** All paths below are **relative to the project root** (`project_{port}/`). Write the curator's output to:
   ```
   branches/shared/library/skill-proposals.md
   ```
   If a previous proposal file exists and is *unaudited* (Ethics has not yet processed it), append a new section dated for this pass rather than overwriting. Do not delete unaudited proposals.

5. **Notify Ethics.** Send a single EACN message to Ethics: "skill-proposals.md updated, N proposals pending audit." Cite the file path. Do not summarise the proposals — Ethics must read them independently.

6. **Stop.** Noter does not call skill-forge, does not modify the Library, does not retract proposals after sending. If a previous Noter pass made a bad proposal, the next pass can supersede it; Noter does not delete history.

## Pitfalls

- **Pre-filtering on Noter's own judgement.** The decorrelation principle requires Ethics to see the raw curator output. If Noter starts trimming "obviously bad" proposals before Ethics sees them, the audit gate degrades.
- **Running without draft-maintenance first.** A noisy Draft produces noisy proposals. Always run [[draft-maintenance]] in the same wake, before this skill.
- **Calling the global skill on a thin window.** If the Draft has fewer than ~10 new nodes since last pass, skip — the curator will reject sparse data anyway and the wasted call is paid context.
- **Auditing one's own proposals.** Noter must NEVER call `skill-evaluator` or `skill-forge` directly. The proposal hands off to Ethics; that is the entire interface.
- **Citing only Noter-observed events.** If every lineage entry comes from Noter's own messages, the curator's view is self-correlated. Prefer events from the Roles being curated (Coder, Writer, Expert).

## Output habit

Every proposal that Noter passes through must carry lineage from at least one *non-Noter* event. Mark this in the proposal block: `lineage_source: cross-role` (preferred) or `lineage_source: noter-only` (flag for Ethics caution).

This is Noter's only editorial intervention on the curator's output — labelling lineage independence so Ethics can weight the proposals accordingly.
