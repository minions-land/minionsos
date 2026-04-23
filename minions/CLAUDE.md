# CLAUDE.md — minions/ Developer View

This file is shown when you `cd minions/ && claude` to hack MinionsOS itself. It covers the Python package architecture and how to extend it.

## Package architecture

```
minions/
├── __init__.py              # package root; exports version
├── bin/gru                  # shell launcher (uv run claude ...)
├── cli.py                   # `mos` CLI entrypoint (argparse); dispatches subcommands
├── gru/
│   ├── __init__.py
│   ├── main.py              # Gru main loop: startup, project scan, heartbeat
│   └── scheduler.py         # multi-IP scheduler: port allocation, health probes
├── lifecycle/
│   ├── project.py           # project_create/close/dormant/revive
│   ├── role.py              # register_role / register_expert / invoke_role_ephemeral / dismiss
│   ├── wakeup.py            # Python-level event-driven Role dispatcher (see below)
│   ├── relay.py             # gru_relay implementation
│   ├── eacn_client.py       # thin EACN3 HTTP client (used by wakeup)
│   └── health.py            # backend / role health probes
├── tools/
│   ├── mcp_server.py        # FastMCP stdio server wrapping lifecycle functions
│   ├── experiment_ssh.py    # exp_run / exp_put / exp_get / exp_tail MCP tools
│   ├── relay.py             # gru_relay MCP-facing wrapper
│   └── whitelist.py         # resolve_allowed_tools
├── roles/                   # SYSTEM.md templates (not Python)
│   ├── ethics/
│   │   └── SYSTEM.md
│   ├── expert/
│   │   ├── SYSTEM.md
│   │   └── skills/         # methodology skills (first-principles, dialectics, …)
│   └── reviewer/
│       ├── SYSTEM.md
│       ├── personas/        # ≤10-line persona files (identity + focus only)
│       └── templates/       # output-format templates (fresh / revision_delta / consolidated / summary)
├── domains/                 # Expert domain packs (not Python)
├── config/
│   ├── gru.yaml.example
│   └── experiment_targets.yaml.example
└── state/                   # runtime state (gitignored)
    ├── projects.json
    └── logs/gru.log
```

## Event-driven Role lifecycle

Roles are **ephemeral**: no long-running Claude process per Role, and no in-Claude polling loop.

- `minions/lifecycle/role.py` exposes `register_role` / `register_expert` (registry-only; no subprocess) and `invoke_role_ephemeral(role, port, events)` which launches a short-lived Claude subprocess seeded with the Role's `SYSTEM.md` and an event batch, then exits.
- `minions/lifecycle/wakeup.py` (`WakeupScheduler`) runs on the Python side, polls EACN3 on each registered Role's cadence, deduplicates events by id, and fires `invoke_role_ephemeral` when events arrive.
- `minions/gru/loop.py` runs `WakeupScheduler` in parallel with Gru's heartbeat (sibling thread when `run()` is used; sibling task when `run_async()` is used). The MCP `gru_start_monitor` tool starts both.
- `schedule_poll` MCP tool is deprecated (no-op that logs a deprecation warning); still present for backward compatibility during migration.
- Role `SYSTEM.md` files no longer describe a polling loop; generic per-role conventions (phase vocabulary, dormant/revive, idle framing) live in root `CLAUDE.md` under "Common role conventions". Reviewer's output-format fenced templates live under `minions/roles/reviewer/templates/`.

Key design points:

- All state writes go through `StateStore` (in `gru/main.py` or a shared util): file-locked atomic writes (write to `.tmp` then rename).
- All paths are resolved from `MINIONS_ROOT = Path(__file__).parent.parent` — no hardcoded absolute paths.
- MCP tools accept and return Pydantic models where possible.
- Logging uses the standard `logging` module; level controlled by `MINIONS_LOG_LEVEL` env var (default: info).
- No `os.system`; use `subprocess.run` with list args.
- Python 3.11+; `from __future__ import annotations` in every module.

## How to add a new Role template

1. Create `minions/roles/{role}/SYSTEM.md`. Keep it lean: Identity & scope, Can do, Cannot do, Workspace constraints, Collaboration rules, role-specific idle examples (bullet list), and any role-specific deviations from the common conventions. Do **not** redeclare phase vocabulary, dormant/revive generics, or the polling loop — those live in root `CLAUDE.md`.
2. Update `minions/config/__init__.py` `_WHITELIST` to add `main` and `subagent` entries for the new role.
3. Add a row to the tool whitelist table in root `CLAUDE.md` §4.
4. If the new role registers via `spawn_role`, add its name to `FIXED_ROLES` in `minions/lifecycle/role.py`.
5. Write a unit test under `tests/unit/` covering registration and whitelist resolution.
6. If the new role has a multi-pass workflow (like Reviewer's 3-Pass progressive disclosure), document the pass boundaries and isolation rules explicitly; do not let later passes contaminate earlier ones by accident.

## How to add an Expert methodology skill

1. Create `minions/roles/expert/skills/{slug}.md` where `{slug}` is a lowercase hyphen-separated name of the reasoning discipline (e.g. `occams-razor.md`, `counterfactual-reasoning.md`).
2. Follow the structure of existing skills: Core move / question, Procedure, When to invoke, Pitfalls, Output habit (marking derived claims per root §9).
3. Keep skills short (≤ 60 lines). They are reasoning disciplines, not exhaustive treatises.
4. No code change needed — Expert discovers skills by listing the directory at wake-up.
5. Do not duplicate domain knowledge into a skill; domain specifics belong in `minions/domains/`. Skills are cross-domain reasoning tools.

## How to add a domain pack

1. Create `minions/domains/{slug}.md` where `{slug}` is lowercase, hyphen-separated (e.g., `rl-theory.md`).
2. Follow the structure: Core scope, Canonical references, Common methods, Typical pitfalls, Useful toolchains, Evaluation norms.
3. The spawn system in `minions/tools/spawn.py` auto-discovers domain packs by listing `minions/domains/*.md`. No code change needed for discovery.
4. Test: `./mos doctor` should list the new domain pack as available.

## How to add a new MCP tool

1. Add the tool function to the appropriate module in `minions/tools/` (or create a new module).
2. Decorate with the MCP tool decorator (FastMCP or equivalent).
3. Accept/return Pydantic models.
4. Register the tool in the MCP server setup (`.mcp.json` or the server entrypoint).
5. Update the tool whitelist table in `CLAUDE.md` (root constitution) to specify which agents may use it.
6. Write a unit test in `tests/unit/`.

## Running tests

```bash
# All unit tests
uv run pytest tests/unit/

# Single file
uv run pytest tests/unit/test_port_allocator.py

# Single test case
uv run pytest tests/unit/test_port_allocator.py::test_no_reuse_retired_ports

# Smoke tests (requires MINIONS_FAKE_CLAUDE=1 to stub claude CLI)
MINIONS_FAKE_CLAUDE=1 uv run pytest tests/smoke/

# Ruff lint
uv run ruff check minions/
uv run ruff format --check minions/
```

## Coding conventions

- 100-char line limit.
- `from __future__ import annotations` at the top of every module.
- Full type hints on all public functions.
- `logging` not `print`.
- `pathlib.Path` for all file paths.
- `subprocess.run` with list args; never `os.system` or shell=True with user input.
- Atomic state writes: write to `path.with_suffix('.tmp')` then `rename`.
