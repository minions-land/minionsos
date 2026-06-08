---
slug: skill-audit
summary: Audit a `skill-proposals.md` ledger before skill-forge admission; reads only the proposal plus its evidence lineage and emits accept/reject/held verdicts per proposal.
layer: logical
tools: Read, Write, Grep, Glob, mos_draft_query, mos_publish_to_shared, eacn3_send_message
version: 1
status: active
supersedes:
references: citation-authenticity-audit, evidence-pointer-sweep
provenance: human
---

# Skill — Skill Audit

Skills and Experts entering the project change *all future Role behaviour*. A
bad skill becomes a permanent contamination source; a wrongly spawned Expert
distorts the EACN labour market. This skill is the Ethics gate between the
proposal ledger and skill-forge admission.

## Position in the Skill family

```
branches/shared/notes/skill-proposals.md
                │
                ▼
        this skill (skill-audit)
                │
  accepted subset │ rejected / held subset
                ▼
       Gru enactment + skill-forge
                ▼
       Skill Library / Expert roster
```

Ethics is the **only** Role authorised to emit accept verdicts here.
skill-forge does not run on a proposal until Ethics has accepted that proposal.

## When to invoke

- When `branches/shared/notes/skill-proposals.md` changes and contains pending
  proposals.
- On user request: "audit skill proposals", "review the skill curation",
  "process skill-proposals.md".
- Before any project phase transition (Signboard checkpoint) where the current
  proposal file would otherwise be carried forward unaudited.

Skip when the proposal file is identical to a previously audited version
(compare hashes / line counts).

## Procedure

1. **Read the proposal file independently.** Open
   `branches/shared/notes/skill-proposals.md` directly. Do not rely on any
   accompanying EACN message body for context; the proposal must stand on its
   own.

2. **Verify lineage for every proposal.** For each `proposal-NNNN`:
   - Each cited event id must resolve in `events/*.jsonl` and contain content
     consistent with the rationale.
   - Each cited Draft node id must resolve in the current Draft
     (`mos_draft_query`) and match the claimed pattern.
   - Each cited artefact path must exist and be readable.
   - **Reject** any proposal where lineage does not resolve. Lineage gaps are
     the cheapest reward-hacking attack surface.

3. **Apply the per-op acceptance criteria.**

   | Op | Accept iff | Reject if |
   |---|---|---|
   | `add` (knowledge) | Lineage shows ≥3 distinct occurrences AND no existing skill covers the same trigger | Pattern occurs in <3 events, OR overlaps an existing skill that should be revised instead |
   | `revise` (knowledge) | Lineage points to a specific failure of the targeted skill | Rationale is generic ("could be clearer") with no failure event |
   | `merge` (knowledge) | Both skills' frontmatter triggers overlap ≥70%, verified by reading both files | Triggers differ in ≥30% of decision boundary |
   | `split` (knowledge) | Lineage shows the single skill firing on two distinct decision classes that have produced conflicting outputs | Only one decision class evidenced |
   | `drop` (knowledge) | Last-trigger date >N curation cycles AND no failure case is unique to the skill | Trigger fired recently or unique failure case found |
   | `spawn` (agent) | ≥3 task instances rejected/awkwardly handled outside any Expert's domain AND domain pack does not duplicate existing coverage | Domain overlap >50% with an existing Expert |
   | `dismiss` (agent) | Expert has no won bids or completed tasks in N cycles AND its domain coverage is fully replicated elsewhere | Any unique domain coverage remains |
   | `merge` (agent) | Two Experts bid on ≥80% of the same recent tasks | Bid patterns diverge in ≥20% |
   | `split` (agent) | Single Expert is producing quality issues attributable to mixing two methodologically incompatible domains | Quality issues have a different root cause |

4. **Run reward-hacking checks** on each proposal that survives lineage +
   per-op criteria:
   - **Token bloat**: would the new/revised skill add >2× the median Skill body
     length without proportional decision-quality evidence? Reject or downgrade
     to revise.
   - **Universal hedging**: does the proposed skill steer agents toward "always
     check with the user" or "consider all options"? Reject — those degrade
     decision quality without preventing failures.
   - **Trigger leakage**: does the proposed `description:` field contain
     phrasing too close to the eval probes? Reject; this is the recall stage
     gaming itself.
   - **Single-source lineage**: are >50% of lineage entries from one source,
     role, or process tag? Reject or hold for a second pass; correlation is too
     high.

5. **Emit the audit verdict.** All paths below are **relative to the project
   root** (`project_{port}/`).

   Write a per-pass summary file to
   `branches/shared/ethics/skill-audit-YYYY-MM-DD.md` and publish via
   `mos_publish_to_shared`. **Also append an inline
   `### audit (by ethics on YYYY-MM-DD)` sub-block under each proposal** in
   `branches/shared/notes/skill-proposals.md` so the proposals file remains a
   self-contained ledger.

   ```markdown
   ### audit (by ethics on YYYY-MM-DD)
   - verdict: accepted | rejected | held
   - reason: <one-line>
   - audit_path: branches/shared/ethics/skill-audit-YYYY-MM-DD.md
   ```

   The summary file schema:

   ```markdown
   ## audit-of-proposals-<filename>

   - **audited_at**: <ISO timestamp>
   - **proposals_total**: N
   - **accepted**: [proposal-YYYYMMDD-0001, proposal-YYYYMMDD-0003, ...]
   - **rejected**: [proposal-YYYYMMDD-0002 (lineage_gap), proposal-YYYYMMDD-0004 (token_bloat), ...]
   - **held_for_revision**: [proposal-YYYYMMDD-0005 (single-source lineage; add cross-role evidence)]

   ### Per-proposal record (rejected/held only — accepted entries don't need narrative)

   #### proposal-YYYYMMDD-0002 — REJECTED
   - **op**: add
   - **reason**: lineage_gap
   - **detail**: cited event evt-2026-05-19-014 not present in events/expert.jsonl; only events evt-..-013 and evt-..-015 exist
   - **next**: proposal owner to revise with verified evidence pointers
   ```

   **Auto-reject before semantic audit.** Before applying the per-op tables in
   step 3, scan the proposal's numeric fields against the proposal schema. Any
   proposal missing a required field, or violating its literal threshold (e.g.
   `trigger_overlap_pct: 65` on a `merge` proposal where the threshold is ≥70),
   is auto-rejected with `reason: schema_violation`. This step is mechanical —
   no judgement, no audit reading. It exists so Ethics never spends real
   attention on malformed proposals.

6. **Notify Gru.** Send a single EACN message to Gru, citing the audit file path
   and the accepted set. Gru routes accepted Knowledge-axis proposals into
   skill-forge and accepted Agent-axis proposals into the appropriate
   role-management calls.

7. **Stop.** Ethics does not run skill-forge directly, does not modify the
   Library, and does not edit Skill files. The audit verdict is the entire
   output.

## Decision rules

| Situation | Action |
|---|---|
| Lineage entry doesn't resolve | Reject the proposal regardless of how good the rationale sounds |
| Same proposal id rejected twice across different curation passes | Flag the repeated rejection in the audit summary and notify Gru |
| Proposal cites lineage from a contradiction page (book/contradictions or library/contradictions) | Treat as high-priority — these are pre-flagged hallucination signals already |
| Proposal `op: split` on the Agent axis | Require additional sign-off via Signboard before the audit verdict is binding — Agent-axis split is the most consequential operation |
| Audit reveals a Skill that Ethics itself authored a previous proposal on | Recuse Ethics' own previous reasoning; treat the proposal on its current lineage alone |

## Pitfalls

- **Relying on message framing for context.** The decorrelation principle
  requires Ethics to read the proposal independently.
- **Treating high proposal volume as suspicious in itself.** A long curation
  window will produce many proposals; what matters is whether each one
  resolves.
- **Approving a `merge` without reading both source skills.** Merges look cheap
  but a merged skill that loses one of the source's decision boundaries is a
  regression.
- **Approving an Agent `spawn` without checking domain-pack overlap.** Two
  Experts with 60% domain overlap degrade specialization and bidding clarity.
- **Letting accepted proposals accumulate without enacting.** Accepted but
  unenacted proposals are stale memory; if skill-forge has not run within N
  cycles of an accept verdict, escalate to Gru.
- **Auditing your own past audit verdicts as if they were ground truth.** A
  previous accept does not bind a future audit — if the same skill is proposed
  for revision, audit it on the current evidence, not on the path-dependent
  history of how it entered.

## Output habit

Mark every reject/hold record with `[evidence: <event_id|path>]` for the cited
deficiency. Accepted proposals do not need per-entry evidence in the audit file
— the proposal's own lineage carries that.
