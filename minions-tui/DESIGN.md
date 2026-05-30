# MinionsOS TUI — Design

> **Status:** Phase 1 + Phase 2 core + Gru-in-TUI blueprint **shipped &
> verified** (2026-05-30). North star: wrap the *entire* MinionsOS into one
> keyboard-driven terminal cockpit. `minions-viz/` (the read-only Observatory
> GUI) is **untouched**; this TUI is its read **and write** sibling.

## Shipped (verified)

- **Launch:** `./mos tui` (builds the Rust binary on first run, then execs the
  cached release binary), `./mos tui --rebuild`, `./mos tui --probe` (scriptable
  read-path health check). Standalone binary: `minions-tui/target/release/mtui`.
- **Gru picker → project overview → role list → session cockpit**, all
  keyboard-driven, three-column responsive layout. Multi-Gru switching re-roots
  the scanner live (verified against 8 registered installs).
- **Drive pipeline (refined):** capture-pane live view (vt100-rendered, zero
  resize disturbance) + `send-keys` steer (via `mos role kick`) + attach/drive
  full takeover (suspend-then-exec, via `mos role attach` / `drive
  --i-know-this-kills-autonomy`).
- **Cockpit views:** `l` cycles live / logs (`role-{name}.log` tail) / health
  (`health_events.jsonl`).
- **One-click haiku issue-filer (`I`):** spawns `claude --print --model haiku`
  to draft an issue from the role's live context → **human-check** review
  overlay → files via `mos issues file` (a new CLI write command added for this).
- **Gru-in-TUI blueprint (`g` / `mtui --gru`):** Gru runs as a `mos-gru` tmux
  session (ensured on demand), surfaced as the starred top "★ Gru (control
  plane)" target so the same cockpit pipeline drives Gru itself.



A new top-level `minions-tui/` Rust crate, single binary, launched by
`./mos tui` (thin launcher) or the standalone `mtui` symlink. It lets an
operator browse every project's role-agent sessions one-by-one and **drive**
them — and, panel by panel, exposes the rest of MinionsOS (experiments,
memory layers, role evolution, EACN, deliverable lifecycle, health) from the
terminal.

## Two planes

| Plane | How | Boundary |
|---|---|---|
| **Read** | directly read state files + poll EACN *safe* endpoints | mirror minions-viz's read-only data access |
| **Write** | shell out to `mos` subcommands / `mos_*` MCP tools | reuse existing authz + destructive-action confirmations; never bypass to mutate files directly |

This split is deliberate: reads are cheap and local, writes carry the same
authorization semantics and guardrails the CLI already enforces (e.g. the
`mos role drive --i-know-this-kills-autonomy` takeover gate).

## Drive pipeline (the soul of the TUI)

Role processes are **already running** in tmux sessions named
`mos-{port}-{role}` (started by `role_launcher.py`). We do not spawn them —
we attach to / observe / feed them. The pipeline has three tiers, each using
the tmux primitive that least disturbs a live autonomous role:

1. **Multi-pane live view (look)** — `tmux capture-pane -ept <session>` polled
   ~200 ms, parsed by a vt100 engine, rendered with `tui-term`. **Zero attach
   client, zero resize disturbance.** This is what lets the operator watch N
   roles' real screens at once.
2. **Drive input (steer)** — `tmux send-keys -t <session>` (large input via
   `load-buffer` + `paste-buffer`). Same mechanism MinionsOS itself uses
   (`compact.py`, initial-prompt injection). You type in the TUI input box →
   send-keys → capture-pane shows the reaction. Interactive, **no attach
   needed, still zero resize disturbance.**
3. **Full-fidelity takeover (optional, heavy)** — real `tmux attach` into a pty,
   or suspend-then-attach full screen. Equivalent to the existing
   `mos role drive --i-know-this-kills-autonomy` and carries the same
   "this kills autonomy" guardrail.

### Why not a portable-pty attach client per pane

A tmux session's size is the **smallest** attached client. If each visible
pane ran its own `tmux attach`, every role's claude TUI would be force-reflowed
to that small pane size — actively disturbing a role that is running
autonomously. capture-pane reads a snapshot without attaching, so the role's
own geometry is never touched. Same vt100/tui-term render layer either way; the
only change is the data source (capture snapshots vs. an owned pty), which
sidesteps the resize hell.

## Capability map (panels = MinionsOS subsystems)

| # | Panel | Reads | Drives (writes via mos/MCP) |
|---|---|---|---|
| 0 | Gru picker | `~/.minionsos/grus.json` | switch Gru / start-stop viz |
| 1 | Project overview | `projects.json` + `mos status --json`, grouped active/dormant/closed | create / close / dormant / revive / repair / set-phase / checkpoint |
| 2 | Role list | per-project `active_roles[]` + `session_alive` + heartbeat/crash counter | spawn / dismiss / attach / inspect / **drive** / kill / compact / reset |
| 3 | **Session cockpit** (core, MVP) | role log tail + capture-pane live screen + REPL state | browse one-by-one → capture-pane live multi-pane → send-keys drive → full takeover |
| 4 | Role evolution | `governance/role_evolution.jsonl` recommendation stream | evaluate / split / merge / evolve-dismiss (Gru-only) |
| 5 | Experiment queue | `exp_queue_status` + GPU pool + `exp/` bundles | submit / run / tail / kill / GPU-pool config |
| 6 | Memory 4 layers | L0 Reel / L1 Draft graph / L2 Book (hot.md + contradictions) / L3 Shelf | read + drill-down (follow `reel_ref` back to the execution frame) |
| 7 | EACN stream | **safe** endpoints: tasks / agents / cluster + `events/*.jsonl` audit | read-mostly; message send optional |
| 8 | Deliverable lifecycle | `submissions/` + `reviews/` | submit / evaluate / adjudicate / review_run / benchmark |
| 9 | Health / logs | `health_events.jsonl` + backend/role/gru logs (follow) | doctor / restart / crash triage |

Cross-cutting: a `:`-invoked global command palette (fuzzy command search),
fully keyboard-driven, responsive Wide/Stacked/Narrow layout.

## Safe vs. unsafe data access

EACN **safe read endpoints** (`http://127.0.0.1:{port}`): `/health`,
`/api/tasks?limit=N`, `/api/tasks/open`, `/api/cluster/status`,
`/api/admin/logs?limit=N`, `/api/discovery/agents`, `/api/reputation/{id}`,
`/api/economy/balance`.

**RED LINE:** never call `GET /api/events/{agent_id}` — it **drains** the
role's event queue (destructive). Read persisted `events/*.jsonl` from disk
instead. This is the same invariant minions-viz enforces.

## Tech skeleton

- **Crates:** `ratatui 0.29` + `crossterm 0.28` (TUI); `vt100` / `tui-term`
  (screen render); `portable-pty` (full-takeover tier only); `notify 6`
  (FS watcher); `serde_json`, `anyhow`.
- **Concurrency:** background threads + `mpsc` snapshot delivery so the render
  loop never blocks (ManageCode pattern). EACN polling may use a separate
  `tokio` runtime, but the core event loop stays synchronous.
- **Modules:**
  - `main.rs` — terminal setup, event loop, mode-based key dispatch, exec.
  - `app.rs` — `App` state + `Mode` enum + all state mutations.
  - `ui.rs` — ratatui rendering + responsive Wide/Stacked/Narrow layout.
  - `scanner.rs` — read state files (`projects.json`, `meta.json`, events, draft).
  - `poller.rs` — EACN *safe* endpoint fetchers.
  - `tmux.rs` — `capture-pane` / `send-keys` / `attach` driver (argv arrays, no manual shell escaping).
  - `pty.rs` — full-fidelity takeover.
  - `actions.rs` — write actions dispatched to `mos` / `mos_*`.
  - `watcher.rs` — notify-based FS watcher thread.
  - `vt.rs` — vt100 screen parsing + render.

### Borrowed from ManageCode (`github.com/Minions-Land/ManageCode`)

suspend-then-exec attach loop (`ExitRequest::Exec`); tmux name-prefix
namespacing (`mc-` → maps onto our existing `mos-` convention); mode-enum
keybinding dispatch; `Row` enum (`Header | Item`) for grouped lists; multi-tier
refresh (debounced notify watcher + ~1.5 s cheap status sweep + ~30 s fallback
full scan); background-thread + mpsc snapshot delivery; responsive layout.

**Explicitly avoid:** hardcoded model pricing; parsing Claude's private JSONL
schema (brittle); `sh_quote` manual shell escaping (pass argv arrays to tmux).

## Roadmap

- **Phase 1 — MVP (the original ask):** Gru picker → project overview →
  role list (`session_alive` + heartbeat) → **Session cockpit**: browse
  one-by-one, capture-pane live multi-pane, send-keys drive, upgrade to full
  takeover. One command in, keyboard flow throughout.
- **Phase 2 → N — wrap the rest in:** experiment queue (queue + GPU), memory
  four-layer drill-down (Reel/Draft/Book/Shelf), role evolution
  (split/merge/dismiss), EACN stream, deliverable lifecycle
  (submit/evaluate/adjudicate/review/benchmark), health/logs (doctor/restart).
  Each panel = one subsystem; read direct, write via `mos`.

## Verified facts (repo, 2026-05-30)

- Session naming `mos-{port}-{role}`: `role_launcher.py:70-72`. `session_alive`
  = `tmux has-session` (:75-80), `kill_session` = `tmux kill-session`
  (:83-101), `attach_command` → `['tmux','attach','-t',name]` (:104-110),
  `list_project_sessions` matches `mos-{port}-*` (:113+).
- Host has `tmux 3.6a` (supports `capture-pane -ept`).
- `mos` is a Typer app (`minions/cli.py`) — clean mount point for a `tui`
  subcommand. Existing role CLI: `mos role attach|inspect|drive`.
- State: `minions/state/projects.json` (ProjectsData). Per-project `meta.json`,
  `logs/{backend,role-NAME,gru}.log`, `events/*.jsonl`,
  `branches/shared/draft/draft.json`, `branches/shared/book/hot.md`.
  Global registry `~/.minionsos/grus.json`. Health
  `logs/health_events.jsonl`; crash counter `minions/state/crash_counter.json`.
