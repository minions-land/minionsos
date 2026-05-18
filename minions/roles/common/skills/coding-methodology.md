---
slug: coding-methodology
summary: Three-phase coding pipeline — Plan → Review → Simplify — each gated by a fixed smoke test. Open for changes touching shared state, public APIs, lifecycle, ≥2 files, or adding a public function/class.
layer: logical
tools:
version: 3
status: active
supersedes: coding-discipline, change-review, simplify-changes
references: bounded-repair-loop, feature-implementation, test-coverage-review
provenance: human
---

# Skill — Coding Methodology

Three phases for writing code that works and stays clean. You decide which
to use, how many, and in what order. The default sequence below is a
recommendation for non-trivial changes — not a mandatory pipeline.

## When to consider this skill

- The change touches shared state, public APIs, lifecycle, or more than one file.
- The edit changes more than 20 lines in one module.
- You are about to dispatch a non-trivial subagent.
- You are tempted to "just refactor this quickly while I'm here."
- The request has multiple reasonable interpretations.

**Skip entirely** when the task is a single-file, single-function edit with
no caller impact: comment fixes, typo corrections, isolated one-line bug fixes.

**User intent wins.** If the user explicitly limits scope ("just implement,
don't clean up"), respect that. The phases are available, not mandatory.

## The three phases (your toolkit)

| Phase | File | Use when | Skip when |
|---|---|---|---|
| **Plan** | `coding-methodology/coding-plan.md` | You need to decide HOW before writing code | Spec is concrete with file path + acceptance already stated |
| **Review** | `coding-methodology/coding-review.md` | Code is written and needs self-review before declaring done | Trivial change where the gate alone is sufficient verification |
| **Simplify** | `coding-methodology/coding-simplify.md` | Code works but could be cleaner | User said "don't clean up" or the diff is ≤5 lines |

Each phase is a sibling file under `coding-methodology/`. Read the
relevant phase file when you decide to use it. Phase files are NOT
listed as standalone skills in `[Skills]` — they are progressive
disclosure reachable only after this orchestrator is chosen.

## Default recommendation (not mandatory)

For non-trivial code changes where you genuinely need all three:

1. **Plan** — decide how to write the code before writing it
2. **Review** — implement, then self-review the diff
3. **Simplify** — focused cleanup on code that already works

This is a pipeline: each phase's exit gate must pass before advancing.
But this is ONE way to use the toolkit.

## Other valid patterns

- **Just Plan**: Task is ambiguous; once the plan is clear, implementation is trivial.
- **Just Simplify**: Code already works and was accepted; user asks for cleanup pass.
- **Plan → Review**: Standard implementation without cleanup (user said "don't simplify").
- **Review only**: You inherited code from a subagent and need to verify it before committing.
- **Skip all three**: Single-line fix, comment correction, typo. Just do it.

The agent decides. The skill does not decide for you.

## The gate (shared across all phases)

```bash
ruff check <changed_paths>
ruff format --check <changed_paths>
ty check <package>          # or mypy / pyright if the project uses those
pytest tests/unit/ -q       # the fast local suite
```

All four must pass before advancing to the next phase. If any fails, fix first.

**Fail loud, don't fail silent.** A skipped test, a tool not installed, a
command not run, a check that timed out — none count as passing. Name which
check could not run and why.

## Pitfalls

- Skipping Plan because the task feels obvious — the obvious ones are where assumptions hide.
- Adding code in a file you have not read this session.
- Declaring Review done without running the gate. "It looks right" is not a gate pass.
- Reporting "tests pass" when one of the four commands was skipped or errored.
- Simplify changing behavior under the banner of "cleanup." The gate catches this, but only if you run it.
- Treating the three phases as ritual. They are judgment heuristics, not a checklist to rush through.
