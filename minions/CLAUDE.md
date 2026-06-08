# CLAUDE.md — minions/ Developer View

This file is shown when you `cd minions/ && claude` to hack MinionsOS itself. It covers the Python package architecture and how to extend it. **Claude Code is the agent host** for every Role process — `agent_host.py` builds the long-lived `claude` invocation.

## Package architecture

```
minions/
├── __init__.py              # package root; exports version
├── bin/gru                  # shell launcher (Claude Code host)
├── cli.py                   # `mos` CLI entrypoint (Typer); dispatches subcommands
├── gru/
│   ├── __init__.py
│   └── loop.py              # Gru heartbeat/health loop plus experiment queue reconciliation
├── lifecycle/
│   ├── agent_registry.py    # project-local AgentCard registration and domains
│   ├── agent_host.py        # long-lived `claude` invocation builder
│   ├── eacn_identity.py     # stable per-project role agent ids and plugin state
│   ├── project.py           # project_create/close/dormant/revive/repair helpers
│   ├── role.py              # register_role / register_expert / dismiss / list_roles
│   ├── skills.py            # role skill discovery and one-line summaries
│   ├── project_bridge.py    # mos_project_bridge implementation
│   ├── eacn_client.py       # thin EACN3 HTTP client (registration / bootstrap / health)
│   └── health.py            # backend / role health probes
├── tools/
│   ├── mcp_server.py        # FastMCP stdio server wrapping lifecycle functions
│   ├── experiment_ssh.py    # exp_run plus exp_queue_* / exp_gpu_pool_* MCP tools
│   ├── experiment_scheduler.py # SQLite-backed Expert GPU queue
│   ├── project_bridge.py    # mos_project_bridge MCP-facing wrapper
│   └── whitelist.py         # resolve_allowed_tools
├── roles/                   # shared contract, role prompts, skills
│   ├── SYSTEM.md            # common Role contract injected before role-specific prompts
│   ├── {role}/SYSTEM.md     # gru/ethics/expert (v23 three-role roster)
│   └── {role}/skills/       # procedural skills discovered at wake-up
├── review/                  # paper-review prompt assets used by mos_review_run
│   ├── SYSTEM.md            # Area-Chair system prompt for the spawned claude --print
│   ├── skills/              # run-review-round, simulate-reviewer-instance, aspect-review, ...
│   ├── personas/            # short reviewer stance files
│   └── templates/           # aspect-note / reviewer-instance / fresh / revision_delta / consolidated / summary / submission-checklist
├── domains/                 # Expert domain-pack assets (not Python)
├── hooks/                   # post_compact_draft.py, pre_compact_science.py
├── config/
│   ├── gru.yaml.example
│   └── experiment_targets.yaml.example
└── state/                   # runtime state (gitignored)
    ├── projects.json
    └── logs/gru.log
```

## Role lifecycle

Roles are long-lived agent-host processes. EACN-registered roles (Ethics,
Expert) drive their event loop by calling `mos_await_events` on their EACN3
queue. Roles are started by
`minions/lifecycle/role_launcher.py` inside their own tmux session.

- `minions/lifecycle/role.py` exposes `register_role` / `register_expert` (registers a project-local EACN AgentCard for EACN roles, prepares the role workspace, and records a named host session; no subprocess launch) and `mos_dismiss_role` / `mos_list_roles`.
- `minions/lifecycle/project.py` also exposes `mos_project_checkpoint_workspace(...)` for durable local commits and optional GitHub push when `github_push_target` is configured.
- `minions/lifecycle/agent_host.py` is the only place that should know Claude Code CLI invocation details.
- `minions/gru/loop.py` runs the Gru heartbeat monitor and experiment queue reconciliation.
- Role `SYSTEM.md` files must not describe a polling loop. Shared role/subagent/draft/EACN behavior lives in `minions/roles/SYSTEM.md`; review output formats live under `minions/review/templates/`.

Key design points:

- All registry state writes go through `minions/state/store.py` `StateStore`: file-locked atomic writes (write to `.tmp` then rename).
- All paths are resolved from `MINIONS_ROOT = Path(__file__).parent.parent` — no hardcoded absolute paths.
- MCP tools accept and return Pydantic models where possible.
- Logging uses the standard `logging` module; level controlled by `MINIONS_LOG_LEVEL` env var (default: info).
- No `os.system`; use `subprocess.run` with list args.
- Python 3.11+; `from __future__ import annotations` in every module.

## How to add a new Role template

1. Create `minions/roles/{role}/SYSTEM.md`. Keep it lean: identity and scope, can do, cannot do, workspace constraints, collaboration rules, and role-specific deviations from the common contract. Do **not** redeclare the polling loop, generic subagent handoff rules, or draft rules — those live in `minions/roles/SYSTEM.md`.
2. Update `minions/config/__init__.py` `_WHITELIST` to add `main` and `subagent` entries for the new role.
3. Add a row to the tool/write boundary table in root `CLAUDE.md`.
4. If the new role registers via `mos_spawn_role`, add its name to `FIXED_ROLES` in `minions/lifecycle/role.py`.
5. Write a unit test under `tests/unit/` covering registration and whitelist resolution.
6. If the new role has a multi-pass workflow with required isolation between passes, document the pass boundaries and isolation rules explicitly; do not let later passes contaminate earlier ones by accident. Use `minions/review/SYSTEM.md` as the worked example for pass isolation and review artifacts.

## How to add a Role skill

Applies to any Role (Gru, Ethics, Expert).

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
4. Register the tool in the MCP server setup (`.mcp.json` for Claude Code, or the server entrypoint).
5. Update the tool/write boundary table in root `CLAUDE.md` to specify which agents may use it.
6. Write a unit test in `tests/unit/`.

## Skill and Agent population evolution

The four "How to add ..." sections above describe the *human-driven* path for introducing a new Role, skill, domain pack, or MCP tool. The system also has an **autonomous evolution path** that runs continuously inside an active project. It evolves on two axes simultaneously, fed by one trajectory source.

### Two axes, one trajectory source

| Axis | What evolves | Operations |
|---|---|---|
| **Knowledge** | Individual Skills inside the library | `add` / `revise` / `merge` / `split` / `drop` |
| **Agent** | Expert population (count, scope, identity) | `spawn` / `dismiss` / `merge` / `split` |

Both axes consume the same raw trajectory (Draft + EACN events + shared artefacts). They are conceptually distinct but architecturally co-equal.

The **Agent-axis** `split` is a permanent topology change — one Expert is dismissed and two are spawned with disjoint domain partitions. It is **not** the same as a sub-agent: a sub-agent is a within-task executor that disappears when the task ends. Split changes the project's permanent Expert roster and creates two AgentCards on EACN where there was one.

The **Agent-axis** `merge` collapses two Experts whose domains and bid patterns have converged. The **Knowledge-axis** `merge` collapses two Skills whose triggers have converged.

### Four-stage pipeline (decorrelated)

```
   raw trajectory  (Draft, EACN events, shared artefacts)
        │
        ▼
   skill-curator              ← Gru-driven (periodic), kept off Ethics by design
   (~/.claude/skills/skill-curator/)
        │  branches/main/notes/skill-proposals.md
        ▼
   skill-audit                ← Ethics operates this
   (minions/roles/ethics/skills/skill-audit.md)
        │  accepted subset  →  notify Gru
        ▼
   skill-forge (Knowledge) │ mos_spawn_expert / mos_dismiss_role / Agent-axis tools
   (~/.claude/skills/skill-forge/)
        │
        ▼
   Library / Expert roster
        │  use telemetry, failure events
        ▼
   feeds back into trajectory for the next curation pass
```

The four stages are **structurally decorrelated**: the curator (proposer) is run as a Gru-driven periodic pass that never makes business decisions and is deliberately not Ethics; Ethics (auditor) reads the proposal artefact, not the proposer's reasoning; skill-forge (validator) runs blind A/B testing; the operating Roles (consumer) only see admitted artefacts. This satisfies the decorrelation principle that makes the multi-agent error rate fall below the single-agent rate.

### Implementation status

| Component | Status |
|---|---|
| Global `skill-curator` skill | Implemented (`~/.claude/skills/skill-curator/SKILL.md`); invoked as a Gru-driven periodic pass |
| Ethics `skill-audit` skill | Implemented (`minions/roles/ethics/skills/skill-audit.md`) |
| `skill-forge` orchestrator | Implemented (`~/.claude/skills/skill-forge/`) |
| Knowledge-axis ops (add/revise/merge/split/drop) | Routed through skill-forge — operational |
| Agent-axis `spawn` / `dismiss` | MCP tools `mos_spawn_expert`, `mos_dismiss_role` |
| Agent-axis `merge` / `split` | MCP tools `mos_role_merge`, `mos_role_split` (plus `mos_role_evolve_evaluate` / `mos_role_evolve_dismiss`); Signboard sign-off still required for `split` |

The Knowledge-axis and Agent-axis evolution surfaces are both fully wired: every op has a backing MCP tool. The remaining discipline lives at the audit gate — `mos_role_split` is consequential enough that Ethics' `skill-audit` skill marks accepted `op: split` proposals as `requires_signboard: true`, and Gru must reach Signboard consensus before invoking the tool.

### Gru intake contract

Ethics' audit pass ends with one EACN message to Gru. Gru is then the routing authority — it (and only it) maps accepted proposals to enactment surfaces. The runtime authority for this contract lives in `minions/roles/gru/SYSTEM.md` §G15 (Gru reads SYSTEM.md at wake; Gru does not read this dev-view file). The message and routing table are reproduced here for developer convenience — keep both in sync, but treat §G15 as the canonical home.

**EACN message Ethics sends to Gru (schema):**

```json
{
  "type": "skill-audit-complete",
  "audit_path": "branches/main/ethics/skill-audit-YYYY-MM-DD.md",
  "proposals_path": "branches/main/notes/skill-proposals.md",
  "accepted": [
    {"proposal_id": "proposal-20260523-0001", "op": "add", "axis": "knowledge"},
    {"proposal_id": "proposal-20260523-0002", "op": "spawn", "axis": "agent"}
  ],
  "rejected_count": <int>,
  "held_count": <int>
}
```

**Gru routing table (proposal → enactment surface):**

| `axis` | `op` | Gru action | Notes |
|---|---|---|---|
| knowledge | `add` | `Skill(skill-forge)` with `mode=create`, draft_skill_md from proposal | Runs full Stage 1–6 |
| knowledge | `revise` | `Skill(skill-forge)` with `mode=improve`, target_skill_path from proposal | Runs Stage 2 + 3 minimum |
| knowledge | `merge` | `Skill(skill-forge)` with `mode=create` against the union, plus `drop` of source_a + source_b after admission | Two-phase: admit new, then drop sources only if new passes |
| knowledge | `split` | Two `Skill(skill-forge)` create runs (one per decision class), then `drop` of source after both admit | Three-phase; if either child fails Stage 3, no drop |
| knowledge | `drop` | Direct removal from library + commit on the project main branch | No skill-forge run needed; audit already verified `unique_coverage_check` |
| agent | `spawn` | `mos_spawn_role` or `mos_spawn_expert` with proposed_domain_pack + proposed_tool_whitelist from proposal | Native MCP tool |
| agent | `dismiss` | `mos_dismiss_role` against target_expert_id | Native MCP tool (also `mos_role_evolve_dismiss` for evidence-gated dismiss with Draft + EACN inputs) |
| agent | `merge` | `mos_role_merge` against `expert_a` + `expert_b` with `union_domain_pack` | Native MCP tool; bid-overlap-gated. `mos_role_evolve_evaluate` produces the supporting evidence summary first |
| agent | `split` | `mos_role_split` against `target_expert_id` with `domain_partition` | Native MCP tool; **the proposal's `requires_signboard: true` is enforced here — Gru must reach Signboard consensus before calling the tool** |

**Post-enactment.** After Gru completes enactment for a proposal, it appends an `### enactment (by gru on YYYY-MM-DD)` sub-block to that proposal in `branches/main/notes/skill-proposals.md`, closing the lifecycle (see [[skill-curator]] §5 lifecycle annotations). The proposal's `status` flips to `enacted`. If enactment fails (e.g. skill-forge Stage 3 rejects), `status` becomes `superseded` and Gru explains in the enactment block.

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

# Type gate for the Python runtime core
uv run ty check minions

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
