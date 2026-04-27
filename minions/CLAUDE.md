# CLAUDE.md — minions/ Developer View

This file is shown when you `cd minions/ && claude` to hack MinionsOS itself. It covers the Python package architecture and how to extend it. Runtime role execution is agent-host neutral: Claude Code remains the default, and Codex is supported through the same lifecycle abstractions.

## Package architecture

```
minions/
├── __init__.py              # package root; exports version
├── bin/gru                  # shell launcher (Claude Code or Codex host)
├── cli.py                   # `mos` CLI entrypoint (argparse); dispatches subcommands
├── gru/
│   ├── __init__.py
│   └── loop.py              # Gru heartbeat/health loop plus WakeupScheduler startup
├── lifecycle/
│   ├── agent_registry.py    # project-local AgentCard registration and domains
│   ├── agent_host.py        # Claude Code / Codex invocation builders
│   ├── eacn_identity.py     # stable per-project role agent ids and plugin state
│   ├── project.py           # project_create/close/dormant/revive/repair helpers
│   ├── project_eacn.py      # Gru-facing project-local EACN adapters
│   ├── role.py              # register_role / register_expert / invoke_role_ephemeral / dismiss
│   ├── skills.py            # role skill discovery and one-line summaries
│   ├── wakeup.py            # Python-level event-driven Role dispatcher (see below)
│   ├── relay.py             # gru_relay implementation
│   ├── eacn_client.py       # thin EACN3 HTTP client (used by wakeup)
│   ├── gru_inbox.py         # Gru EACN pending journal for drain-only queues
│   ├── role_inbox.py        # role event queue helpers
│   └── health.py            # backend / role health probes
├── tools/
│   ├── mcp_server.py        # FastMCP stdio server wrapping lifecycle functions
│   ├── experiment_ssh.py    # exp_run / exp_put / exp_get / exp_tail MCP tools
│   ├── relay.py             # gru_relay MCP-facing wrapper
│   └── whitelist.py         # resolve_allowed_tools
├── roles/                   # shared contract, role prompts, skills, reviewer assets
│   ├── SYSTEM.md            # common Role contract injected before role-specific prompts
│   ├── {role}/SYSTEM.md     # gru/noter/coder/experimenter/writer/reviewer/ethics/expert
│   ├── {role}/skills/       # procedural skills discovered at wake-up
│   └── reviewer/
│       ├── personas/        # short stance files
│       └── templates/       # aspect-note / reviewer-instance / fresh / revision_delta / consolidated / summary
├── domains/                 # Expert domain-pack assets (not Python)
├── config/
│   ├── gru.yaml.example
│   └── experiment_targets.yaml.example
└── state/                   # runtime state (gitignored)
    ├── projects.json
    └── logs/gru.log
```

## Event-driven Role lifecycle

Roles are **ephemeral**: no long-running agent-host process per Role, and no in-agent polling loop.

- `minions/lifecycle/role.py` exposes `register_role` / `register_expert` (registers a project-local EACN AgentCard and records the role; no subprocess) and `invoke_role_ephemeral(role, port, events)` which launches a short-lived Claude Code or Codex subprocess seeded with the shared `roles/SYSTEM.md`, the Role's `SYSTEM.md`, discovered skills, scratchpad context, identity/boundary text, and an event batch, then exits.
- `minions/lifecycle/agent_host.py` is the only place that should know CLI-specific role invocation details. Preserve the Claude command exactly unless intentionally changing the Claude path; Codex uses `codex exec -` with the role prompt on stdin.
- `minions/lifecycle/wakeup.py` (`WakeupScheduler`) runs on the Python side, polls EACN3 on each registered Role's cadence, deduplicates events by id, and fires `invoke_role_ephemeral` when events arrive.
- `minions/gru/loop.py` runs `WakeupScheduler` in parallel with Gru's heartbeat (sibling thread when `run()` is used; sibling task when `run_async()` is used). The MCP `gru_start_monitor` tool starts both.
- `schedule_poll` MCP tool is deprecated (no-op that logs a deprecation warning); still present for backward compatibility during migration.
- Role `SYSTEM.md` files must not describe a polling loop. Shared role/subagent/scratchpad/EACN behavior lives in `minions/roles/SYSTEM.md`; review output formats live under `minions/roles/reviewer/templates/`.

Key design points:

- All registry state writes go through `minions/state/store.py` `StateStore`: file-locked atomic writes (write to `.tmp` then rename).
- All paths are resolved from `MINIONS_ROOT = Path(__file__).parent.parent` — no hardcoded absolute paths.
- MCP tools accept and return Pydantic models where possible.
- Logging uses the standard `logging` module; level controlled by `MINIONS_LOG_LEVEL` env var (default: info).
- No `os.system`; use `subprocess.run` with list args.
- Python 3.11+; `from __future__ import annotations` in every module.

## How to add a new Role template

1. Create `minions/roles/{role}/SYSTEM.md`. Keep it lean: identity and scope, can do, cannot do, workspace constraints, collaboration rules, and role-specific deviations from the common contract. Do **not** redeclare the polling loop, generic subagent handoff rules, or scratchpad rules — those live in `minions/roles/SYSTEM.md`.
2. Update `minions/config/__init__.py` `_WHITELIST` to add `main` and `subagent` entries for the new role.
3. Add a row to the tool/write boundary table in root `CLAUDE.md`.
4. If the new role registers via `spawn_role`, add its name to `FIXED_ROLES` in `minions/lifecycle/role.py`.
5. Write a unit test under `tests/unit/` covering registration and whitelist resolution.
6. If the new role has a multi-pass workflow (like Reviewer's 3-Pass progressive disclosure), document the pass boundaries and isolation rules explicitly; do not let later passes contaminate earlier ones by accident.

## How to add a Role skill

Applies to any Role (Expert, Experimenter, Writer, Noter, Coder, Reviewer, Ethics, Gru).

1. Create `minions/roles/{role}/skills/{slug}.md` where `{slug}` is lowercase hyphen-separated (e.g. `occams-razor.md`, `triage-request.md`, `citation-audit.md`).
2. Follow the standard structure: H1 title on the first line, a one-line summary on the next non-blank line (used by the discovery mechanism), then `Core move` / `Core question`, `Procedure`, `When to invoke`, `Pitfalls`, `Output habit` (marking derived claims per root `Evidence-first EACN communication`).
3. Keep skills short (≤ 60 lines). They are reasoning / procedure disciplines, not exhaustive treatises.
4. No code change needed — every Role discovers its skills by listing `minions/roles/{role}/skills/` at wake-up via `minions.lifecycle.skills.list_skills`, which seeds a `[Skills]` block into the init message.
5. Do not duplicate domain knowledge into a skill; domain specifics belong in `minions/domains/`. Skills are cross-domain reasoning or procedure tools.
6. Add or extend a unit test under `tests/unit/test_skills_discovery.py` if the new skill exercises an edge case (e.g. unusual title format).

## How to add a domain pack

1. Create `minions/domains/{slug}.md` where `{slug}` is lowercase, hyphen-separated (e.g., `rl-theory.md`).
2. Follow the structure: Core scope, Canonical references, Common methods, Typical pitfalls, Useful toolchains, Evaluation norms.
3. Domain packs are reusable prompt assets; keep them independent from role skills. If a change needs automatic prompt injection or CLI discovery, wire it through `minions/lifecycle/role.py` / `minions/paths.py` and add tests.
4. Test any new discovery or prompt-injection behavior with focused unit coverage.

## How to add a new MCP tool

1. Add the tool function to the appropriate module in `minions/tools/` (or create a new module).
2. Decorate with the MCP tool decorator (FastMCP or equivalent).
3. Accept/return Pydantic models.
4. Register the tool in the MCP server setup (`.mcp.json`, `.codex/config.toml`, or the server entrypoint).
5. Update the tool/write boundary table in root `CLAUDE.md` to specify which agents may use it.
6. Write a unit test in `tests/unit/`.

## Running tests

```bash
# All unit tests
uv run pytest tests/unit/

# Single file
uv run pytest tests/unit/test_port_allocator.py

# Single test case
uv run pytest tests/unit/test_port_allocator.py::test_no_reuse_retired_ports

# Smoke tests (requires MINIONS_FAKE_CLAUDE=1 to stub Claude CLI)
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
