# CLAUDE.md — MinionsOS V2 Root Constitution

> Towards Fully Autonomous Scientific Discovery: A Multi-Agent Workflow on the EACN Protocol.

This file is the authoritative guide for every agent and developer working in this repository. If any other document contradicts this file, this file wins.

## Layout

```
MinionsOS_V2/
├── EACN3/                       # git submodule — untouched; upgrade by replacing
├── minions/                     # MinionsOS Python package
│   ├── bin/gru                  # launcher script
│   ├── cli.py                   # `mos` CLI (argparse)
│   ├── gru/                     # Gru main loop, multi-IP scheduler
│   ├── tools/                   # MCP tools: project, spawn, relay, experiment_ssh
│   ├── roles/                   # Role SYSTEM.md templates
│   │   ├── gru/SYSTEM.md
│   │   ├── noter/SYSTEM.md
│   │   ├── coder/SYSTEM.md
│   │   ├── experimenter/SYSTEM.md
│   │   ├── writer/SYSTEM.md
│   │   ├── reviewer/SYSTEM.md
│   │   ├── ethics/SYSTEM.md
│   │   └── expert/SYSTEM.md     # base; domain pack appended at spawn time
│   ├── domains/                 # Expert domain packs (dl-arch, optimization, theory, nlp, cv)
│   ├── config/
│   │   ├── gru.yaml.example
│   │   └── experiment_targets.yaml.example
│   └── state/                   # runtime state (gitignored)
│       ├── projects.json
│       └── logs/gru.log
├── project_{port}/              # created by Gru at runtime (gitignored by pattern)
│   ├── CLAUDE.md                # project narrative (author + Gru write; roles read-only)
│   ├── meta.json                # machine fields; NO phase field
│   ├── workspace/               # git worktree on branch minionsos/project-{port}
│   ├── eacn3_data/eacn3.db      # per-project EACN3 backend DB
│   ├── artifacts/               # runtime artifacts
│   │   ├── notes/               # Noter summaries
│   │   ├── ethics/              # Ethics reports/ flags/open|resolved/ investigations/
│   │   ├── reviews/round-<n>/   # Reviewer outputs
│   │   ├── exp-{id}/            # Experimenter result bundles
│   │   ├── external_feedback/   # injected via project_revive
│   │   ├── checkpoint_<ts>.md   # Noter on dormant
│   │   └── final_summary.md     # Noter on close
│   └── logs/
│       ├── backend.log          # EACN3 backend subprocess
│       └── role-{name}.log      # each role subprocess
├── gru / minionsos / mos        # symlinks → minions/bin/gru
├── install.sh
├── pyproject.toml               # uv-managed
├── uv.lock
├── .gitignore
└── CLAUDE.md                    # this file
```

## Reader navigation

**If you are the author (human):**
- Run `./install.sh` once, then `./gru` to start.
- Use `./mos status`, `./mos logs`, `./mos doctor` for project management.
- See the Commands section below.

**Prerequisite — parent directory must be a git repo.**
MinionsOS creates per-project **git worktrees** branched off the directory
that *contains* `MinionsOS_V2/`. Before the first `project_create`, that
parent directory must be git-initialised, and `MinionsOS_V2/.git` must not
be treated as an embedded repo by it. `./install.sh` warns if this is
wrong; `./mos doctor` re-checks it. If you need to fix it by hand:

```bash
cd <parent of MinionsOS_V2>
# if MinionsOS_V2/.git is a plain directory and you are NOT using
# submodules, remove it so the parent can own it:
# rm -rf MinionsOS_V2/.git
git init
git add -A
git commit -m "init"
```

**If you are Gru:**
- Read this file, then `minions/state/projects.json`, then each active project's `CLAUDE.md`.
- Your role definition is in `minions/roles/gru/SYSTEM.md`.
- You are the only agent allowed to use `gru_relay` and `project_*` tools.

**If you are a Role (Noter, Coder, Experimenter, Writer, Reviewer, Expert, Ethics):**
- Read this file for hard rules, then your own `minions/roles/{role}/SYSTEM.md` for role-specific behavior.
- Read the project `CLAUDE.md` (in `project_{port}/CLAUDE.md`) for project context.
- Communicate only via EACN3 (`eacn3_*` tools). Do not make direct HTTP calls to the EACN3 backend.

## Hard rules

### 1. EACN3 is untouched

The `EACN3/` directory is a git submodule treated as a dependency. No MinionsOS code edits files inside `EACN3/`. To upgrade EACN3, replace the submodule. All EACN3 operations go through `eacn3_*` MCP tools — never handcrafted HTTP calls.

### 2. Python environments use uv only

All Python environment management uses `uv`. Do not use `pip` directly, `conda`, `mamba`, `virtualenv`, or bare `python -m venv` in any workflow step. The root `pyproject.toml` is managed by `uv`; run `uv sync` to install.

### 3. IP isolation via gru_relay

Each project runs its own EACN3 backend on a dedicated port. Roles on one project cannot contact roles on another project directly. The only cross-project path is `gru_relay(from_port, to_port, content, mode)`, which only Gru may call.

### 4. Subagent tool whitelists

| Agent | eacn3_* | exp_* | gru_relay / project_* / spawn_* | workspace write | web search |
|---|---|---|---|---|---|
| Gru main | yes | no | yes | yes | yes |
| Gru subagent | no | no | no | yes | yes |
| Noter main | yes | no | no | artifacts/notes only | yes |
| Noter subagent | no | no | no | no | yes |
| Coder main | yes | no | no | yes | yes |
| Coder subagent | no | no | no | yes | yes |
| Experimenter main | yes | yes | no | yes | yes |
| Experimenter subagent | no | yes | no | yes | yes |
| Writer main | yes | no | no | yes | yes |
| Writer subagent | no | no | no | yes | yes |
| Expert main | yes | no | no | yes (soft: read mostly) | yes |
| Expert subagent | no | no | no | yes (soft) | yes |
| Reviewer main | yes | no | no | artifacts/reviews only | yes |
| Reviewer subagent | no | no | no | no | yes |
| Ethics main | yes | no | no | artifacts/ethics only | yes |
| Ethics subagent | no | no | no | no | yes |

These whitelists are enforced via `--allowed-tools` on spawn. Do not circumvent them.

### 5. Noter and Reviewer are read-only on workspace

- **Noter** may read `workspace/` but may not write to it. Writes go to `artifacts/notes/` only.
- **Reviewer** may read `workspace/` but may not write to it. Writes go to `artifacts/reviews/round-<n>/` only.

### 6. Event-driven Role lifecycle

Roles (Noter, Coder, Experimenter, Writer, Reviewer, Expert, Gru-per-project) are **ephemeral**. No Role runs a long-lived Claude process and no Role runs an in-Claude polling loop. A Python-level dispatcher (`minions.lifecycle.wakeup.WakeupScheduler`) polls EACN3 on the cadence configured via `gru.yaml: poll_interval_default` (allowed: `1m` / `3m` / `5m`; per-role override at registration time). When events arrive for a Role, the dispatcher launches a short-lived Claude subprocess seeded with that Role's `SYSTEM.md` and the event batch. The Role's job is **receive events → act → exit**; empty polls cost zero Claude context. Registration is done by Gru via `spawn_role` / `spawn_expert` (now registry-only); the cadence is persisted to `projects.json` so revived Roles retain it.

### 7. EACN visibility boundary — only Gru spawns EACN agents

Only Gru may spawn EACN-visible agents (Noter / Coder / Experimenter / Writer / Reviewer / Expert mains). Every subagent spawned by a Role, and every member of a Claude-CLI Agents Team running inside a Role's process, is **EACN-invisible** by design: they do not hold `eacn3_*` tools, they do not appear in `projects.json`, and they do not address other Roles directly. The boundary is mechanism-level — it is what keeps EACN's bus from becoming a free-for-all — so the whitelists in §4 encode it and must not be circumvented.

The intended division of labor (soft, not enforced): EACN-visible agents **coordinate and dispatch**; subagents and team members **do the heavy lifting** (code writing, paragraph drafting, literature scans, experiment scripts, review subspect analysis). Roles may still do small scratch work directly, but should prefer dispatching non-trivial production to subagents. This is a strong convention, not a hard rule — the system's autonomy is preserved.

### 8. Idle time is working time (soft)

When a Role's poll loop returns nothing, or when long-running external work (experiments, external feedback, remote reviews) has the team blocked, Roles are expected to dispatch short, bounded idle work rather than sit passive: `/simplify`-style passes on code / drafts / hypotheses, baseline-freshness checks, competitor survey refreshes, small self-audits. Gru may also push idle tickets proactively. Idle tasks stay small (roughly one subagent cycle) so real EACN events are not starved, and must not start new scientific directions, launch new experiments, or trigger new review rounds. See each Role's `Idle-time productive work` section for specifics.

### 9. Evidence-first communication (soft)

EACN messages from Roles that make substantive claims SHOULD carry an evidence marker:

- `[evidence: <artifact path | commit SHA | URL | EACN event id>]` — a concrete pointer.
- `[speculation]` — the claim is explicitly unverified.
- `[derived: <base>]` — a deduction from an already-evidenced base; name the base.

Unmarked substantive claims default to `[speculation]` and may be flagged by Ethics. Evidence can be gathered via web search / web fetch / artifact reading / code reading / EACN history. This is a **soft convention**, not a mechanical format checker: Ethics runs statistical audits of unmarked-claim ratios per Role; a single missed marker is not a violation, but persistent offenders get flagged. The goal is a culture of evidence, not bureaucracy. The rule applies to **all** Roles including Ethics itself — Ethics' own reports and flags must cite concrete evidence (artifact paths, URLs, EACN event ids).

## Common role conventions

These apply to every non-Gru Role. Individual `SYSTEM.md` files only note role-specific deviations.

- **Phase vocabulary (not a state machine).** Phase words (Scheduling, Plan, Discussion, Experiment, Writing, Review, Rebuttal, Camera-ready, Closed) are suggestive vocabulary used in team communication. They are not enforced states.
- **Dormant / revive awareness.** You are invoked from a cold start every time. Reconstruct context from recent EACN history and role-relevant on-disk artifacts; do not assume any in-memory state survived from a previous invocation.
- **Idle-time productive work.** When an event batch has nothing genuinely actionable, prefer to dispatch a short, bounded subagent task (≤ ~10 min, one subagent cycle) rather than idle. Keep tasks small so real EACN events are not starved; do not start new scientific directions, new experiments, or new review rounds on idle time. Role-specific examples live in each Role's own file.
- **Tool access.** Your tool access is governed by §4 of this constitution and enforced via `--allowed-tools` on invocation. Do not assume access to tools not listed there.
- **Skills.** Each Role may ship a `minions/roles/{role}/skills/` directory of methodology / procedure files. On wake-up, the list of available skills (slug + one-line summary) is injected into your init message as a `[Skills]` block. Read a skill file in full before applying it — summaries are navigational, not a substitute. Skills apply to the ~20% of tasks where framing or procedure matters; routine actions do not need them. New skills may be added over time; discovery is automatic, so never hard-code a fixed skill list in role behavior.

### Layered memory

Because Roles are ephemeral (§6), each invocation is a cold start. Memory is organized in four layers:

- **L1 — Transcript.** The current Claude session only; evaporates on exit.
- **L2 — Scratchpad.** Per-Role persistent working memory at `project_{port}/memory/{role}.md`. This is *your* working memory — in-flight tasks, tentative hypotheses, unresolved questions, judgement cues not worth a formal artifact.
- **L3 — Artifacts + EACN.** Team-shared facts: `artifacts/notes/`, `artifacts/reviews/`, experiment bundles, EACN message history.
- **L4 — CLAUDE.md.** Institutional rules (this file) and per-project `CLAUDE.md`.

Wake-up convention: **first action** is to read your scratchpad. **Final action before exit** is to update it with only what future-you needs — remove stale entries, never dump transcripts. Free-form markdown; no rigid schema.

Size discipline (enforced Python-side in `minions/lifecycle/wakeup.py`, rough estimator `len(text)/4`, ±20%). Thresholds are percentages of the model context window so they auto-scale when the underlying model changes; defaults computed against a 1M-token window:

- **Soft — 10% of context window (100k tokens @ 1M)** — wake-up hints that compression is due when convenient.
- **Hard — 15% of context window (150k tokens @ 1M)** — wake-up requires you to compress the scratchpad **before** processing new events.
- **Veto — 20% of context window (200k tokens @ 1M)** — wake-up refuses to spawn and notifies Gru; events remain in EACN for the next tick.

Compression is a **plain subagent task**: "read the scratchpad at `<path>`, output a condensed version retaining only future-relevant entries, write it back." No slash command.

## Commands

```bash
# Install (once)
./install.sh

# Launch Gru (interactive)
./gru
# or equivalently:
./minionsos
./mos

# Project management
./mos status                        # dashboard of all projects
./mos status --json                 # machine-readable
./mos logs --project 37596          # logs for a project
./mos logs --role noter --tail 50   # tail a role log
./mos doctor                        # check uv / node / git / EACN3 / port-bind
./mos config                        # print config paths
./mos project list
./mos project close 37596
./mos project revive 37596
./mos role list 37596
./mos role dismiss 37596 noter
```

## Debug entry points

| What broke | Where to look |
|---|---|
| Gru itself | `minions/state/logs/gru.log` |
| EACN3 backend for a project | `project_{port}/logs/backend.log` |
| A specific role | `project_{port}/logs/role-{name}.log` |
| Role crash loop | Check log for 3-crash threshold; Gru marks role dismissed |
| Backend crash loop | Check `backend.log`; 3 crashes in 1h → Gru notifies author, stops auto-restart |
| Experiment failure | `artifacts/exp-{id}/report.md`; circuit-break after 3 consecutive same-script failures |
| EACN3 state | `project_{port}/eacn3_data/eacn3.db` (SQLite) |
