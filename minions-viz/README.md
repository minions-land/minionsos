# MinionsOS — Project Observatory

Local read-only dashboard for the MinionsOS V2 autonomous-research system.
**One viz process serves every Gru installation on the host**, filtered in
the UI by a two-level **Gru → Project** picker.

1. A **Gru picker** lists every MinionsOS_V2 checkout registered in
   `~/.minionsos/grus.json`, with an online/stale freshness badge.
2. A **Project picker** then lists that Gru's projects (from its own
   `minions/state/projects.json`), with a "← Switch Gru" back-affordance.
3. Per-project live view of that project's **own EACN3 backend** at
   `http://127.0.0.1:{port}` (tasks, agents, cluster, event log) plus
   MinionsOS filesystem state (CLAUDE.md, meta.json, role scratchpads
   with token-usage thresholds, artifacts tree, logs).
4. Switch Gru or Project at any time from the top bar (two side-by-side
   dropdowns).

Everything is **strictly read-only** — no POSTs to EACN3, and we never
call `/api/events/{agent_id}` (that drains real queues).

## Stack

Express + WebSocket server → React + Vite + Tailwind frontend. Single
machine-wide singleton process, default port **7891** (scans 7891..7910
for a free port).

## Run

**Integrated (primary path).** From any MinionsOS_V2 checkout:

```bash
./install.sh        # builds minions-viz/dist on first run; creates ~/.minionsos/
./gru               # registers this Gru + starts the singleton viz
# Manual control:
./viz ensure                      # register + start (no-op if already up)
./viz start|stop|status|open|logs
./viz register|deregister|heartbeat
./mos viz start|stop|status|open|logs
```

Env knobs: `GRU_VIZ=0` to disable auto-start, `GRU_VIZ_OPEN=0` to suppress
browser open, `MINIONS_VIZ_PORT=N` to override the port, and
`MINIONS_VIZ_REBUILD=1` to force a rebuild during `./install.sh`.

**Dev fallback** (only when hacking on the viz itself):

```bash
cd minions-viz
npm install
npm run build
npm start          # http://localhost:7891
```

Dev mode with live reload:

```bash
npm run dev
```

Environment variables:

| Var            | Default                                      | Purpose                                   |
|----------------|----------------------------------------------|-------------------------------------------|
| `PORT`         | `7891`                                       | Observatory HTTP/WebSocket port           |
| `MINIONS_ROOT` | parent of `minions-viz/` (i.e. `MinionsOS_V2/`) | Where `minions/state/projects.json` lives |

## How project discovery works

- The server polls `MINIONS_ROOT/minions/state/projects.json` every 5 s and
  broadcasts the list over WebSocket.
- Each project is pinned to a **unique port** that is both its identifier and
  its local EACN3 backend port. Only one EACN3 backend runs per project.
- A project's EACN3 backend is only polled when a connected browser has that
  project selected — idle projects are never touched.
- Filesystem views (Overview / Roles / Artifacts / Logs) work even when the
  EACN3 backend for the selected project is not running.

## Tabs

- **Overview** — `CLAUDE.md` + `meta.json` + branch / venue fields.
- **Roles** — cards per role with state / PID / poll interval. Click to open a
  drawer with that role's scratchpad (L2 memory) and a token-usage bar:
  green < 10 %, amber 10–15 %, red 15–20 %, black ≥ 20 % of a 1 M-token window.
- **Dashboard / EACN Agents / Tasks / Task Tree / Event Log** — the live EACN3
  views, scoped to the selected project's backend.
- **Artifacts** — shallow tree of `project_{port}/artifacts/` with an inline
  text/markdown previewer.

## HTTP API (read-only)

```
GET /api/mos/projects
GET /api/mos/roles
GET /api/mos/project/:port/overview
GET /api/mos/project/:port/scratchpads
GET /api/mos/project/:port/scratchpad/:role
GET /api/mos/project/:port/artifacts
GET /api/mos/project/:port/artifact?path=<rel>
GET /api/mos/project/:port/log?which=backend|role:<name>|gru&tail=500
GET /api/snapshot?port=<port>
```

## WebSocket protocol (`/ws`)

Client → server:

```json
{ "type": "select_project", "port": 37596 }   // or null to return to picker
```

Server → client:

```
snapshot             initial full state for the client's selection
projects:update      list of MosProject (every 5 s)
selected_project     ack of select_project
tasks:update         per-project EACN3 task list
agents:update        per-project enriched agents
cluster:update       per-project cluster status
logs:update          per-project EACN3 admin event log tail
connection:status    EACN3 backend up/down for client's selected port
```

All updates other than `snapshot` / `projects:update` / `selected_project`
are port-scoped — the server only sends them to clients whose selection
matches.

## What we never do

- No POST / PUT / DELETE to any EACN3 backend.
- No calls to `/api/events/{agent_id}` — that would drain a real agent's
  queue (see `AGENTREAD.md` §6).
- No writes to `EACN3/` (git submodule) or to `minions/`.

All writes live under `minions-viz/`.
