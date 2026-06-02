# CLAUDE.md

**Who reads this file:**
In default (non-hermetic) mode, Claude Code's cwd walk includes this file for
all Role processes as well as developer sessions. In hermetic mode
(`MINIONS_ROLE_HERMETIC_CWD=1`), Role processes use a stub cwd and never reach
this file. **Role agents should treat this file as developer documentation and
not apply its architectural details as runtime rules.** Runtime rules for Role
agents live exclusively in `minions/roles/SYSTEM.md` (injected via
`--append-system-prompt`) and the initial_prompt built by `agent_host.py`.

This file provides guidance to Claude Code when working with **MinionsOS
codebase development**. If you are a **Role agent** at runtime and somehow
reading this: your operative contract is SYSTEM.md, not this file.

## Tool-use input must stay small (Opus 4.7 empty-input bug)

> **Canonical source:** `~/.claude/CLAUDE.md` (host-level). This section
> restates the rule for contributors who clone the repo without the host
> file. If the rule needs to change (e.g. a future Opus release fixes
> the bug), update `~/.claude/CLAUDE.md` first, then sync this section,
> `minions/roles/QUICKSTART.md`, and `minions/roles/SYSTEM.md` §4 host-fallback paragraph.

NEVER inline a large payload in a single `tool_use`'s `input` object — neither `Write.content`, `Edit.new_string`, nor `Bash.command` containing a long heredoc. **Hard cap per tool_use input: ~50 lines / ~3 KB of actual payload.**

For anything larger, especially anything matching CJK / LaTeX math / heredoc-tokens / multi-section structured content, use the `reliable-file-io` skill's **Tier 0 seed-and-Edit** recipe (`minions/roles/common/skills/reliable-file-io.md`):

1. Seed the file with one short `Write` (≤50 lines: preamble + closing token).
2. Append the rest with successive `Edit` calls, each ≤50 lines, inserting before the closing token.
3. Never put the full document into a Bash heredoc. The heredoc body becomes the oversize `Bash.command` string and triggers the same bug.

**Why this matters here:** every Role process (Noter / Writer / Coder / Ethics / Expert / Gru / review) routinely produces long Markdown / LaTeX / CJK content — Draft summaries, paper sections, review packets, project notes. Those are the exact content shapes that hit the bug. Confirmed failure: `Paper Crash` 2026-05-24, three consecutive `InputValidationError: required parameter ... is missing` on a Chinese LaTeX comparison report; output_tokens 47/74/25, cache_read 25K — not max_tokens, not context length, the model just dropped the long structured field.

This rule overrides any habit of "use reliable-file-io Tier 1's Python heredoc". For Tier-0-trigger content, Tier 1 is unsafe.

## Project overview

MinionsOS is a local multi-agent operating system for running autonomous research projects. A persistent Gru process supervises many isolated paper-sized projects; each project has its own EACN3 backend, git worktree, artifacts, logs, role drafts, and long-lived Role processes hosted by Claude Code.

**Mission Profiles (v15+).** A project's behaviour is controlled by a *Mission Profile* (`minions/profiles/<name>.yaml`) selected at `mos_project_create` time. Profiles declare which Roles spawn, what the deliverable is, and how it's evaluated. The default `scientific-paper` profile preserves the original Autonomous Scientific Discovery pipeline (Gru + Ethics + spawnable Experts → peer-reviewed paper PDF).

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
- `mcp-servers/` — standalone MCP servers registered in `.mcp.json`. `mcp-servers/README.md` is the canonical registry. Currently houses `eacn3/` (the EACN3 dep + its Node plugin) and `keepalive/` (Python FastMCP — `wait_bg` cache-keepalive + `keepalive_now`). The `minionsos` MCP server itself lives inside the Python package at `minions/tools/mcp/` (with a 50-line shim at `minions/tools/mcp_server.py`) for import-graph reasons; see `mcp-servers/minionsos.md` for why.
- `projects/` — runtime projects created by Gru; gitignored. Each project lives at `projects/project_{port}/`.

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

### Runtime project model

Every project is identified by its EACN3 backend port and lives under `projects/project_{port}/`:

```text
projects/project_{port}/
├── CLAUDE.md                    # project narrative; author/Gru write, roles read
├── AGENTS.md                    # subagent's view of project context (mirrors CLAUDE.md)
├── meta.json                    # machine metadata
├── parent_repo.git/             # per-project bare git repo, seeded from author HEAD
├── branches/                    # git worktrees, one per role plus a shared tree
│   ├── main/                    # Gru — branch minionsos/project-{port}
│   ├── coder/                   # branch minionsos/project-{port}-coder
│   │   └── reel/<session_id>/   ← Layer 0: raw session traces (Reel)
│   │       ├── index.jsonl       JSONL index of captured subagent outputs
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
│       │   ├── log.md                      Append-only ingest/lint journal (JSONL)
│       │   ├── sources/{role}-{slug}.md    One page per ingested artifact (carries reel_ref)
│       │   └── contradictions/             Auto-detected claim conflicts (Ethics reads)
│       └── shelf/shelf.json               ← Layer 3: Gru cross-project structural index
├── eacn3_data/eacn3.db          # project-local EACN3 SQLite state (gitignored)
├── events/                      # per-agent EACN event JSONL audit stream (gitignored)
├── state/                       # runtime control state (gitignored)
│   ├── shared.lock              # flock used by mos_publish_to_shared
│   └── .reset_markers/          # mos_reset_context drops a marker per role
└── logs/                        # backend.log and role-{name}.log (gitignored)
```

Cross-role writes go through `mos_publish_to_shared(role, src_path, dst_subpath, commit_message)`, which holds `state/shared.lock`, copies the source file into `branches/shared/<dst_subpath>`, and commits on the shared branch. Per-role subdir policy lives in `minions/tools/publish.py` (`_ROLE_ALLOWED_SHARED_SUBDIRS`); the policy table is reproduced in `lookup.py --domain publish`. The Draft file is updated in place by `mos_draft_append`/`mos_draft_annotate` and flushed on a timer by Noter through `mos_draft_commit_shared`. The review surface (`reviews/`) is reserved for `mos_review_run`; `submissions/` is reserved for `mos_submit`; `book/` is Noter-only.

(Role-facing publish rules — what each role may write where — live in the role's `SYSTEM.md` plus `lookup.py --domain publish`. This file documents only the implementation: the lock + commit pipeline.)

The parent directory containing this repository is the **author seed repo**: at `mos_project_create` time, MinionsOS imports its current HEAD (excluding `MinionsOS/` itself and any file larger than 500 MB) into a per-project bare git repo at `projects/project_{port}/parent_repo.git/`. All worktrees — main, role, shared — branch off that per-project bare repo, so the author repo is never written to and never gains `minionsos/*` branches. The seed source must be git-initialized; `./install.sh` warns about this and `./mos doctor` re-checks it. To override the seed source, set `gru.yaml:author_repo` (or `MINIONS_AUTHOR_REPO`). To override the projects directory, set `gru.yaml:projects_root` (or `MINIONS_PROJECTS_ROOT`); the default is `MinionsOS/projects/`.

### Mission profiles

A *Mission Profile* is a project-level YAML manifest under `minions/profiles/<name>.yaml` that decouples the runtime topology from the "always a paper" assumption. Each profile declares:

- `roles_active`: which Roles spawn at `mos_project_create` time (e.g. scientific-paper bootstraps `gru/ethics` and auto-spawns one generalist `expert`).
- `role_prompt_overlay`: per-role markdown overlay paths appended to the role's `SYSTEM.md` so a profile can reshape Role focus without forking prompts.
- `deliverable_schema`: required output paths under `branches/shared/`, plus a per-role `publish_whitelist` overriding the default scientific-paper baseline. The default whitelist (in `minions/tools/publish.py`) is the fallback when no profile is set.
- `evaluation`: strategy + reference path. The single strategy is `scientific_peer_review`, which dispatches through `mos_evaluate` and delegates to `mos_review_run`.
- `phase_schema`: `scientific_three_stage` (exploration → experiment → writing → review) or `minimal` (no phase progression).
- `on_done`: `none` (default), `dormant`, or `shutdown_project` once the deliverable is submitted+evaluated.

The two MCP entry points that close the deliverable lifecycle:

- `mos_submit(port, payload, kind)` — Role asks Gru to persist a deliverable (kinds: `paper` / `patch` / `report`) under `branches/shared/submissions/` and commit on the shared branch.
- `mos_evaluate(port)` — Gru runs the project's profile-defined evaluation strategy (`scientific_peer_review`, which delegates to `mos_review_run`) and returns `{score, verdict, details}`.

Available profiles ship in `minions/profiles/`:

| Profile | Use case | Roles | Evaluation | Deliverable |
|---|---|---|---|---|
| `scientific-paper` (default) | Full Autonomous Scientific Discovery — peer-reviewed paper | gru, ethics, expert (one generalist auto-spawned) | `scientific_peer_review` (mos_review_run) | `branches/shared/notes/`, `exp/`, `ethics/`, `reviews/` |

To add a new profile: drop `minions/profiles/<name>.yaml` matching the `MissionProfile` schema in `minions/profiles/__init__.py`, optionally add a role-prompt overlay, and (if needed) extend `mos_evaluate` with a new strategy in `minions/tools/evaluator.py`.

### Role lifecycle and boundaries

**Note for developers:** Role *runtime protocol* (wake loop, Plan→Dispatch→Verify, EACN behaviour, write-scope rules) is canonicalized in `minions/roles/SYSTEM.md` (the common contract) and `minions/roles/{role}/SYSTEM.md` (role-specific scope). This section covers only architecture facts — what's wired where, who can spawn what, the authz table — that a contributor needs to read code. Do **not** restate runtime rules here; if a rule belongs to a Role, it lives in SYSTEM.md.

**Architecture facts:**

- Each Role is a long-lived `claude` process inside its own tmux session named `mos-{port}-{role}`.
- The wake driver for EACN-registered roles is `mos_await_events()` in `minions/tools/await_events.py` (wraps the project-local 60-second `GET /api/events/{agent_id}` long-poll, drains events on read, runs an idle-check after ~5 minutes of silence). Heartbeat writes between polls feed the Gru sidecar watchdog.
- **Noter** is not on EACN3 — it uses `mos_noter_wait()` (timer-based, default 3 min) and reads `events/*.jsonl` plus `branches/shared/` for observation. Runs on Sonnet (`gru.yaml: noter_model`).
- **Writer** is on-demand — not bootstrapped at project creation. Gru spawns via `mos_spawn_role(role="writer")` when the project enters a paper-writing phase.
- Only Gru may spawn EACN-visible agents or use `mos_project_*`, `mos_spawn_*`, `mos_project_bridge`. Subagents/local teams inside a Role are EACN-invisible by design — no `eacn3_*` tools, not in `projects.json`.
- Claude Code is the only Role host (honors CLI `--allowed-tools` for tool gating).
- MinionsOS MCP server-side authorization in `minions/tools/mcp_server.py` must remain aligned with `minions.config.resolve_whitelist` so the same boundary applies regardless of which surface a tool call comes through.

Tool/write boundaries (main role write scope; subagents inherit from their parent main role):

| Agent | Project-local EACN access | Experiment tools | Gru/project/spawn tools | Own branch | Shared subdirs (via mos_publish_to_shared) |
|---|---|---|---|---|---|
| Gru main | `eacn3_send_message` (out) + read-only inspection (`eacn3_get_events`/`get_messages`/`list_tasks`/`get_task`/`list_agents`/`get_agent`/`health` etc.). Task-creation tools server-side denied — see common contract §7 + Gru §G2. | no | yes | `branches/main/` | any subdir |
| Noter main | `mos_noter_wait` (timer, no EACN) | no | no | `branches/noter/` (drafts) | `notes/`, `draft/`, `handoffs/`, `book/` |
| Coder main | `eacn3_*` | yes | no | `branches/coder/` | `exp/`, `handoffs/`, `governance/` |
| Writer main (on-demand) | `eacn3_*` plus paper-search MCP tools | no | no | `branches/writer/` | `handoffs/`, `governance/` |
| Expert main | `eacn3_*` | no | no | `branches/<expert>/` (read-mostly) | `handoffs/`, `governance/` |
| Ethics main | `eacn3_*` | no | no | `branches/ethics/` (drafts) | `ethics/`, `handoffs/`, `governance/` |
| All roles (read) | - | - | - | - | `book/` (via `mos_book_query`/`hot_get`/`save_synthesis`/`audit_walk`/`resolve_contradiction`) |

**Memory tool authz detail** (tools not captured in column headers above):

| Tool | Allowed callers | Notes |
|---|---|---|
| `mos_reel_get` / `mos_reel_window` | self; Ethics (cross-role R); Gru (cross-role R) | Peer roles denied. Noter excluded entirely. |
| `mos_book_ratify` | Ethics only | Promotes verified Book page; server-side authz gate (Stream 3). |
| `mos_book_open_question` | All EACN-visible roles | Creates a pending-question node for Noter to resolve. |
| `mos_book_dead_end` | Noter (direct); other roles propose via handoff → Noter ingests | Prevents direct write pollution of Book's dead-end registry. |
| `mos_draft_annotate` | All roles for own nodes; Ethics for any node's `support_status` | Ethics is the sole cross-role annotator of ratification fields. |

Profile-specific publish detail: `branches/shared/submissions/` access is granted per-role through the active profile's `publish_whitelist[role]` list. The default `publish_whitelist` baseline lives in `minions/tools/publish.py`.

Visual format-check tools (`mos_visual_render`, `mos_visual_inspect`, `mos_visual_check`) are available to every EACN-visible role (Gru, Coder, Writer, Ethics, Expert) and denied to Noter; reports persist under `branches/<role>/visual-reports/` and are referenced cross-role by EACN message rather than via a shared subdir.

**Deliverable lifecycle tools.** `mos_submit` and `mos_evaluate` are Gru-only (whitelist + server-side authz). Other Roles must surface a deliverable to Gru by EACN message; Gru then calls `mos_submit` to persist it under `branches/shared/submissions/` and `mos_evaluate` to score it via the profile-defined strategy. The lifecycle separation matches the existing "Gru is the control plane" rule.

**Reel (L0) layer.** Every EACN-visible role gets `mos_reel_get` / `mos_reel_window` for drill-down access into its own raw session transcripts at `branches/<role>/reel/<session_id>/`. Gru holds cross-role read permission (so it can audit any role's reasoning when bridging projects or evaluating role evolution); non-Gru roles can only read their own reel. Noter is excluded from the reel surface — it observes the project through events/* and the Draft, not through other roles' transcripts. Capture is automatic: the `reel_capture` PostToolUse hook archives every `Agent` / `Task` output into the calling role's reel directory; roles never call reel-write tools directly. Draft / Book frontmatter carries a `reel_ref` pointer that auditors can follow back to the original execution frame.

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

Roles are cold-started each invocation. There are no per-role private memory
files. Persistent memory spans four layers (L0 → L3) plus a federated future
(L4 Library, vision). The reference table for all four layers — the writers,
the file paths, the MCP read tools — lives in **`MANUAL/domains/memory.md`**
(canonical) and is also discoverable via
`python3 MANUAL/scripts/lookup.py --domain memory`. Roles fetch that page on
demand instead of carrying the table in their always-loaded context.

Quick orientation only:

- **L0 Reel** — raw subagent transcripts; drill-down only, not wake-injected.
- **L1 Draft** — process graph at `branches/shared/draft/draft.json`; every
  EACN role writes via `mos_draft_*`.
- **L2 Book** — Noter-curated durable knowledge at `branches/shared/book/`.
- **L3 Shelf** — Gru-aggregated cross-project structural index derived from Book.

Roles reconstruct context at wake-up from current transcript + Draft summary
(especially `pending_plan` nodes) + EACN history + shared artefacts. The root
and project `CLAUDE.md` files are *human-side* documentation: a Role process
does not load this file at wake; the always-injected contract is
`minions/roles/SYSTEM.md`.

### Evidence-first EACN communication

Substantive EACN messages from roles should be tagged with one of
`[evidence: <path|sha|url|event_id>]`, `[speculation]`, or `[derived: <base>]`.
Ethics audits unmarked claim ratios statistically. The same rule is restated
in `minions/roles/SYSTEM.md` (the on-wake contract) and indexed under
`MANUAL/domains/eacn3.md`; this file is the human-side documentation only.

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
| Project backend | `projects/project_{port}/logs/backend.log` |
| Role crash or behavior | `projects/project_{port}/logs/role-{name}.log` |
| Project metadata | `projects/project_{port}/meta.json` |
| EACN3 state | `projects/project_{port}/eacn3_data/eacn3.db` |
| Experiment failure | `projects/project_{port}/branches/shared/exp/exp-{id}/report.md` |
| Viz process | `./viz status` and `./viz logs` |

## Extension points

- New Role: add `minions/roles/{role}/SYSTEM.md`, update role whitelist/configuration, update the root whitelist table, and add unit coverage.
- New Role skill: add `minions/roles/{role}/skills/{slug}.md`; discovery is automatic through `minions.lifecycle.skills`.
- New review output shape: update the relevant `minions/review/templates/*.md`, the matching review skill in `minions/review/skills/`, and the test pinning the `mos_review_run` invariants.
- New Expert domain: add `minions/domains/{slug}.md`; keep it as a reusable prompt asset and add discovery/injection tests if runtime behavior changes.
- New MCP tool: add it under `minions/tools/`, register it in the MCP server, update whitelist rules, and add tests.
- New mission profile: add `minions/profiles/{name}.yaml` (and any role overlays under `minions/profiles/{name}/`), validate it loads via `minions.profiles.load_profile`, and add tests under `tests/unit/test_profiles.py`. If the profile needs a new evaluation strategy, extend `minions/tools/evaluator.py`.
