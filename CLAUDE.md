# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. **Claude Code is the primary and default agent host** for every Role. Codex is no longer used to host a Role process directly — it is reachable as a sub-agent through the `codex-bridge` MCP server (`tools/codex-bridge/`) when a Role wants to delegate high-intensity execution to GPT-5.5. Keep that delegation path working when refactoring; do not ground new Role behavior in Codex-as-host.

## Project overview

MinionsOS is a local multi-agent operating system for running autonomous research projects. A persistent Gru process supervises many isolated paper-sized projects; each project has its own EACN3 backend, git worktree, artifacts, logs, role scratchpads, and long-lived Role processes hosted by Claude Code. Roles may delegate high-intensity execution to Codex GPT-5.5 through the `codex-bridge` MCP, but Codex never hosts a Role process directly.

`EACN3/` is a local editable dependency pinned through `pyproject.toml` and `uv.lock`. Treat it as a dependency boundary during normal MinionsOS work: prefer EACN MCP tools and the MinionsOS adapter modules over hand-written HTTP calls or incidental edits inside `EACN3/`.

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

Use `uv` for Python environment management. Do not use `pip`, `conda`, `mamba`, `virtualenv`, or bare `python -m venv` in workflow steps. The package requires Python 3.11+ and uses `uv.lock` plus the editable `EACN3` source configured in `pyproject.toml`.

## Architecture map

### Root layout

- `minions/` — Python package and main implementation.
- `minions/bin/gru`, root `gru`, `minionsos`, `mos`, `viz` — launcher scripts/symlinks.
- `minions/config/` — example Gru and experiment-target configs copied by `install.sh`.
- `minions/state/` — runtime Gru state, including `projects.json` and Gru logs; gitignored runtime data.
- `minions/roles/SYSTEM.md` — common Role contract injected before each role-specific prompt.
- `minions/roles/{role}/SYSTEM.md` — role prompts for Gru, Noter, Coder, Experimenter, Writer, Ethics, and Expert.
- `minions/roles/{role}/skills/*.md` — optional role skills discovered at wake-up.
- `minions/review/` — paper-review prompt assets (SYSTEM.md, skills, personas, templates) consumed by the `mos_review_run` MCP tool. Review is **not** a Role and is not registered on EACN.
- `minions/domains/*.md` — Expert domain packs used as reusable specialty assets.
- `minions-viz/` — read-only Observatory dashboard, Express/WebSocket server plus React/Vite frontend.
- `EACN3/` — local editable EACN3 dependency.
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
- `minions/tools/experiment_ssh.py` implements Experimenter `mos_exp_*` local/SSH execution tools, including queue-facing `exp_queue_*` and `exp_gpu_pool_*`.
- `minions/tools/experiment_scheduler.py` keeps the SQLite-backed project experiment queue and GPU packing logic.
- `minions/tools/paper_search.py` implements Writer paper-search helpers exposed through MCP.
- `minions/tools/whitelist.py` resolves allowed tool surfaces for main roles vs. subagents.
- `tools/codex-bridge/` is a standalone Node MCP server that bridges Claude Code roles to Codex GPT-5.5 for high-intensity execution (`ask_codex` for read-only analysis, `run_codex_worker` for full-access sub-agent delegation).

### Runtime project model

Every project is identified by its EACN3 backend port and lives under `project_{port}/`:

```text
project_{port}/
├── CLAUDE.md              # project narrative; author/Gru write, roles read
├── AGENTS.md              # Codex-bridge subagent's view of project context (mirrors CLAUDE.md)
├── meta.json              # machine metadata
├── workspace/             # git worktree on branch minionsos/project-{port}
├── eacn3_data/eacn3.db    # project-local EACN3 SQLite state
├── memory/{role}.md       # L2 role scratchpads
├── artifacts/             # notes, reviews, ethics reports, experiments, feedback
└── logs/                  # backend.log and role-{name}.log
```

The parent directory containing this repository must be a git repository before `mos_project_create`, because MinionsOS creates per-project worktrees from the parent repo. `./install.sh` warns about this and `./mos doctor` re-checks it.

### Role lifecycle and boundaries

Roles are event-driven and ephemeral. No Role should run a long-lived agent-host process or implement an in-agent polling loop. Every active project agent, including Noter and the per-project Gru queue agent, must be registered as an AgentCard on that project's Local EACN3 network.

Each Role is a long-lived `claude` process running inside its own tmux session named `mos-{port}-{role}`. The Role drives its event loop with `mos_await_events()` (in `minions/tools/await_events.py`), which wraps the project-local 60-second `GET /api/events/{agent_id}` long-poll, drains events on read, runs an idle-check after ~5 minutes of silence, and only returns when there is actionable content. Heartbeat writes happen between polls so the Gru sidecar watchdog can spot a dead session and respawn it. Roles respond with raw `eacn3_send_message` / `eacn3_create_task` / `eacn3_submit_bid` / `eacn3_submit_result` and stay resident across many cycles. They do not call `eacn3_await_events` / `eacn3_next` / `eacn3_get_events` directly — that bypasses the wrapper and drops the suggested-action annotations.

Only Gru may spawn EACN-visible agents or use `mos_project_*`, `mos_spawn_*`, and `mos_project_bridge` tools. Subagents or local teams created inside a Role are EACN-invisible by design: they do not have `eacn3_*` tools and do not appear in `projects.json`.

Claude Code is the only Role host. It honors CLI `--allowed-tools` for tool gating. The `codex-bridge` MCP exposes Codex GPT-5.5 to Roles as a delegation target (`ask_codex` for read-only analysis, `run_codex_worker` for full-access sub-agent delegation); it does not host a Role process. MinionsOS MCP server-side authorization in `minions/tools/mcp_server.py` must remain aligned with `minions.config.resolve_whitelist` so the same boundary applies regardless of which surface a tool call comes through.

Tool/write boundaries:

| Agent | Project-local EACN access | Experiment tools | Codex bridge | Gru/project/spawn tools | Workspace writes |
|---|---|---|---|---|---|
| Gru main | `eacn3_*` (events delivered by scheduler) | no | `codex` | yes | yes |
| Gru subagent | no | no | no | no | yes |
| Noter main | `eacn3_*` (read-mostly) | no | no | no | `artifacts/notes/` only |
| Noter subagent | no | no | no | no | no |
| Coder main | `eacn3_*` | no | `codex` | no | yes |
| Coder subagent | no | no | `codex` | no | yes |
| Experimenter main | `eacn3_*` | yes | `codex` | no | yes |
| Experimenter subagent | no | yes | `codex` | no | yes |
| Writer main | `eacn3_*` plus paper-search MCP tools | no | `codex` | no | yes |
| Writer subagent | paper-search MCP tools only | no | no | no | yes |
| Expert main | `eacn3_*` | no | `codex` | no | yes, but preferably read-mostly |
| Expert subagent | no | no | `codex` | no | yes, but preferably read-mostly |
| Ethics main | `eacn3_*` | no | `codex` | no | `artifacts/ethics/` only |
| Ethics subagent | no | no | `codex` | no | no |

Noter must not write to `workspace/`. The review surface (`artifacts/reviews/round-<n>/` and `artifacts/reviews/summaries/`) is owned exclusively by the spawned process from `mos_review_run`; no Role writes there.

### Role skills and review workflow

Role skills are markdown procedure guides under `minions/roles/{role}/skills/`. `minions.lifecycle.skills.list_skills` discovers them at wake-up, extracts one-line summaries, and injects a `[Skills]` block pointing to the full files. Skills should stay procedural and cross-domain; put domain-specific content under `minions/domains/`.

Review is run by Gru's `mos_review_run` MCP tool, not by a long-lived Role. Its prompt assets live under `minions/review/`:

- `minions/review/SYSTEM.md` — Area-Chair / Editor system prompt for the spawned `claude --print` process.
- `minions/review/skills/*.md` — `run-review-round`, `simulate-reviewer-instance`, `aspect-review`, `code-validity-review`, `revision-delta`, `finalize-review-packet`.
- `minions/review/personas/*.md` — short reviewer stances used by aspect subagents.
- `minions/review/templates/*.md` — required outputs: `aspect-note.md`, `reviewer-instance.md`, `fresh.md`, `revision_delta.md`, `consolidated.md`, `summary.md`, plus the `submission-checklist.md` Writer attaches when submitting.

A review round's Pass A must produce 3-5 independent reviewer-instance reports before reading prior review history. History enters only through the previous rolling summary during Pass B / Pass C.

### Layered memory

Roles are cold-started each invocation. Reconstruct role context from:

1. current transcript,
2. `project_{port}/memory/{role}.md`,
3. project artifacts and EACN history,
4. root and project `CLAUDE.md` files.

Role scratchpads are working memory, not transcript dumps. They are size-policed by `minions/lifecycle/wakeup.py`: soft at 10%, hard at 15%, veto at 20% of the model context estimate.

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
| Experiment failure | `project_{port}/artifacts/exp-{id}/report.md` |
| Viz process | `./viz status` and `./viz logs` |

## Extension points

- New Role: add `minions/roles/{role}/SYSTEM.md`, update role whitelist/configuration, update the root whitelist table, and add unit coverage.
- New Role skill: add `minions/roles/{role}/skills/{slug}.md`; discovery is automatic through `minions.lifecycle.skills`.
- New review output shape: update the relevant `minions/review/templates/*.md`, the matching review skill in `minions/review/skills/`, and the test pinning the `mos_review_run` invariants.
- New Expert domain: add `minions/domains/{slug}.md`; keep it as a reusable prompt asset and add discovery/injection tests if runtime behavior changes.
- New MCP tool: add it under `minions/tools/`, register it in the MCP server, update whitelist rules, and add tests.
