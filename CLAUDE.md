# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. **Claude Code is the primary and default agent host** for every Role. Codex is no longer used to host a Role process directly — it is reachable as a sub-agent through the `codex-subagent` MCP server (`mcp-servers/codex-subagent/`) when a Role wants to delegate high-intensity execution to GPT-5.5. Keep that delegation path working when refactoring; do not ground new Role behavior in Codex-as-host.

## Project overview

MinionsOS is a local multi-agent operating system for running autonomous research projects. A persistent Gru process supervises many isolated paper-sized projects; each project has its own EACN3 backend, git worktree, artifacts, logs, role drafts, and long-lived Role processes hosted by Claude Code. Roles may delegate high-intensity execution to Codex GPT-5.5 through the `codex-subagent` MCP, but Codex never hosts a Role process directly.

**Mission Profiles (v15+).** A project's behaviour is controlled by a *Mission Profile* (`minions/profiles/<name>.yaml`) selected at `mos_project_create` time. Profiles declare which Roles spawn, what the deliverable is, and how it's evaluated. The default `scientific-paper` profile preserves the original Autonomous Scientific Discovery pipeline (Noter + Coder + Ethics + Writer → peer-reviewed paper PDF). Lightweight profiles like `hle-answer` enable benchmark/leaderboard scenarios (HLE, MMLU, GPQA, SWE-bench) by spawning a smaller role roster (Gru + Expert + Coder), persisting deliverables under `branches/shared/submissions/`, and evaluating via `mos_evaluate` strategies (`answer_grader`, `test_runner`, or `scientific_peer_review`). The original Autonomous Scientific Discovery capability is fully preserved as the default profile; no breaking changes to existing projects.

`mcp-servers/eacn3/` is a local editable dependency pinned through `pyproject.toml` and `uv.lock`. Treat it as a dependency boundary during normal MinionsOS work: prefer EACN MCP tools and the MinionsOS adapter modules over hand-written HTTP calls or incidental edits inside `mcp-servers/eacn3/`.

## Common commands

```bash
# Install / refresh dependencies and generated config files
./install.sh
uv sync

# Launch Gru / CLI entry points
./gru
./minionsos
./mos

# Environment and project management
./mos doctor
./mos status
./mos status --json
./mos config
./mos project list
./mos project close <port>
./mos project revive <port>
./mos project repair <port>
./mos role list <port>
./mos role dismiss <port> <role>
./mos logs --project <port>
./mos logs --project <port> --role <role> --tail 50

# Python tests
uv run pytest tests/unit/
uv run pytest tests/unit/test_port_allocator.py
uv run pytest tests/unit/test_port_allocator.py::test_no_reuse_retired_ports
MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/

# Python lint / format checks
uv run ruff check minions/
uv run ruff format --check minions/

# MinionsVIZ dashboard
./viz ensure
./viz start|stop|status|open|logs
./mos viz ensure|start|stop|status|open|logs

# MinionsVIZ development, only when editing minions-viz/
cd minions-viz
npm install
npm run dev
npm run build
npm start
```

Use `uv` for Python environment management. Do not use `pip`, `conda`, `mamba`, `virtualenv`, or bare `python -m venv` in workflow steps. The package requires Python 3.11+ and uses `uv.lock` plus the editable EACN3 source at `mcp-servers/eacn3/` configured in `pyproject.toml`.

## Architecture map

### Root layout

- `minions/` — Python package and main implementation.
- `minions/bin/gru`, root `gru`, `minionsos`, `mos`, `viz` — launcher scripts/symlinks.
- `minions/config/` — example Gru and experiment-target configs copied by `install.sh`.
- `minions/state/` — runtime Gru state, including `projects.json` and Gru logs; gitignored runtime data.
- `minions/roles/SYSTEM.md` — common Role contract injected before each role-specific prompt.
- `minions/roles/{role}/SYSTEM.md` — role prompts for Gru, Noter, Coder, Writer, Ethics, and Expert.
- `minions/roles/{role}/skills/*.md` — optional role skills discovered at wake-up.
- `minions/review/` — paper-review prompt assets (SYSTEM.md, skills, personas, templates) consumed by the `mos_review_run` MCP tool. Review is **not** a Role and is not registered on EACN.
- `minions/domains/*.md` — Expert domain packs used as reusable specialty assets.
- `minions-viz/` — read-only Observatory dashboard, Express/WebSocket server plus React/Vite frontend.
- `EACN3` — local editable EACN3 dependency (lives at `mcp-servers/eacn3/`).
- `mcp-servers/` — standalone MCP servers registered in `.mcp.json`. `mcp-servers/README.md` is the canonical registry. Currently houses `eacn3/` (the EACN3 dep + its Node plugin), `codex-subagent/` (Node bridge to Codex GPT-5.5), `keepalive/` (Python FastMCP — `wait_bg` cache-keepalive + `keepalive_now`), and `graphify/` (Python — read-only L3 Shelf graph queries). The `minionsos` MCP server itself lives inside the Python package at `minions/tools/mcp/` (with a 50-line shim at `minions/tools/mcp_server.py`) for import-graph reasons; see `mcp-servers/minionsos.md` for why.
- `project_{port}/` — runtime projects created by Gru; gitignored.

### Python package responsibilities

- `minions/cli.py` is the `mos` CLI entry point and dispatches project, role, logs, doctor, and viz commands.
- `minions/gru/loop.py` runs the Gru monitor loop (backend health probes, resident-Role tmux watchdog, experiment queue reconcile).
- `minions/lifecycle/project.py` implements project create/close/dormant/revive behavior, including project directories, metadata, worktrees, backends, and artifacts.
- `minions/lifecycle/agent_host.py` builds the long-lived `claude` invocation for each Role and the forever-loop initial prompt.
- `minions/lifecycle/role.py` registers roles (project-local EACN3 AgentCard, role workspace, host session name) and dismisses them. Resident-Role process startup runs through `role_launcher.py`.
- `minions/lifecycle/role_launcher.py` starts the long-lived Role process for each (project, role) inside a named tmux session (`mos-{port}-{role}`). The Role drives its own event loop via `mos_await_events()`. The launcher also exposes `session_alive` / `kill_session` / `attach_command` for the watchdog and the operator.
- `minions/lifecycle/eacn_client.py` is the thin EACN3 HTTP client used by lifecycle code and `mos_await_events` (registration, bootstrap messages, health-event notifications).
- `minions/lifecycle/agent_registry.py` and `eacn_identity.py` keep project-local AgentCard identities stable.
- `minions/lifecycle/project_bridge.py` implements the Gru-only cross-project bridge (`mos_project_bridge`).
- `minions/state/` contains file-backed state management and port allocation.
- `minions/tools/mcp_server.py` exposes lifecycle operations as FastMCP tools.
- `minions/tools/experiment_ssh.py` implements Coder's `mos_exp_*` local/SSH execution tools, including queue-facing `exp_queue_*` and `exp_gpu_pool_*`.
- `minions/tools/experiment_scheduler.py` keeps the SQLite-backed project experiment queue and GPU packing logic.
- `minions/tools/paper_search.py` implements Writer paper-search helpers exposed through MCP.
- `minions/tools/whitelist.py` resolves allowed tool surfaces for main roles vs. subagents.
- `mcp-servers/codex-subagent/` is a standalone Node MCP server that exposes Codex GPT-5.5 to Claude Code roles as a full-access sub-agent for high-intensity execution (single `codex` tool: read-only analysis or full-access delegation, controlled via the `sandbox` arg).

### Runtime project model

Every project is identified by its EACN3 backend port and lives under `project_{port}/`:

```text
project_{port}/
├── CLAUDE.md                    # project narrative; author/Gru write, roles read
├── AGENTS.md                    # Codex sub-agent's view of project context (mirrors CLAUDE.md)
├── meta.json                    # machine metadata
├── parent_repo.git/             # per-project bare git repo, seeded from author HEAD
├── branches/                    # git worktrees, one per role plus a shared tree
│   ├── main/                    # Gru — branch minionsos/project-{port}
│   ├── coder/                   # branch minionsos/project-{port}-coder
│   │   └── reel/<session_id>/   ← Layer 0: raw session traces (Reel)
│   │       ├── index.jsonl       JSONL index of captured subagent/codex outputs
│   │       └── transcripts/      Verbatim *.jsonl transcripts per task_id
│   ├── writer/                  # branch minionsos/project-{port}-writer
│   │   └── reel/<session_id>/   ← Layer 0: same shape as coder/reel/
│   ├── ethics/                  # Ethics drafts; published reports go to shared/ethics/
│   │   └── reel/<session_id>/   ← Layer 0: same shape
│   ├── noter/                   # Noter drafts; published notes/Draft go to shared/
│   ├── expert-<slug>/           # one per Expert
│   │   └── reel/<session_id>/   ← Layer 0: same shape
│   └── shared/                  # branch minionsos/project-{port}-shared
│       ├── draft/draft.json # Noter-curated Draft (L1 process memory)
│       ├── notes/               # Noter staged reports
│       ├── ethics/              # Ethics published reports (flat)
│       ├── exp/exp-<id>/        # Coder experiment result bundles
│       ├── reviews/round-<n>/   # mos_review_run output (tool-owned)
│       ├── handoffs/            # cross-role handoffs
│       ├── governance/          # signboard.json (phase-transition consensus)
│       ├── book/                          ← Layer 2: Compiled Knowledge (Book)
│       │   ├── index.md                    Noter-maintained catalog
│       │   ├── hot.md                      ~500-word rolling cache, injected at role wake-up
│       │   ├── log.md                      Append-only ingest/lint journal (JSONL)
│       │   ├── sources/{role}-{slug}.md    One page per ingested artifact (carries reel_ref)
│       │   └── contradictions/             Auto-detected claim conflicts (Ethics reads)
│       └── shelf/shelf.json               ← Layer 3: structural index (graphify-extracted)
├── eacn3_data/eacn3.db          # project-local EACN3 SQLite state (gitignored)
├── events/                      # per-agent EACN event JSONL audit stream (gitignored)
├── state/                       # runtime control state (gitignored)
│   ├── shared.lock              # flock used by mos_publish_to_shared
│   └── .reset_markers/          # mos_reset_context drops a marker per role
└── logs/                        # backend.log and role-{name}.log (gitignored)
```

Cross-role writes go through `mos_publish_to_shared(role, src_path, dst_subpath, commit_message)`, which holds `state/shared.lock`, copies the source file into `branches/shared/<dst_subpath>`, and commits on the shared branch. Per-role subdir policy lives in `minions/tools/publish.py` (`_ROLE_ALLOWED_SHARED_SUBDIRS`). The Draft file is updated in place by `mos_draft_append`/`mos_draft_annotate` and flushed on a timer by Noter through `mos_draft_commit_shared`. The review surface (`reviews/`) is reserved for `mos_review_run`, which writes there directly and commits the round at the end.

The parent directory containing this repository is the **author seed repo**: at `mos_project_create` time, MinionsOS imports its current HEAD (excluding `MinionsOS/` itself and any file larger than 500 MB) into a per-project bare git repo at `project_{port}/parent_repo.git/`. All worktrees — main, role, shared — branch off that per-project bare repo, so the author repo is never written to and never gains `minionsos/*` branches. The seed source must be git-initialized; `./install.sh` warns about this and `./mos doctor` re-checks it. To override the seed source, set `gru.yaml:author_repo` (or `MINIONS_AUTHOR_REPO`).

### Mission profiles

A *Mission Profile* is a project-level YAML manifest under `minions/profiles/<name>.yaml` that decouples the runtime topology from the "always a paper" assumption. Each profile declares:

- `roles_active`: which Roles spawn at `mos_project_create` time (e.g. scientific-paper spawns `gru/noter/coder/ethics`; hle-answer only spawns `gru/expert/coder`).
- `role_prompt_overlay`: per-role markdown overlay paths appended to the role's `SYSTEM.md` so a profile can reshape Role focus without forking prompts.
- `deliverable_schema`: required output paths under `branches/shared/`, plus a per-role `publish_whitelist` overriding the default scientific-paper baseline. The default whitelist (in `minions/tools/publish.py`) is the fallback when no profile is set.
- `evaluation`: strategy + reference path. Strategies dispatch through `mos_evaluate`: `scientific_peer_review` (delegates to `mos_review_run`), `answer_grader` (compares `branches/shared/submissions/answer.json` to `input/expected.json`), `test_runner` (reserved for SWE-bench).
- `phase_schema`: `scientific_three_stage` (exploration → experiment → writing → review) or `minimal` (no phase progression).
- `on_done`: `none` (default), `dormant`, or `shutdown_project` once the deliverable is submitted+evaluated.

The two MCP entry points that close the deliverable lifecycle:

- `mos_submit(port, payload, kind)` — Role asks Gru to persist a deliverable (kinds: `answer` / `paper` / `patch` / `report`) under `branches/shared/submissions/` and commit on the shared branch.
- `mos_evaluate(port)` — Gru runs the project's profile-defined evaluation strategy and returns `{score, verdict, details}`.

For batch leaderboard / 打榜 scenarios, `mos benchmark run <jsonl>` (or `minions.tools.benchmark.benchmark_run_from_jsonl`) creates one project per task, evaluates each, and writes a single aggregate JSON under `minions/state/benchmark_runs/run-<id>.json`.

Available profiles ship in `minions/profiles/`:

| Profile | Use case | Roles | Evaluation | Deliverable |
|---|---|---|---|---|
| `scientific-paper` (default) | Full Autonomous Scientific Discovery — peer-reviewed paper | gru, noter, coder, ethics (writer on-demand) | `scientific_peer_review` (mos_review_run) | `branches/shared/notes/`, `exp/`, `ethics/`, `reviews/` |
| `hle-answer` | Single-question benchmarks (HLE, MMLU, GPQA) | gru, expert, coder | `answer_grader` (exact match / numeric close) | `branches/shared/submissions/answer.json` |

To add a new profile: drop `minions/profiles/<name>.yaml` matching the `MissionProfile` schema in `minions/profiles/__init__.py`, optionally add a role-prompt overlay, and (if needed) extend `mos_evaluate` with a new strategy in `minions/tools/evaluator.py`.

### Role lifecycle and boundaries

Each Role is a long-lived `claude` process running inside its own tmux session named `mos-{port}-{role}`. EACN-registered roles drive their event loop with `mos_await_events()` (in `minions/tools/await_events.py`), which wraps the project-local 60-second `GET /api/events/{agent_id}` long-poll, drains events on read, runs an idle-check after ~5 minutes of silence, and only returns when there is actionable content. Heartbeat writes happen between polls so the Gru sidecar watchdog can spot a dead session and respawn it. Roles respond with raw `eacn3_send_message` / `eacn3_create_task` / `eacn3_submit_bid` / `eacn3_submit_result` and stay resident across many cycles. They do not call `eacn3_await_events` / `eacn3_next` / `eacn3_get_events` directly — that bypasses the wrapper and drops the suggested-action annotations.

**Noter** is the exception: it is NOT registered on EACN3. It uses `mos_noter_wait()` (timer-based, default 3 min) instead of `mos_await_events()`, and observes the project by reading `events/*.jsonl` and `branches/shared/` artifacts. It runs on Sonnet (configured via `gru.yaml: noter_model`).

**Writer** is on-demand: it is not bootstrapped at project creation. Gru spawns it with `mos_spawn_role(role="writer")` when the project enters a paper-writing phase.

Only Gru may spawn EACN-visible agents or use `mos_project_*`, `mos_spawn_*`, and `mos_project_bridge` tools. Subagents or local teams created inside a Role are EACN-invisible by design: they do not have `eacn3_*` tools and do not appear in `projects.json`.

Claude Code is the only Role host. It honors CLI `--allowed-tools` for tool gating. The `codex-subagent` MCP exposes Codex GPT-5.5 to Roles as a full-access delegation target through the single `codex` tool (use `sandbox=read-only` for analysis, `sandbox=danger-full-access` for execution); it does not host a Role process. MinionsOS MCP server-side authorization in `minions/tools/mcp_server.py` must remain aligned with `minions.config.resolve_whitelist` so the same boundary applies regardless of which surface a tool call comes through.

Tool/write boundaries (main role write scope; subagents inherit from their parent main role):

| Agent | Project-local EACN access | Experiment tools | Codex subagent | Gru/project/spawn tools | Own branch | Shared subdirs (via mos_publish_to_shared) |
|---|---|---|---|---|---|---|
| Gru main | `eacn3_*` (events delivered by scheduler) | no | `codex` | yes | `branches/main/` | any subdir |
| Noter main | `mos_noter_wait` (timer, no EACN) | no | no | no | `branches/noter/` (drafts) | `notes/`, `draft/`, `handoffs/`, `book/` |
| Coder main | `eacn3_*` | yes | `codex` | no | `branches/coder/` | `exp/`, `handoffs/`, `governance/` |
| Writer main (on-demand) | `eacn3_*` plus paper-search MCP tools | no | `codex` | no | `branches/writer/` | `handoffs/`, `governance/` |
| Expert main | `eacn3_*` | no | `codex` | no | `branches/<expert>/` (read-mostly) | `handoffs/`, `governance/` |
| Ethics main | `eacn3_*` | no | `codex` | no | `branches/ethics/` (drafts) | `ethics/`, `handoffs/`, `governance/` |
| All roles (read) | - | - | - | - | - | `book/` (via `mos_book_query`/`hot_get`/`save_synthesis`/`audit_walk`/`resolve_contradiction`) |

`branches/shared/reviews/` is reserved for `mos_review_run` — the publish tool will reject any other caller. `branches/shared/submissions/` is reserved for `mos_submit`; any role's profile may grant the role access to it via the profile's `publish_whitelist[role]` list (e.g. `hle-answer` grants `expert` and `coder` write access; `scientific-paper` grants nobody by default — paper deliverables go through Writer + `mos_review_run` instead). `branches/shared/draft/draft.json` is updated in-place by `mos_draft_append` and committed on a Noter-driven cron through `mos_draft_commit_shared` (whitelisted to Noter and Gru only). No role writes to another role's `branches/<role>/` directly; cross-role artefacts always travel through `branches/shared/<subdir>/` via `mos_publish_to_shared`. The visual format-check tools (`mos_visual_render`, `mos_visual_inspect`, `mos_visual_check`) are available to every EACN-visible role (Gru, Coder, Writer, Ethics, Expert) and denied to Noter; reports persist under `branches/<role>/visual-reports/` and are referenced cross-role by EACN message rather than via a shared subdir.

**Deliverable lifecycle tools.** `mos_submit` and `mos_evaluate` are Gru-only (whitelist + server-side authz). Other Roles must surface a deliverable to Gru by EACN message; Gru then calls `mos_submit` to persist it under `branches/shared/submissions/` and `mos_evaluate` to score it via the profile-defined strategy. The lifecycle separation matches the existing "Gru is the control plane" rule.

**Reel (L0) layer.** Every EACN-visible role gets `mos_reel_get` / `mos_reel_window` for drill-down access into its own raw session transcripts at `branches/<role>/reel/<session_id>/`. Gru holds cross-role read permission (so it can audit any role's reasoning when bridging projects or evaluating role evolution); non-Gru roles can only read their own reel. Noter is excluded from the reel surface — it observes the project through events/* and the Draft, not through other roles' transcripts. Capture is automatic: the `reel_capture` PostToolUse hook archives every `Agent` / `Task` / `mcp__codex-subagent__codex` output into the calling role's reel directory; roles never call reel-write tools directly. Draft / Book frontmatter carries a `reel_ref` pointer that auditors can follow back to the original execution frame.

### Evidence-gated Role evolution (SPLIT / MERGE / DISMISS)

Roles are not fixed in number for the lifetime of a project. Gru can grow, fuse, or retire Roles based on artifact-grounded evidence. The mechanism lives in `minions/lifecycle/role_evolution.py` and is exposed through four Gru-only MCP tools:

- `mos_role_evolve_evaluate` — read-only; reads recent artifacts under `branches/shared/` (Ethics reports, review packets, experiment failures) and per-role activity stats; returns `SplitDecision` per active role plus `MergeDecision` (convergence-only) and `DismissDecision` (starvation-only) candidates.
- `mos_role_split` — realises a SPLIT decision: spawns each specialist via `register_expert`, then dismisses the source role. Requires non-empty `evidence_refs`. On partial spawn failure the source role is **kept alive** to preserve coverage.
- `mos_role_merge` — realises a MERGE decision: spawns the unified role, dismisses the sources. Used **only for behavioural convergence** between two active Roles. Source roles do **not** need to share a SPLIT lineage; convergence merge applies to independently-spawned Experts whose artifact overlap exceeds `merge_convergence_threshold`.
- `mos_role_evolve_dismiss` — realises a DISMISS decision: retires a Role with no recent work. Distinct from the generic `mos_dismiss_role` because it requires non-empty `evidence_refs` and writes to the role-evolution audit log. **No replacement is implied.** If new work appears later that no active Role can cover, a separate spawn trigger handles it.

Triggers are evidence-gated, not diversity-gated:

- **SPLIT**: ≥ `split_min_failures` (default 5) attributable failures in the recent window, partitioned into ≥ `split_min_subdomains` (default 2) labeled clusters each ≥ `split_min_per_subdomain` (default 3) large.
- **MERGE-by-convergence**: any pair of active roles whose `convergence_score` (Jaccard of artifact basenames + directory-prefix overlap) ≥ `merge_convergence_threshold` (default 0.75).
- **DISMISS-by-starvation**: a role active ≥ `dismiss_starve_min_age_hours` (default 6h) with ≤ `dismiss_starve_max_tasks` (default 1) tasks in the recent window. Starvation goes to DISMISS, **not** MERGE — a Role with no work should be retired, not fused into another Role's scope.

A protective cooldown after any SPLIT/MERGE/DISMISS prevents oscillation: a role just evolved cannot be re-evaluated for `cooldown_after_split_hours` (12h), `cooldown_after_merge_hours` (6h), or `cooldown_after_dismiss_hours` (6h).

Every recommendation and apply event writes one line to `branches/shared/governance/role_evolution.jsonl`. The Gru loop runs `mos_role_evolve_evaluate` on a `role_evolution_interval_seconds` cadence (default 15 min) and **logs recommendations only** unless `role_evolution_auto_apply: true` is set in `gru.yaml`. Default is recommend-only — operators inspect the JSONL log and apply manually until the recommendation stream has been validated on real workloads.

### Role skills and review workflow

Role skills are markdown procedure guides under `minions/roles/{role}/skills/`. `minions.lifecycle.skills.list_skills` discovers them at wake-up, extracts one-line summaries, and injects a `[Skills]` block pointing to the full files. Skills should stay procedural and cross-domain; put domain-specific content under `minions/domains/`.

Review is run by Gru's `mos_review_run` MCP tool, not by a long-lived Role. Its prompt assets live under `minions/review/`:

- `minions/review/SYSTEM.md` — Area-Chair / Editor system prompt for the spawned `claude --print` process.
- `minions/review/skills/*.md` — `run-review-round`, `simulate-reviewer-instance`, `aspect-review`, `code-validity-review`, `revision-delta`, `finalize-review-packet`.
- `minions/review/personas/*.md` — short reviewer stances used by aspect subagents.
- `minions/review/templates/*.md` — required outputs: `aspect-note.md`, `reviewer-instance.md`, `fresh.md`, `revision_delta.md`, `consolidated.md`, `summary.md`, plus the `submission-checklist.md` Writer attaches when submitting.

A review round's Pass A must produce 3-5 independent reviewer-instance reports before reading prior review history. History enters only through the previous rolling summary during Pass B / Pass C.

### Cross-cycle memory

Roles are cold-started each invocation. There are no per-role private memory files. Persistent memory spans four layers (L0 → L3) plus a federated future (L4):

- **L0 Reel** — raw verbatim session traces at `project_{port}/branches/<role>/reel/<session_id>/`. Captured automatically by the `reel_capture` PostToolUse hook on every `Agent` / `Task` / `mcp__codex-subagent__codex` invocation. Each session directory holds an `index.jsonl` and a `transcripts/<task_id>.jsonl` per dispatched subagent. **Role-private by default**; Gru can read any role's reel. Read via `mos_reel_get(ref)` / `mos_reel_window(ref, span)` where `ref = "<role>/<session_id>/<task_id>"`. Reel is **not** injected at wake-up; it is drill-down only — Draft / Book / Shelf metadata carry a `reel_ref` pointer that any auditor can follow back to the original execution frame.
- **L1 Draft** — Noter-curated process graph at `project_{port}/branches/shared/draft/draft.json`. Accessed via `mos_draft_append` / `mos_draft_query` / `mos_draft_summary` / `mos_draft_annotate` / `mos_draft_path`. Buffered to disk on every call and flushed to a single commit on the shared branch by Noter on its periodic wake (`noter_periodic_interval`, default 3m). **Auto-injects `reel_ref` into every appended node's metadata** when `MINIONS_ROLE_NAME` and `MINIONS_SESSION_ID` env are set.
- **L2 Book** — durable compiled knowledge at `project_{port}/branches/shared/book/`. Noter-owned. Source pages carry `reel_ref` frontmatter when ingested by a role that had a session active.
- **L3 Shelf** — structural index. Two tiers: (a) per-project `branches/shared/shelf/shelf.json` (graphify-extracted, queryable by all roles via `mcp__graphify__*`); (b) global `~/.minionsos/shelf.json` (Gru-only cross-project aggregate via `mos_shelf_*`, built by `mos_shelf_register` merging per-project graphs).
- **L4 Library** (vision, not yet implemented) — federated global EACN3 network where projects are pluggable, shareable, evolvable, executable, recoverable. L4's "executable + recoverable" requirement is exactly why L0 must store full-fidelity transcripts.

Roles reconstruct context at wake-up from:

1. current transcript,
2. the Draft (especially `pending_plan` nodes left by their previous self before a `mos_reset_context`),
3. EACN history and shared `branches/shared/<subdir>/` artefacts,
4. root and project `CLAUDE.md` files.

### Evidence-first EACN communication

Substantive EACN messages from roles should include one of:

- `[evidence: <artifact path | commit SHA | URL | EACN event id>]`
- `[speculation]`
- `[derived: <base>]`

Ethics audits unmarked claim ratios statistically. This is a soft convention, but apply it when writing role prompts, templates, artifacts, and EACN-facing messages.

## MinionsVIZ

`minions-viz/` is a strictly read-only Observatory dashboard for all Gru installations on the host. It is a machine-wide singleton using `~/.minionsos/` for registry and process state. The server polls registered Grus and selected project EACN3 backends, then serves a React UI over HTTP/WebSocket.

Important invariants:

- Never POST/PUT/DELETE to EACN3 from viz.
- Never call `/api/events/{agent_id}` from viz because that drains real role queues.
- Project-scoped viz endpoints require `?gru=<id>` and should 404 unknown Gru/project pairs.
- Viz writes only its build output and `~/.minionsos/{grus.json,viz.pid,viz.port,viz.url}` state.

Relevant files:

- `minions-viz/src/server/index.ts` — Express and WebSocket server.
- `minions-viz/src/server/grus.ts` — `~/.minionsos/grus.json` and per-Gru project discovery.
- `minions-viz/src/server/mosFs.ts` — read-only filesystem views into project state.
- `minions-viz/src/server/poller.ts` — EACN3 read-only fetchers.
- `minions-viz/src/server/state.ts` — per `(gruId, port)` snapshot cache and broadcasts.
- `minions-viz/src/web/App.tsx` — Gru picker, project picker, and dashboard tabs.

## Debug entry points

| Problem | Where to look |
|---|---|
| Gru process | `minions/state/logs/gru.log` |
| Project backend | `project_{port}/logs/backend.log` |
| Role crash or behavior | `project_{port}/logs/role-{name}.log` |
| Project metadata | `project_{port}/meta.json` |
| EACN3 state | `project_{port}/eacn3_data/eacn3.db` |
| Experiment failure | `project_{port}/branches/shared/exp/exp-{id}/report.md` |
| Viz process | `./viz status` and `./viz logs` |

## Extension points

- New Role: add `minions/roles/{role}/SYSTEM.md`, update role whitelist/configuration, update the root whitelist table, and add unit coverage.
- New Role skill: add `minions/roles/{role}/skills/{slug}.md`; discovery is automatic through `minions.lifecycle.skills`.
- New review output shape: update the relevant `minions/review/templates/*.md`, the matching review skill in `minions/review/skills/`, and the test pinning the `mos_review_run` invariants.
- New Expert domain: add `minions/domains/{slug}.md`; keep it as a reusable prompt asset and add discovery/injection tests if runtime behavior changes.
- New MCP tool: add it under `minions/tools/`, register it in the MCP server, update whitelist rules, and add tests.
- New mission profile: add `minions/profiles/{name}.yaml` (and any role overlays under `minions/profiles/{name}/`), validate it loads via `minions.profiles.load_profile`, and add tests under `tests/unit/test_profiles.py`. If the profile needs a new evaluation strategy, extend `minions/tools/evaluator.py`.
