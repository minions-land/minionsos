# Changelog

All notable changes to MinionsOS are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

**Versioning.** The `vN` milestone tag used in commit messages maps one-to-one
to the package minor version: milestone `vN` ⇒ pyproject `0.N.x`, and a `vN.M`
polish commit ⇒ `0.N.M`. The single source of truth is
`pyproject.toml [project].version`; `minions.__version__` reads it from package
metadata. (Historical note: entries below `0.5.x` predate this convention, when
the `vN` commit tags and the frozen `0.5.x` package version were decoupled.)

---

## [0.20.0] - 2026-05-30 (current)

Milestone `v17`–`v20`. Package version realigned with the `vN` milestone series
(see Versioning above): the `0.5.x`-frozen-while-commits-ran-to-`v16` drift is
resolved — `v20` ⇒ `0.20.0`.

### Added
- Per-role `SYSTEM.md` + role skills; `Workflow` tool coverage for role workflows (v17)
- Scratchpad isolation infra; role-launcher hard-fails on a bad cwd (v17)
- `mos restart` primitives — cold-restart Role tmux sessions and the Gru monitor
  sidecar so `mos upgrade` reaches already-running processes (v19)
- CI type gate: `uv run ty check minions` (v19)
- `docs/README.md` — documents the doc-layer boundary (docs = contributor, MANUAL
  = agent runtime, dev-log = journal, root `*.md` = release) (v20)

### Changed
- Hermetic Role cwd is now **default-ON** — the structural disclosure boundary.
  Role processes launch from `~/.minionsos/role-cwd/` (outside the repo) with a
  terminating `CLAUDE.md` stub, so Claude Code's automatic cwd-walk can no longer
  reach repo or host dev docs. Opt out with `MINIONS_ROLE_HERMETIC_CWD=0`, which
  now emits a pre-flight WARNING. Gru stays non-hermetic by design (control
  plane). (v20.14)
- Root `CLAUDE.md` rewritten 344→49 lines: a minimal pointer (what it is /
  install / "MANUAL is the handbook" via `lookup.py` / the one Opus tool-use
  rule / where to look when broken). `MANUAL/` is the throughline, not an index. (v20.14)
- Common role contract: Plan→Workflow→Verify + §10.1; per-role skills (v17)
- Dispatch tests/audit aligned to the v17 Workflow contract; paper-writing CNS
  skill upgrades (v18)
- `uv.lock` registry switched from the aliyun mirror back to pypi.org (v16)
- Book retrieval is body-aware (BM25 over page bodies); tighter contradiction
  detector subject filter (v19)
- Draft decay confidence driven by weighted reinforce/accelerate edge relations
  rather than raw supports/contradicts counts (v19)
- `install.sh` incremental rebuild keyed on source-tree hash; model binding
  defaults to `claude-opus-4-8[1m]`; `role_ultracode` passthrough (v19)
- Single version source of truth: `minions.__version__` now reads package
  metadata instead of a hard-coded literal (v20)

### Fixed
- Role disclosure leak: in the previous non-hermetic default, Claude Code's
  `CLAUDE.md` cwd-walk ascended from a Role's in-repo branch worktree through
  project `CLAUDE.md`, root `CLAUDE.md`, and `~/.claude/CLAUDE.md`, pulling
  dev/host docs into every Role's context — bounded only by an advisory
  "treat as dev documentation" header. Now bounded structurally by the
  default-ON hermetic cwd; CI smoke test pins that a launched Role's cwd is
  outside `MINIONS_ROOT` and the stub terminates the walk. (v20.14)
- Gru-monitor watchdog drift: production sidecar (`run_async`) silently started
  only 1 of 7 watchdogs; both entrypoints now share `_start_watchdog_threads`
  and `main()` drives the complete `run()` path (v19)
- `CrashCounter` now persists to disk (wall-clock timestamps) so the ≥3-in-1h
  crash guard survives a `mos upgrade` monitor restart (v19)
- Bounded `timeout=` on all supervision-critical tmux subprocess calls so a
  wedged tmux server can no longer hang a watchdog thread (v19)
- `test_doctor_checks` no longer hangs the suite — runs against a hermetic
  `MINIONS_ROOT` instead of probing every live backend over HTTP (v19)

### Removed
- `MARKDOWN_INDEX.md` + `MODULE_PATH_INDEX.md` — navigation-patch index files
  (and the test forcing every root `.md` into the index). The root is now
  self-explaining; `MANUAL/` is the handbook. (v20.14)
- Root `AGENTS.md` — Gru hosts on Claude Code, not Codex; the per-project
  `AGENTS.md` runtime shim is a separate file and is untouched. (v20.14)
- Unwired `agent_host/` quota/telemetry prototype + its orphan test (v20)
- Stale `docs/eacn3-mcp-tools-reference.html` (superseded by MANUAL) (v20)
- `outline/` 21GB research/dataset workspace relocated out of the repo
  (gitignored; was never pushed) (v20)

---

## [0.5.3 → 0.16.x equivalent] - 2026-05-16 (the `v6`–`v16` patch series)

> **Historical framing.** During this window the package version was frozen at
> `0.5.3` while commit milestones ran from `v6` to `v16`. Under the current
> convention these would be `0.6.x`–`0.16.x`. The version-by-version timeline is
> preserved below as it was recorded at the time.

Version bump commit: `ed1b81a`

### Added
- Resident-Role launcher: tmux-based long-lived Role processes (`mos-{port}-{role}` sessions)
- `mos_` prefix namespace for all MCP tools; config whitelist alignment
- `mos_await_events` added to all role main whitelists
- Workspace-structure skill with Freedom clause

### Changed
- All Role prompts, skills, and docs updated for resident-Role + `mos_` namespace

---

## [`v6`–`v16` detailed timeline] - 2026-05-16 to 2026-05-28

Version-by-version detail for the milestone series above. During this window the
pyproject package version stayed frozen at `0.5.3` while commit milestones ran
`v6`→`v16` (the drift the current `vN ⇒ 0.N.x` convention fixes). Listed in
reverse chronological order.

### v16.1 (2026-05-27)
- Compact-hook scope gate, fallback-model wiring, install hardening
- Anti-wedge backstop + project tree migration to `projects/`

### v15.52 (2026-05-26)
- `project_create` cold-start collapse: A/C/D phases from 4–5 min to ~30 s
- Gru EACN boundary docs+tests (v15.50)
- Filter dismissed roles from the observatory terminal and project list (v15.49)
- Fix bare-slug expert spawn ACL bug + tighten Gru EACN boundary (v15.48)
- Harden Role spawn defaults: `IS_SANDBOX` for root-uid hosts, 1M-context model strings (v15.47)
- Install UX overhaul: minimal-core, background visual extras, auto PyPI mirror (v15.46)
- Scope hooks to MinionsOS-only; guard against outer-repo bleed (v15.45)
- Tighten author-seed git detection (v15.44)
- Subagent dispatch: Codex-vs-Sonnet two-case gate (v15.43)
- Paper-writing figure-chart-atlas: Taylor diagram archetype (v15.42)
- Lifecycle fix: tmux sweep + project revive ordering (v15.40)

### v15.31 (2026-05-25)
- Gru + Ethics SYSTEM.md slim — ~10.5k tokens saved per Role per turn
- SYSTEM.md slim 529→232 lines (-56%), ~4k tokens saved per turn (v15.30)
- Context-tax slim: `auto:30` tiered ToolSearch + MANUAL coupling (v15.29)
- Data-grounded MANUAL refinement + roles/SYSTEM.md hardening (v15.28)
- Paper-writing skill polish: figure / caption / IMRAD / chart-atlas (v15.27)
- MANUAL refactor: 3-layer fetch-on-demand reference (134 tools, 12 domains, 9 pitfalls) (v15.26)
- Paper-writing skill expansion + MANUAL/: CNS discipline, chart atlas, figure idioms (v15.24)
- MCP-dead wedge detection; revert `cache_keepalive` default to 240s (v15.23)
- Post-compact tmux kick (#29); `cache_keepalive` filter & retune (#28) (v15.22)
- MinionsVIZ overhaul: picker, terminals, orbit, packets, tasks, events (v15.20)
- Book index gains a Relations section (edges) (v15.19.2)
- `noter_model` defaults to opus; claude_model default flips too (v15.19.1)
- `.mcp.json` + config files use absolute paths (#27) (v15.19)
- Gru stall breaker: proactive milestone vote on long-term stagnation (v15.18)
- `wedge_detect` reads session JSONL; queue auto-reconciles in operator mode (v15.17)

### v15.16 (2026-05-24)
- Draft-discipline ABCD: contract + audit + cron + digest
- `cmd` token expansion in `exp_run` + scheduler port carry (#24) (v15.15)
- Large init prompts (#22) + `stop_backend` race (#23) (v15.14)
- Spawn init retry (#21) + template assert (#20) (v15.13)
- Silent-wedge watchdog (#15) + operator kick (#17) + graphify timeout (#16) (v15.11)
- Document Tier 0 seed-and-Edit for Opus 4.7 empty-input bug (v15.10.1)
- Fix GitHub Issues #13 + #14: commit amplification + observatory unbounded turn (v15.10)
- Fix Issues #9/#10/#11/#12 + graphify install + `draft_nodes_persisted` (v15.9)
- VIZ + Gru drive + scaffolding fixes (Issues #4/#5/#7/#8) (v15.8)
- Fix Issues #1/#2/#3 + harden label-retry on uploads (v15.7)
- GitHub Issues uploader + cold-start advisory message (v15.6)
- tmux install: Windows platform branches (v15.5.1)
- Tier-2 relay contract hardening + tmux as install dependency (v15.5)
- Bootstrap seed: cold-start unified with L1 Draft root (v15.4)
- Gru loop self-cleanup: orphan reaper + auto-exit + signal handlers (v15.3)

### v15.2 / v15.1 (2026-05-23)
- Isolate MinionsOS-spawned sessions from host auto-rename hooks
- Adjudication layer: fine-grained answer review before grader (v15.1)

### v15-α through v15-δ (2026-05-23) — Mission Profile track
- Batch benchmark harness + CLI + Mission Profile docs (v15-δ)
- End-to-end profile-aware publish whitelist coverage (v15-γ)
- Profile-aware publish whitelist + `mos_submit` / `mos_evaluate` (v15-β)
- Mission Profile loader + `scientific-paper` manifest (v15-α)

### v14 series (2026-05-23)
- v14.2: README rewrite + correct three v14 errors
- v14.1: clean delivery surface — untrack dev workspace from public repo
- v14: Skill family cleanup + four-stage evolution pipeline

### v13 series (2026-05-22)
- v13.6.x: pass-5 audit; historical leftovers, redundant interfaces, registry alignment
- v13.5.x: deep audit pass 2 — drift fixes, dead code purge, latent-gap hardening; boundary tests + install.sh hook regression smoke
- v13.4: viz Atlas removal; expert split/merge experiments; memory outline; consistency audit
- v13.3: execution-role cleanup + final memory-surface cleanup
- v13.2: full name-consistency sweep for memory and governance surfaces
- v13.1: name-consistency cleanup for Draft, Book, and governance surfaces

### v12 / v11 series (2026-05-20 to 2026-05-22)
- v12.1: scrub author-local absolute paths from committed surfaces
- v12: memory-surface standardization + identity module + skill cleanup
- v11.3: visual format-check tooling + paper-writing quality contract + keepalive early-exit
- v11.2: extract 3 cohesive helpers from `lifecycle/project.py` — partial split
- v11.1: split `mcp_server.py` into `mcp/` package — mechanical-only refactor
- v11: name-only rename — DAG→Scratchpad, Wiki→Library, global_graph→Atlas

### v10 series (2026-05-19)
- v10.1.2: one-command bootstrap polish — hooks, conditional MCP, install verification
- v10.1.1: README accuracy patch — purge Experimenter, demote Codex, add missing MCP tools
- v10.1: viz fixes — wiki/KG views actually reachable + serve real data
- v10: viz + dev-log + integrations docs + hygiene
- v10: role SYSTEM.md updates — issue reporting, audit depth, wiki duties
- v10: hooks + lifecycle refactors — compact pipeline, role launcher, paths
- v10: new MCP tools — `global_graph`, `issues`, wiki rewrite, skill-nodes mounting

### v9 / v8 (2026-05-19)
- v9: product-memory architecture (wiki / signboard / graphify) + real-Role e2e fixes + paper-search rewrite
- v8: `mos audit` + `mos scaffold` + MCP authz hardening + dev-log + skills polish

### v7 series (2026-05-17 to 2026-05-18)
- v7.9: consolidate MCP servers under `mcp-servers/` — registry + EACN3 move
- v7.8: progressive-disclosure toolkit pattern — orchestrator + nested sub-skills
- v7.7: per-project bare git repo — author repo seeded once, projects fully isolated
- v7.6: workspace restructure — retire `artifacts/`, introduce `branches/shared/` + `mos_publish_to_shared`
- v7.5.1: prune stale build/audit/eval artifacts
- v7.5: think-then-act skill v3→v4; Observatory DAG view tab
- v7: CLI role attach/inspect/drive + role-prompt polish; paper-writing skill expansion (academic discipline library + figure aesthetic exemplars); formal review workflow, Draft graph, reset/pending_plan, `mos_review_run`

## [Unreleased post-0.5.3] - 2026-05-17 to 2026-05-28 (rollup)

The sections below summarize the work landed on `main` after the v0.5.3
version-bump commit (`ed1b81a`) — i.e. the in-flight `0.5.3+` patch
series — grouped Keep-a-Changelog style. The internal version-by-version
timeline for the same window appears above under "v0.5.x internal patch
series".

### Added
- Hermetic Role process isolation (Tier 1 + Tier 2, opt-in via `MINIONS_ROLE_HERMETIC_CWD`)
- Reel L0 memory layer — raw verbatim subagent transcripts via PostToolUse hook; `reel_ref` pointers from Draft/Book
- `mos_reel_get` / `mos_reel_window` MCP tools for drill-down into per-role session transcripts
- Ethics cross-role Reel read permission; Gru cross-role read for all roles
- Book V2 schema — 7-state `status`, `paper_role`, Ethics ratify, `open_question`, `dead_end` nodes
- `mos_book_ratify`, `mos_book_open_question`, `mos_book_dead_end` MCP tools
- `mos_adjudicate` — panel adjudication (1–3 independent instances) before answer grader
- `mos_role_evolve_evaluate` / `mos_role_split` / `mos_role_merge` / `mos_role_evolve_dismiss` for evidence-gated Role topology changes
- `mos_project_reimport` / `mos_project_relocate` lifecycle commands
- Bare-slug Expert migration + `register_expert` coercion
- Portable project paths via `${PROJECT_DIR}` placeholder in EACN3 event data
- `mos role capture` CLI command
- wait_bg early-exit on bg Agent/Task via SubagentStop marker hook
- §-numbered common role contract (12 layers) replacing flat SYSTEM.md
- Codex-vs-Sonnet two-tier subagent dispatch gate in skills
- `mos upgrade` incremental install (60 s → ~2 s for unchanged environments)
- Heartbeat watchdog for stalled roles
- Silent-wedge watchdog + operator kick
- QUICKSTART.md onboarding guide
- GitHub Issues uploader + cold-start advisory
- `mos audit` + `mos scaffold` CLI subcommands
- `branches/shared/` publishing model + `mos_publish_to_shared`
- Per-project bare git repo — author repo seeded once, projects fully isolated
- High-intensity execution delegation experiments
- Mission Profile loader (`scientific-paper` manifest)
- `mos_submit` / `mos_evaluate` profile-aware delivery
- Batch benchmark harness + CLI
- `mos_review_run` — Gru-run paper-review workflow
- Skill-curator / skill-audit / skill-forge four-stage evolution pipeline
- `mos_project_checkpoint_workspace` durable local commits + optional GitHub push

### Fixed
- Roles self-kill on EACN connection errors (issue #53)
- Role-wedge protection and anti-wedge backstop
- bare-slug expert spawn ACL bug
- Cold-start collapse — `project_create` A/C/D phases from 4–5 min to ~30 s
- Dismissed roles filtered from the observatory terminal and project list
- tmux safety warning on destructive session ops
- `.mcp.json` + config files use absolute paths (issue #27)
- ANSI escape codes in role logs (issue #54)
- Adjudication task routing to Ethics (issue #55)
- Commit amplification + observatory unbounded turn (issues #13, #14)
- `${PROJECT_DIR}` placeholder rehydration in `get_events` drain (issue #47)
- Lifecycle revive filter for malformed role names (issue #44)
- SyntaxWarning in `role_launcher.py` sed regex
- `cache_keepalive` prompt and add heartbeat watchdog (issue #61)

### Changed
- Project tree migrated to `projects/` (from `workspaces/`)
- Memory layers standardized as Reel, Draft, and Book
- SYSTEM.md slim: 529→232 lines (−56%), ~4k tokens saved per role per turn
- Graphify/CodeGraph downgraded to per-role optional MCP; removed from project-level Shelf
- MCP tool namespace prefixed with `mos_` across all role whitelists
- Common role contract decoupled into single canonical §-numbered file
- Formal paper review consolidated under `mos_review_run`

---

## [0.5.0–0.5.2] - 2026-04-26 to 2026-05-16

Version v0.5.x development phase. Specific subversions are consolidated;
exact dates of intermediate releases are approximate. Major themes:

### v5 / v5.x track
- v5.1–v5.4 (2026-05-13 → 2026-05-16): simplify lifecycle; promote cross-role skills to `common/`; rewrite EACN3 manual into 3-layer progressive-disclosure skill; Exploration DAG as shared team cognitive memory; cognitive discipline skills
- Workspace restructure to `branches/`; lifecycle hooks; per-branch AGENTS.md
- Role wake loop becomes `eacn3_await_events(120s)` with graceful exit
- Observatory reads role session archives non-destructively
- Archive host session jsonl into role branch after each wake
- `mos_pool` module — EACN3 wrapper + per-wake local ACK
- Native `mos_*` MCP tools registered (no role wiring yet at first; subsequently wired)
- Common role contract switches to `mos_*` + ultrathink-before-act
- Role MCP surfaces migrated to the `mos_*` namespace
- Gru SYSTEM.md routes internal work through MOS Agent Pool
- Durable workspace checkpoints + hook-driven wake signals
- High-intensity execution delegation experiments
- SSL-based progressive-disclosure skill library + EACN3 manual
- Stabilize runtime and observatory wiring; standardize MinionsOS repository naming
- Refresh observatory dependency lock; prune obsolete docs

### v4 / pre-v5 (2026-04-26 → 2026-04-29)
- v4: initial public MinionsOS V4 release
- MinionsVIZ V2 rewrite — network and observatory views; dashboard polish
- Stabilize EACN role collaboration; experiment scheduling and role maintenance flow
- Recover roles after runtime kill
- Compact scratchpads past veto
- Vendor EACN3 as plain directory (submodule URL was unreachable)
- Phase 1 state contract — extend RoleEntry, queue_depth from EACN, pending_events, role lifecycle helpers
- Project port pre-check with retry; workspace `.gitignore` hygiene
- `mos status --json` extended with backend/agent/queue/failure fields
- `project_status_snapshot()` for Phase 1 status contract
- `mos doctor` checks: model-registry, claude-debug-disabled
- `claude_model` field and `model_registry_valid()` in `GruConfig`
- `MINIONS_DEBUG` env var for Gru DEBUG_MODE
- Project-local agent registration enforcement on EACN
- Role skills + review templates

---

## [0.1–0.4] - pre-2026-04-26

Early versions consolidated. The repository was initialized as
`MinionsOS_V3` on 2026-04-26 (`2c1586c Initial MinionsOS_V3 repository`)
with a Phase 0 + minimal Phase 1 implementation plan. Earlier MinionsOS
iterations (V1–V3) lived in predecessor repositories and are not
documented in this changelog.

---

[0.20.0]: https://github.com/Minions-Land/MinionsOS/releases/tag/v20
[0.5.3]: https://github.com/Minions-Land/MinionsOS/releases/tag/v0.5.3
