# minions-tui

A keyboard-driven terminal control plane for MinionsOS — the read **and write**
sibling of `minions-viz/` (the strictly read-only Observatory GUI).

Open it with:

```bash
./mos tui          # builds on first run, then execs the cached release binary
./mos tui --rebuild  # force a fresh cargo build --release
./mos tui --probe    # non-interactive read-path check (scriptable health summary)
```

## What it does

Browse every project's role-agent sessions one by one and **drive** them, all
from one terminal UI. Phase 1 ships the session cockpit; later phases fold in
the rest of MinionsOS (experiments, memory layers, role evolution, EACN,
deliverable lifecycle, health) panel by panel.

## Two planes

- **Read** — directly reads `minions/state/projects.json`, per-project
  `meta.json` / logs / `events/*.jsonl`, and polls EACN *safe* endpoints. Never
  calls `/api/events/{agent_id}` (it drains role queues — same invariant as viz).
- **Write** — every mutation shells out to `mos` subcommands, reusing the CLI's
  authorization and its destructive-action guardrails (e.g. the
  `--i-know-this-kills-autonomy` confirmation on `drive`).

## Drive pipeline

Role processes already run in tmux sessions named `mos-{port}-{role}`. The TUI
attaches to / observes / feeds them in three tiers, each the least-disturbing
tmux primitive for a live autonomous role:

1. **Look** — `tmux capture-pane -ept` polled ~200ms, parsed by vt100, rendered
   with styled spans. No attach client, so the role's geometry is never reflowed.
2. **Steer** — `tmux send-keys -l <text>` + Enter (via `mos role kick`). Type in
   the cockpit, the role's pane reacts. No attach needed.
3. **Takeover** — suspend the TUI and `mos role attach` (read-mostly) or
   `mos role drive` (full takeover, kills autonomy). Re-enters and rescans on exit.

## Keys

`↑↓`/`jk` move · `→`/`Enter` descend · `←`/`Esc` back · `i` steer · `a` attach ·
`d` drive · `r` refresh · `?` help · `q` quit.

## Layout

```
src/
├── main.rs     event loop, mode-based key dispatch, suspend-then-exec, --probe
├── app.rs      App state + Focus/Mode enums + channel draining
├── ui.rs       ratatui rendering + responsive Wide/Narrow layout + overlays
├── scanner.rs  read projects.json + tmux liveness -> Snapshot
├── tmux.rs     capture-pane / send-keys / attach driver (argv arrays, no shell)
├── vt.rs       vt100 ANSI -> styled ratatui Lines (the cockpit render core)
├── actions.rs  write actions -> mos subcommands
├── config.rs   resolve MinionsOS root + Gru registry (~/.minionsos/grus.json)
└── model.rs    serde shapes mirroring ProjectsData / ProjectEntry / RoleEntry
```

See `DESIGN.md` for the full capability map and roadmap.
