# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MinionsOS V2 is a multi-agent operating system for running autonomous research projects. A persistent Gru process supervises many isolated paper-sized projects; each project has its own EACN3 backend, git worktree, artifacts, logs, role scratchpads, and ephemeral Claude Role subprocesses.

`EACN3/` is a git submodule and dependency. Do not edit files inside `EACN3/`; upgrade it by replacing the submodule. All EACN operations should go through the EACN MCP tools, not hand-written HTTP calls.

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
./mos role list <port>
./mos role dismiss <port> <role>
./mos logs --project <port>
./mos logs --role <role> --tail 50

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
- `minions/roles/{role}/SYSTEM.md` — role prompts for Gru, Noter, Coder, Experimenter, Writer, Reviewer, Ethics, and Expert.
- `minions/roles/{role}/skills/*.md` — optional role skills discovered at wake-up.
- `minions/domains/*.md` — Expert domain packs appended to Expert prompts at spawn time.
- `minions-viz/` — read-only Observatory dashboard, Express/WebSocket server plus React/Vite frontend.
- `project_{port}/` — runtime projects created by Gru; gitignored.

### Python package responsibilities

- `minions/cli.py` is the `mos` CLI entry point and dispatches project, role, logs, doctor, and viz commands.
- `minions/gru/loop.py` runs the Gru monitor loop and starts the Python-side wake-up scheduler.
- `minions/lifecycle/project.py` implements project create/close/dormant/revive behavior, including project directories, metadata, worktrees, backends, and artifacts.
- `minions/lifecycle/role.py` registers roles, invokes ephemeral role subprocesses, and dismisses roles.
- `minions/lifecycle/wakeup.py` contains `WakeupScheduler`, which polls EACN3 on each role cadence, deduplicates events, and invokes roles only when work arrives.
- `minions/lifecycle/eacn_client.py` is the thin EACN3 HTTP client used by the scheduler and lifecycle code.
- `minions/lifecycle/relay.py` implements the Gru-only cross-project relay path.
- `minions/state/` contains file-backed state management and port allocation.
- `minions/tools/mcp_server.py` exposes lifecycle operations as FastMCP tools.
- `minions/tools/experiment_ssh.py` implements Experimenter `exp_*` local/SSH execution tools.
- `minions/tools/whitelist.py` resolves allowed tool surfaces for main roles vs. subagents.

### Runtime project model

Every project is identified by its EACN3 backend port and lives under `project_{port}/`:

```text
project_{port}/
├── CLAUDE.md              # project narrative; author/Gru write, roles read
├── meta.json              # machine metadata
├── workspace/             # git worktree on branch minionsos/project-{port}
├── eacn3_data/eacn3.db    # project-local EACN3 SQLite state
├── memory/{role}.md       # L2 role scratchpads
├── artifacts/             # notes, reviews, ethics reports, experiments, feedback
└── logs/                  # backend.log and role-{name}.log
```

The parent directory containing this repository must be a git repository before `project_create`, because MinionsOS creates per-project worktrees from the parent repo. `./install.sh` warns about this and `./mos doctor` re-checks it.

### Role lifecycle and boundaries

Roles are event-driven and ephemeral. No Role should run a long-lived Claude process or implement an in-Claude polling loop. The Python `WakeupScheduler` polls EACN3 at configured cadences (`1m`, `3m`, or `5m`) and launches short-lived Claude subprocesses seeded with the Role `SYSTEM.md`, discovered skills, scratchpad context, and event batch.

Only Gru may spawn EACN-visible agents or use `project_*`, `spawn_*`, and `gru_relay` tools. Subagents and Claude teams created inside a Role are EACN-invisible by design: they do not have `eacn3_*` tools and do not appear in `projects.json`.

Tool/write boundaries:

| Agent | EACN tools | Experiment tools | Gru/project/spawn tools | Workspace writes |
|---|---|---|---|---|
| Gru main | yes | no | yes | yes |
| Gru subagent | no | no | no | yes |
| Noter main | yes | no | no | `artifacts/notes/` only |
| Noter subagent | no | no | no | no |
| Coder main | yes | no | no | yes |
| Coder subagent | no | no | no | yes |
| Experimenter main | yes | yes | no | yes |
| Experimenter subagent | no | yes | no | yes |
| Writer main | yes | no | no | yes |
| Writer subagent | no | no | no | yes |
| Expert main | yes | no | no | yes, but preferably read-mostly |
| Expert subagent | no | no | no | yes, but preferably read-mostly |
| Reviewer main | yes | no | no | `artifacts/reviews/round-<n>/` only |
| Reviewer subagent | no | no | no | no |
| Ethics main | yes | no | no | `artifacts/ethics/` only |
| Ethics subagent | no | no | no | no |

Noter and Reviewer must not write to `workspace/`.

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
- New Expert domain: add `minions/domains/{slug}.md`; domain packs are discovered from that directory.
- New MCP tool: add it under `minions/tools/`, register it in the MCP server, update whitelist rules, and add tests.
