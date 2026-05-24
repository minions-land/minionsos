# 14 — Role evolution (Gru only)

> **L2 card.** Roles aren't fixed. Gru can SPLIT a strained role, MERGE two converging roles, or DISMISS a starved role. **Evidence-gated, audit-logged, recommend-only by default.**
> Top three: `mos_role_evolve_evaluate` (read-only), `mos_role_split`, `mos_role_evolve_dismiss`.

---

## mos_role_evolve_evaluate (read-only)

```python
args:
  port: int
returns: {
  splits: [ SplitDecision { role, sub_specialists, evidence_refs, confidence } ],
  merges: [ MergeDecision { role_a, role_b, convergence_score, evidence_refs } ],
  dismisses: [ DismissDecision { role, starvation_score, evidence_refs } ],
}
```

**Triggers (defaults from `gru.yaml`):**

| Action | Trigger |
|---|---|
| **SPLIT** | ≥ 5 attributable failures partitioned into ≥ 2 labeled subdomain clusters, each ≥ 3 large |
| **MERGE-by-convergence** | Pair of active roles with Jaccard(artifact basenames) + dir-prefix overlap ≥ 0.75 |
| **DISMISS-by-starvation** | Role active ≥ 6 h with ≤ 1 task in window |

**Cooldowns** (no re-eval after action):
- SPLIT: 12 h
- MERGE: 6 h
- DISMISS: 6 h

The Gru loop runs `_evaluate` every 15 min and **only logs recommendations** unless `gru.yaml: role_evolution_auto_apply: true`. Default is recommend-only.

---

## mos_role_split

Realise a SPLIT.

```python
args:
  port: int
  role: str                          # the source role to split
  sub_specialists: list[dict]        # each: { name, domain, config? }
  evidence_refs: list[str]           # MUST be non-empty
  reason: str
returns: {
  spawned: list[str],
  source_dismissed: bool,
  audit_log_entry: str,
}
```

**Failure mode protection.** If any `sub_specialist` spawn fails, the source role is **kept alive** to preserve coverage. Source dismissal only happens after all spawns succeed.

**Project_37596 example (real but minimal):**
```python
# Hypothetical: Coder is failing on math-derivation tasks 6/8 times
mos_role_split(
  port=37596,
  role="coder",
  sub_specialists=[
    {"name": "coder-experimentation", "domain": "minions/domains/coder-exp.md"},
    {"name": "coder-derivation",     "domain": "minions/domains/derivation.md"},
  ],
  evidence_refs=[
    "branches/shared/exp/exp-abc/result.json",
    "branches/shared/handoffs/coder-failure-trace-2026-05-23.md",
    # ... 5+ refs total
  ],
  reason="Coder is bottlenecking on derivation-heavy tasks; 6 of 8 P1 derivation handoffs flagged needs-revision.",
)
```

---

## mos_role_merge

Realise a MERGE — convergence-driven only.

```python
args:
  port: int
  role_a: str
  role_b: str
  unified_role: dict                # { name, domain, config? }
  evidence_refs: list[str]
  reason: str
returns: { spawned, dismissed: [role_a, role_b], audit_log_entry }
```

**Hard rule.** MERGE applies only to roles whose artifacts genuinely overlap (Jaccard ≥ 0.75 by default). Two independently-spawned Experts with overlapping scope → MERGE. Two roles that never collaborated → never MERGE; pick one and DISMISS.

Source roles do **not** need to share a SPLIT lineage.

---

## mos_role_evolve_dismiss

Retire a Role with no recent work. Distinct from generic `mos_dismiss_role`:
- Requires non-empty `evidence_refs`.
- Writes to the role-evolution audit log.
- **No replacement is implied.** If new work appears later that no active Role can cover, that triggers a separate spawn — not a re-spawn of the dismissed role.

```python
args:
  port: int
  role: str
  evidence_refs: list[str]            # starvation evidence: thin task list, idle hours
  reason: str
returns: { dismissed: bool, audit_log_entry }
```

---

## Audit trail

Every `_evaluate` recommendation and every `_split` / `_merge` / `_evolve_dismiss` apply writes one line to:
```
branches/shared/governance/role_evolution.jsonl
```

When auditing the Gru's decisions, this is the file to read. Lines look like:
```json
{"ts":"2026-05-24T15:00:00Z","action":"recommend","kind":"split","role":"coder","evidence":[...]}
{"ts":"2026-05-24T15:30:00Z","action":"apply","kind":"split","spawned":["coder-exp","coder-deriv"],"source_dismissed":true,...}
```

---

## Pitfalls

- **Don't apply auto.** Default is recommend-only for a reason — false-positive splits oscillate the team.
- **Cooldowns are real.** A role just evolved can't be re-evaluated for 6-12 h.
- **DISMISS ≠ MERGE.** A role with no work doesn't get fused into another role's scope. It gets retired.
- **`evidence_refs` are non-negotiable.** The tool rejects empty lists. Cite paths under `branches/shared/`, EACN event IDs, or commit SHAs.
