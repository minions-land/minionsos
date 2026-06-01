# `docs/` — contributor-facing design, research & integration notes

This directory is the **human, build-time** documentation layer: the *why* and
*how-it-was-decided* behind MinionsOS, read by contributors when changing the
code. It is deliberately distinct from the other documentation surfaces.

## Where each kind of documentation lives (audience × lifecycle)

| Surface | Audience | When read | Contents |
|---|---|---|---|
| **`docs/`** (this dir) | Contributors (humans) | While changing code | Design rationale, research/experiment writeups, third-party integration boundaries |
| **`MANUAL/`** | **Role agents** (runtime) | At wake, via `lookup.py` | Retrieval-shaped tool book — 134 tool pages, domain cards, pitfalls. Token-budgeted, machine-queried. Not prose. |
| **`dev-log/`** | Future maintainers | Post-hoc / when debugging | Session journals (`YYYY-MM.md`) + the upstream Claude Code changelog mirror (`claude-code-upstream-changelog.md`) |
| **root `*.md`** | External users / release | At release / onboarding | `README`, `CHANGELOG` (MinionsOS's own), `STABILITY`, `ERRORS`, `AGENTS`, `CLAUDE` |

**Rule of thumb:** if an agent needs it *at runtime to operate a tool*, it
belongs in `MANUAL/` (and is queried, not read whole). If a *human* needs it to
*understand or change* the system, it belongs here in `docs/`. Operational tool
reference is intentionally NOT duplicated here — `MANUAL/domains/` and
`MANUAL/tools/` are the single source of truth for that, queried via
`python3 MANUAL/scripts/lookup.py`.

## Contents

- **`reel-l0-memory.md`** — design of the L0 Reel memory layer (rationale, file
  layout, pain points, open questions). The runtime tool usage for `mos_reel_*`
  lives in `MANUAL/domains/memory.md`; this page is the design backstory.
- **`research/`** — empirical pilot studies that justify a design decision.
  e.g. `role-evolution-experiments.md` (the split/merge pilot whose findings
  back `minions/lifecycle/role_evolution.py`).
- **`integrations/`** — how MinionsOS depends on each external project
  (EACN3, Claude Code), the surface we consume, version locks, and
  fallback strategy. "Boundary, not fork."
