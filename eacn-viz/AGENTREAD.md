# AGENTREAD — MinionsOS Project Observatory (for AI agents)

This document explains how `eacn-viz/` is wired. It is the observatory for
**MinionsOS V2** and is a **machine-wide singleton**: every Gru installation
on the host shares one viz process reachable at one URL. Read
`/Users/mjm/MinionsOS_V2/CLAUDE.md` first for the system-level constitution.
This viz is a pure read-only observer; it is not an EACN agent and holds no
EACN credentials.

## 1. Big picture

```
browser ─ /ws (WebSocket)
         ─ /api/mos/* (read MinionsOS filesystem state)
         ─ /api/snapshot
              │
              ▼
   observatory server (Express + ws, default port 7891, scans 7891..7910)
              │
              ├─ ~/.minionsos/grus.json      (user-level Gru registry,
              │                                polled every 5 s; auto-touches
              │                                each Gru's last_seen on success)
              ├─ {gru.state_dir}/projects.json   (per-Gru project table)
              ├─ project_{port}/CLAUDE.md, meta.json, memory/*.md,
              │    artifacts/**, logs/*.log   (read-only; resolved as
              │    dirname(gruRootPath)/project_{port})
              └─ http://127.0.0.1:{port}/...  (per-project EACN3 backend;
                                               polled only while a client
                                               has (gruId, port) selected)
```

One observatory process, N Grus, M projects per Gru. Ports are globally
unique on the host (enforced by the PortAllocator in each Gru). The
two-level selection is **Gru → Project**.

## 2. User-level state

```
~/.minionsos/
├── grus.json           # Gru registry (see §3)
├── grus.lock           # advisory mkdir lock for registry writes
├── viz.pid             # running viz PID
├── viz.port            # running viz port
├── viz.url             # canonical URL string
└── viz.lock            # advisory lock for start/stop
```

Created by `./install.sh` with mode 0700.

## 3. Gru registry (`~/.minionsos/grus.json`)

```json
{
  "grus": [
    {
      "id": "<sha1(root_path) first 12 hex chars>",
      "label": "<human name; defaults to basename(dirname(root_path))>",
      "root_path": "/abs/path/to/MinionsOS_V2",
      "state_dir":  "/abs/path/to/MinionsOS_V2/minions/state",
      "parent_repo": "/abs/path/to/MinionsOS_V2/.. (project_{port} container)",
      "registered_at": "<iso>",
      "last_seen":     "<iso>"
    }
  ]
}
```

Lifecycle:

- **Register** — `./viz register` or `./viz ensure`; called automatically by `./gru`.
- **Heartbeat** — `./viz heartbeat`, **or** (preferred) the viz server itself
  auto-touches `last_seen` every time it successfully reads a Gru's
  `projects.json`. No separate heartbeat daemon is required.
- **Stale** — a Gru is `online=false` if both `last_seen` and the
  `projects.json` mtime are older than 2 minutes.
- **Deregister** — `./viz deregister` (manual / optional).

## 4. Machine-singleton viz

`./viz start` / `./viz ensure` acquire `~/.minionsos/viz.lock`, check
whether the recorded PID is alive and the URL health-responsive, and
either return the existing URL or bind a free port from 7891..7910.
Multiple Gru installations on the same host therefore share **one**
viz process at **one** URL. `./viz stop` refuses to kill a PID owned
by another user.

## 5. Repo layout

```
src/
  shared/types.ts         # GruInfo, NetworkSnapshot, WsMessage
  server/
    index.ts              # Express + WS + poller scheduler
    grus.ts               # reads ~/.minionsos/grus.json + each Gru's projects.json
    projects.ts           # legacy shim aggregating across Grus
    mosFs.ts              # read-only views; every fn takes (gruId, port, …)
    poller.ts             # EACN3 fetchers (take endpoint as param)
    state.ts              # per-(gruId,port) snapshot cache + WS broadcast
  web/
    App.tsx               # Gru picker → Project picker → tabs gate
    components/
      GruPicker.tsx       # Gru-level picker (new)
      ProjectPicker.tsx   # Project-level picker (inside selected Gru)
      TopBar.tsx          # Gru ▾ / Project ▾ side-by-side dropdowns + tabs
      …                   # remaining tabs accept (port, gruId) props
    hooks/useStore.ts     # WS client + selectGru / selectProject / select
```

## 6. HTTP endpoints

All project-scoped endpoints **require** `?gru=<gruId>`; unknown Gru → 404,
unknown (Gru, port) pair → 404.

```
GET  /health
GET  /api/snapshot?gru=<id>&port=<port>                # full state for pair
GET  /api/mos/grus                                     # GruInfo[] with embedded projects
GET  /api/mos/projects                                 # legacy: flat across Grus
GET  /api/mos/roles?gru=<id>                           # role SYSTEM.md paths for a Gru
GET  /api/mos/project/:port/overview?gru=<id>
GET  /api/mos/project/:port/scratchpads?gru=<id>
GET  /api/mos/project/:port/scratchpad/:role?gru=<id>
GET  /api/mos/project/:port/artifacts?gru=<id>
GET  /api/mos/project/:port/artifact?gru=<id>&path=<rel>
GET  /api/mos/project/:port/log?gru=<id>&which=…&tail=500
```

## 7. WebSocket protocol

Client → server:

```jsonc
{ "type": "select", "gruId": "abc123def456", "port": 37596 }
{ "type": "select", "gruId": "abc123def456", "port": null   }  // to project picker
{ "type": "select", "gruId": null,            "port": null }  // to Gru picker
// legacy alias (assumes client's last gruId, else first online Gru):
{ "type": "select_project", "port": 37596 }
```

Server → client:

| type                 | scope        | payload                             |
|----------------------|--------------|-------------------------------------|
| `snapshot`           | per-client   | `NetworkSnapshot`                   |
| `grus:update`        | global       | `GruInfo[]` (every 5 s)             |
| `selected`           | per-client   | `{ gruId, port }`                   |
| `tasks:update`       | pair-scoped  | `Task[]`                            |
| `agents:update`      | pair-scoped  | `AgentInfo[]`                       |
| `cluster:update`     | pair-scoped  | `ClusterStatus \| null`             |
| `logs:update`        | pair-scoped  | `LogEntry[]`                        |
| `connection:status`  | pair-scoped  | `{ connected }`                     |

"pair-scoped" = delivered only to sockets whose selection equals
`(gruId, port)`.

## 8. Polling loop

The EACN3 polling loop iterates only over `(gruId, port)` pairs for which
at least one connected client is watching — idle Grus and idle projects
cost zero backend traffic. Registry is read every 5 s and rebroadcast as
`grus:update`; a successful read auto-heartbeats that Gru's `last_seen`.

## 9. Hard rule: do NOT call `/api/events/{agent_id}`

`/api/events/{agent_id}` on any EACN3 backend **consumes** events. The
observatory only calls GET, idempotent endpoints (`/health`, `/api/tasks`,
`/api/cluster/status`, `/api/admin/logs`, `/api/discovery/agents`,
`/api/reputation/…`, `/api/economy/balance`).

## 10. Writes

- Viz never writes to `EACN3/` or any Gru's `minions/`.
- Viz writes `~/.minionsos/{grus.json, viz.pid, viz.port, viz.url}` (atomic
  rename) and its build output under `eacn-viz/dist/`.
- Per-client state that survives a refresh is
  `localStorage["mos.viz.selection"] = {gruId, port}`.

## 11. Minimal run

```bash
# From any MinionsOS_V2 checkout:
./viz ensure         # register this Gru + start viz (no-op if running)
./viz status         # PID / port / URL
./viz open           # open in browser
```
