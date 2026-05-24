# 09 — Deliverables: submit, evaluate, adjudicate, review

> **L2 card.** All four are **Gru-only**. Other roles surface a deliverable to Gru by EACN message; Gru calls these tools.
> Top three: `mos_submit` (persist), `mos_evaluate` (score), `mos_review_run` (peer review for paper profiles).

---

## mos_submit (Gru)

Persist a deliverable under `branches/shared/submissions/`.

```python
args:
  port: int
  payload: dict | str          # the actual deliverable content
  kind: "answer" | "paper" | "patch" | "report"
  metadata: dict | None
returns: { submission_path, kind, sha }
```

**Per-profile destination:**
- `kind="answer"` → `submissions/answer.json`
- `kind="paper"` → `submissions/paper.pdf` (+ source bundle)
- `kind="patch"` → `submissions/patch.diff`
- `kind="report"` → `submissions/report.md`

The submission directory is reserved — no role may write there directly. Gru is the only authoriser.

---

## mos_evaluate (Gru)

Run the project's profile-defined evaluation strategy.

```python
args:
  port: int
  rounds: int | None           # default from profile.evaluation.default_rounds
returns: { score, verdict, details }
```

**Strategies (set in `minions/profiles/<name>.yaml`):**

| Strategy | What | When |
|---|---|---|
| `scientific_peer_review` | Delegates to `mos_review_run` | `scientific-paper` profile |
| `answer_grader` | Compares `submissions/answer.json` to `input/expected.json` | `hle-answer` profile |
| `test_runner` | Runs project test suite | reserved (SWE-bench) |

**Adjudication gate.** If the profile sets `evaluation.adjudication.depth ∈ {single, panel}`, `mos_evaluate` first calls `mos_adjudicate` and only fires the grader if it returns `decision=Accept`.

---

## mos_adjudicate (Gru)

Pre-evaluation answer audit.

```python
args:
  port: int
  depth: "single" | "panel" | None     # default from profile
returns: { decision: "Accept"|"Revise"|"Reject", confidence, evidence_refs }
```

Spawns 1 (single) or 3 (panel) independent adjudicator instances that audit reasoning, search counterexamples, check self-consistency.

**Pitfall (PITFALLS § P-4):** `mos_adjudicate` is NOT for mid-project per-task closure. It expects `submissions/answer.json` to exist. Trying to adjudicate "pending events" mid-run errors out.

**Required state:** a previous `mos_submit(kind="answer", ...)` call must have run.

---

## mos_review_run (Gru) — peer review for paper profiles

```python
args:
  port: int
  round_number: int                 # 1, 2, 3, ...
  use_prior_history: bool = True    # injected only on Pass B/C
returns: {
  packet_path: str,
  reviewer_instance_count: int,
  consolidated_path: str,
  summary_path: str,
}
```

**Pass structure (enforced by review skills):**
- **Pass A** — 3-5 independent reviewer instances simulate fresh reviews. Must NOT read prior review history. Each is its own subagent (Codex or Sonnet) with a different persona.
- **Pass B** — aspect reviews (math, code-validity, baselines, threats-to-validity). Reads prior summary only.
- **Pass C** — revision-delta + finalize.

**Output goes to `branches/shared/reviews/round-<n>/`.** This subdir is reserved; `mos_publish_to_shared` will reject any other writer.

---

## Real example (project_37596 currently in P2)

The project hasn't reached the writing phase yet. When it does:
1. Writer is on-demand: Gru calls `mos_spawn_role(role="writer")`.
2. Writer drafts paper into `branches/writer/paper/`.
3. Writer DMs Gru with submission ready.
4. Gru calls `mos_submit(port=37596, kind="paper", payload=...)`.
5. Gru calls `mos_review_run(port=37596, round_number=1)`.
6. Writer reads `reviews/round-1/summary.md`, revises, repeats.
7. Final round: `mos_evaluate(port=37596)` returns the peer-review verdict.
