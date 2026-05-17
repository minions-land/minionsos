# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. The runtime supports both Claude Code and Codex as agent hosts: Claude Code reads this file directly via `--append-system-prompt`; Codex reads `AGENTS.md` at the repo root (developer guidelines) plus role-specific AGENTS.md files inside each role's branch worktree. Keep this file aligned with `AGENTS.md` so both hosts see the same operating assumptions.

## Project overview

MinionsOS is a local multi-agent operating system for running autonomous research projects. A persistent Gru process supervises many isolated paper-sized projects; each project has its own EACN3 backend, per-role git branches under `branches/`, artifacts, logs, role scratchpads, and ephemeral Role subprocesses launched through the configured agent host (`codex` by default, `claude` when explicitly selected).

`EACN3/` is a local editable dependency pinned through `pyproject.toml` and `uv.lock`. Treat it as a dependency boundary during normal MinionsOS work: prefer EACN MCP tools and the MinionsOS adapter modules over hand-written HTTP calls or incidental edits inside `EACN3/`.

## Common commands

```bash
# Install / refresh dependencies and generated config files
./install.sh
uv sync

# Launch Gru / CLI entry points
./gru
MINIONS_AGENT_HOST=codex ./gru
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

Use `uv` for Python environment management. Do not use `pip`, `conda`, `mamba`, `virtualenv`, or bare `python -m venv` in workflow steps. The package requires Python 3.11+ and uses `uv.lock` plus the editable `EACN3` source configured in `pyproject.toml`.

## Architecture map

### Root layout

- `minions/` — Python package and main implementation.
- `minions/bin/gru`, root `gru`, `minionsos`, `mos`, `viz` — launcher scripts/symlinks.
- `minions/config/` — example Gru and experiment-target configs copied by `install.sh`.
- `minions/state/` — runtime Gru state, including `projects.json`, Gru logs, and the auto-generated `codex-gru.AGENTS.md` Codex-Gru contract file; gitignored runtime data.
- `minions/roles/SYSTEM.md` — common Role contract injected before each role-specific prompt.
- `minions/roles/common/skills/*.md` — shared skills auto-discovered for every role (e.g. `eacn-network-collaboration.md`).
- `minions/roles/{role}/SYSTEM.md` — role prompts for Gru, Noter, Coder, Experimenter, Writer, Reviewer, Ethics, and Expert.
- `minions/roles/{role}/skills/*.md` — optional role-specific skills discovered at wake-up alongside the common skills.
- `minions/roles/reviewer/personas/*.md` and `templates/*.md` — reviewer stance files and required review output formats.
- `minions/domains/*.md` — Expert domain packs used as reusable specialty assets.
- `minions-viz/` — read-only Observatory dashboard, Express/WebSocket server plus React/Vite frontend.
- `EACN3/` — local editable EACN3 dependency. Do not modify.
- `project_{port}/` — runtime projects created by Gru; gitignored.

### Python package responsibilities

- `minions/cli.py` is the `mos` CLI entry point and dispatches project, role, logs, doctor, and viz commands.
- `minions/gru/loop.py` runs the Gru monitor loop and starts the Python-side wake-up scheduler.
- `minions/lifecycle/project.py` implements project create/close/dormant/revive behavior, including project directories, metadata, per-role branch worktrees, backends, and artifacts. Also owns `migrate_legacy_scratchpads` for projects that predate the `branches/` layout.
- `minions/lifecycle/agent_host.py` builds Claude Code and Codex subprocess invocations.
- `minions/lifecycle/role.py` registers roles, builds common+role system prompts, injects skills, writes each role branch's AGENTS.md for Codex, invokes ephemeral role subprocesses through the selected agent host, and dismisses roles.
- `minions/lifecycle/mos_pool.py` is the MOS Agent Pool: thin wrappers over EACN3 (`mos_await_events`, `mos_send_message`, `mos_create_task`, `mos_ack_clear`, `mos_pending_read`) that add a per-wake local ACK crash-shim. This is the standard EACN3 surface for all internal roles.
- `minions/lifecycle/wakeup.py` contains `WakeupScheduler`. In `hooks` mode (default) it reads local wake signals and EACN3 pending-count metadata; it does **not** drain role queues. The legacy `legacy` mode is retained as a compatibility fallback.
- `minions/lifecycle/session_archive.py` copies each wake's Claude/Codex session jsonl into `branches/<role>/.minionsos/sessions/` for Noter observability.
- `minions/lifecycle/hooks.py` + `minions/lifecycle/wake_signals.py` route project lifecycle events into the wake scheduler.
- `minions/lifecycle/eacn_client.py` is the thin EACN3 HTTP client used by the scheduler, `mos_pool`, and lifecycle code.
- `minions/lifecycle/agent_registry.py` and `eacn_identity.py` keep project-local AgentCard identities stable.
- `minions/lifecycle/relay.py` implements the Gru-only cross-project relay path.
- `minions/lifecycle/project_eacn.py` implements a legacy project-local EACN adapter used by `noter_terminal` and a small number of tests. New code should use `mos_pool` instead.
- `minions/lifecycle/gru_actions.py` keeps deprecated compatibility wrappers for older Gru message/task names.
- `minions/lifecycle/gru_inbox.py` is the private Gru pending journal, retained for debugging via `gru_inbox_poll`. The main Gru path is `mos_await_events`.
- `minions/state/` contains file-backed state management and port allocation.
- `minions/tools/mcp_server.py` exposes lifecycle operations as FastMCP tools. It enforces per-role tool authorization via `_require_tool_allowed` using `minions.config.resolve_whitelist`.
- `minions/tools/eacn3_mcp_proxy.py` is a stdio MCP proxy that trims EACN3's tool surface for the active role. The `minions-role` profile (current default in `.codex/config.toml`) mirrors `resolve_whitelist(...)` so Codex-side EACN3 matches Claude's `--allowed-tools`.
- `minions/tools/experiment_ssh.py` implements Experimenter `exp_*` local/SSH execution tools, including queue-facing `exp_queue_*` and `exp_gpu_pool_*`.
- `minions/tools/experiment_scheduler.py` keeps the SQLite-backed project experiment queue and GPU packing logic.
- `minions/tools/paper_search.py` implements Writer paper-search helpers exposed through MCP.

### Runtime project model

Every project is identified by its EACN3 backend port and lives under `project_{port}/`:

```text
project_{port}/
├── CLAUDE.md                 # project narrative; author/Gru write, roles read
├── AGENTS.md                 # Codex shim pointing at CLAUDE.md
├── meta.json                 # machine metadata
├── branches/                 # one git worktree per role
│   ├── main/                 # Gru's branch (= the project's main integration branch)
│   │   └── .minionsos/       # scratchpad.md, wake state, sessions/
│   ├── coder/                # Coder's branch
│   ├── writer/
│   ├── experimenter/
│   ├── reviewer/
│   ├── ethics/
│   ├── noter/
│   ├── expert-*/
│   └── shared/               # cross-role handoff area (not a git branch)
├── eacn3_data/eacn3.db       # project-local EACN3 SQLite state
├── artifacts/                # notes, reviews, ethics reports, experiments, feedback
└── logs/                     # backend.log, role-{name}.log, gru_inbox.jsonl
```

Each `branches/<role>/` is a git worktree on branch `minionsos/project-{port}-<role>` (Gru's `branches/main/` is on `minionsos/project-{port}`). Role scratchpads live at `branches/<role>/.minionsos/scratchpad.md` and are tracked on the role's branch. Codex auto-discovers each branch's `AGENTS.md` (written at wake time) as that role's contract.

The parent directory containing this repository must be a git repository before `project_create`, because MinionsOS creates per-project worktrees from the parent repo. `./install.sh` warns about this and `./mos doctor` re-checks it.

### Role lifecycle and boundaries

Roles are event-driven and ephemeral. No Role should run a long-lived agent-host process or implement an in-agent polling loop. Every active project agent, including Noter and the per-project Gru queue agent, is registered as an AgentCard on that project's Local EACN3 network. The Python `WakeupScheduler` observes pending-count metadata and local wake signals (`hooks` mode), and launches short-lived Claude Code or Codex subprocesses seeded with the shared `minions/roles/SYSTEM.md`, the Role `SYSTEM.md`, discovered skills (common + role), scratchpad context, identity/boundary context, any pending-inbox entries from a prior crashed wake, and the current event batch. Each launched wake enters the `mos_await_events` loop from the common SYSTEM.md Wake window protocol and exits when the process receives SIGTERM.

Only Gru may use `project_*`, `spawn_*`, `gru_relay`, and the project-lifecycle tools. Gru also retains `eacn3_*` wildcard access because Gru is the human's Global EACN3 terminal; internal work still flows through the MOS Agent Pool (`mos_*`). Subagents or local teams created inside a Role are EACN-invisible by design: they do not have `mos_*` or `eacn3_*` tools and do not appear in `projects.json`.

Claude Code receives CLI `--allowed-tools`; Codex does not expose that flag, so MinionsOS MCP server-side authorization in `minions/tools/mcp_server.py` must remain aligned with `minions.config.resolve_whitelist`, and the EACN3 MCP proxy's `minions-role` profile enforces the same per-role EACN3 surface Codex-side.

Tool/write boundaries:

| Agent | Project-local EACN access | Experiment tools | Gru/project/spawn tools | Branch writes |
|---|---|---|---|---|
| Gru main | MOS Agent Pool + full `eacn3_*` (Global scope) + `project_eacn_*` (legacy) + `gru_relay` | no | yes | `branches/main/`, `artifacts/`, scratchpad |
| Gru subagent | none | no | no | inside Gru branch |
| Noter main | MOS Agent Pool (own queue only) + non-destructive `eacn3_get_*` / `eacn3_list_*` | no | no | `artifacts/notes/`, scratchpad |
| Noter subagent | none | no | no | no |
| Coder main | MOS Agent Pool + non-destructive `eacn3_*` reads + non-drain writes (`eacn3_submit_bid` / `eacn3_submit_result` / `eacn3_close_task`) | no | no | `branches/coder/`, scratchpad |
| Coder subagent | none | no | no | inside Coder branch |
| Experimenter main | MOS Agent Pool + non-destructive `eacn3_*` reads + non-drain writes | yes | no | `branches/experimenter/`, `artifacts/exp-*/`, scratchpad |
| Experimenter subagent | none | yes | no | inside Experimenter branch |
| Writer main | MOS Agent Pool + non-destructive `eacn3_*` reads + non-drain writes + paper-search MCP | no | no | `branches/writer/`, scratchpad |
| Writer subagent | paper-search MCP only | no | no | inside Writer branch |
| Expert main | MOS Agent Pool + non-destructive `eacn3_*` reads + non-drain writes | no | no | `branches/<expert>/`, scratchpad (read-mostly) |
| Expert subagent | none | no | no | inside Expert branch (read-mostly) |
| Reviewer main | MOS Agent Pool + non-destructive `eacn3_*` reads + non-drain writes | no | no | `artifacts/reviews/`, scratchpad |
| Reviewer subagent | none | no | no | inside Reviewer branch (typically read-only) |
| Ethics main | MOS Agent Pool + non-destructive `eacn3_*` reads + non-drain writes | no | no | `artifacts/ethics/`, scratchpad |
| Ethics subagent | none | no | no | inside Ethics branch |

`non-destructive eacn3_* reads` = `eacn3_get_task`, `eacn3_get_messages`, `eacn3_list_*`, `eacn3_list_sessions`, etc. `non-drain writes` = `eacn3_submit_bid`, `eacn3_submit_result`, `eacn3_reject_task`, `eacn3_select_result`, `eacn3_close_task`, `eacn3_update_deadline`, `eacn3_update_discussions`, `eacn3_confirm_budget`, `eacn3_create_subtask`. These do not drain the agent's own event queue and remain available directly. All queue-draining, direct messaging, and task creation for internal roles goes through the MOS Agent Pool (`mos_await_events`, `mos_send_message`, `mos_create_task`, `mos_ack_clear`).

No role writes to another role's `branches/<other>/` directly; cross-role work flows through EACN tasks.

### Role skills and reviewer workflow

Role skills are markdown procedure guides. `minions.lifecycle.skills.list_skills` discovers shared skills under `minions/roles/common/skills/` and role-specific skills under `minions/roles/{role}/skills/` at wake-up, extracts one-line summaries, and injects a `[Skills]` block pointing to the full files. Shared skills include `eacn-network-collaboration.md` (MOS Agent Pool usage) and are auto-discovered for every role. Skills should stay procedural and cross-domain; put domain-specific content under `minions/domains/`.

Reviewer has extra review-round assets:

- `minions/roles/reviewer/personas/*.md` define short reviewer stances.
- `minions/roles/reviewer/skills/*.md` define review-round, reviewer-instance, aspect-note, code-validity, revision-delta, and publish procedures.
- `minions/roles/reviewer/templates/*.md` define the required outputs: `aspect-note.md`, `reviewer-instance.md`, `fresh.md`, `revision_delta.md`, `consolidated.md`, and `summary.md`.

Reviewer Pass A must produce 3-5 independent reviewer-instance reports before reading prior review history. History enters only through the previous rolling summary during Pass B / Pass C.

### Layered memory

Roles are cold-started each invocation. Reconstruct role context from:

1. current transcript,
2. `project_{port}/branches/<role>/.minionsos/scratchpad.md` (your role's compact scratchpad),
3. `project_{port}/branches/<role>/.minionsos/sessions/` (your own archived host sessions),
4. project artifacts and EACN history (`eacn3_get_messages`, `eacn3_list_tasks`, etc.),
5. root and project `CLAUDE.md` files.

Role scratchpads are working memory, not transcript dumps. They are size-policed by `minions/lifecycle/wakeup.py`: soft at 10%, hard at 15%, veto at 20% of the model context estimate.

### Evidence-first EACN communication

Substantive EACN messages from roles should include one of:

- `[evidence: <artifact path | commit SHA | URL | EACN event id>]`
- `[speculation]`
- `[derived: <base>]`

Ethics audits unmarked claim ratios statistically. This is a soft convention, but apply it when writing role prompts, templates, artifacts, and EACN-facing messages.

## Agent-host contract delivery

- **Claude Gru**: `minions/bin/gru` passes `--append-system-prompt "@minions/roles/gru/SYSTEM.md"`. Claude additionally reads `CLAUDE.md` in cwd.
- **Claude Role wake**: `minions/lifecycle/agent_host.py` passes `--append-system-prompt` pointing at the combined common+role SYSTEM.md (written to a temp file under `/tmp/minionsos-role-prompts/`). `--allowed-tools` carries the per-role whitelist.
- **Codex Gru**: `minions/bin/gru` generates `minions/state/codex-gru.AGENTS.md` (common + Gru SYSTEM.md combined) on every launch, then launches `codex --cd $REPO` with an inline prompt that tells Gru to read that file. Codex also auto-loads the repo-root `AGENTS.md` (developer guidelines, with a pointer to the Gru contract at the top).
- **Codex Role wake**: `minions/lifecycle/role.py` writes `branches/<role>/AGENTS.md` with the combined common+role SYSTEM.md, then launches `codex exec --cd <branch> --add-dir <project_dir>`; Codex auto-discovers `AGENTS.md` at cwd. Codex has no `--allowed-tools` equivalent, so tool authorization runs inside `mcp_server._require_tool_allowed` and in `eacn3_mcp_proxy.py` (the `minions-role` profile consults the same whitelist).

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
| Role scratchpad / wake state | `project_{port}/branches/{role}/.minionsos/` |
| Archived role session transcripts | `project_{port}/branches/{role}/.minionsos/sessions/*.jsonl` |
| Pending (un-ACK'd) wake inbox | `project_{port}/branches/{role}/.minionsos/inbox/pending.jsonl` |
| Project metadata | `project_{port}/meta.json` |
| EACN3 state | `project_{port}/eacn3_data/eacn3.db` |
| Experiment failure | `project_{port}/artifacts/exp-{id}/report.md` |
| Viz process | `./viz status` and `./viz logs` |

## Extension points

- New Role: add `minions/roles/{role}/SYSTEM.md`, add `("<role>", "main")` / `("<role>", "subagent")` entries to `_WHITELIST` in `minions/config/__init__.py`, update the boundary table above, add an entry to `ROLE_CLASSIFICATION` / `ROLE_WRITE_BOUNDARIES`, and add unit coverage.
- New Role skill: add `minions/roles/{role}/skills/{slug}.md` or `minions/roles/common/skills/{slug}.md`; discovery is automatic through `minions.lifecycle.skills`.
- New Reviewer output shape: update the relevant `minions/roles/reviewer/templates/*.md`, reviewer skill, and `tests/unit/test_reviewer_system_invariants.py`.
- New Expert domain: add `minions/domains/{slug}.md`; keep it as a reusable prompt asset and add discovery/injection tests if runtime behavior changes.
- New MCP tool: add it under `minions/tools/`, register it in the MCP server (`_MINIONS_MCP_TOOL_NAMES` and the `@mcp.tool()` function), update whitelist rules, and add tests. For EACN3-adjacent tools also update `eacn3_mcp_proxy.py` if a new profile filtering rule is needed.
