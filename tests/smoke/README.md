# MinionsOS — Manual Smoke Test Scenario

This document describes the 15-step manual smoke scenario for verifying a fresh
MinionsOS installation end-to-end. Run this after `./install.sh` completes
successfully and before declaring a release candidate ready.

Set `MINIONS_FAKE_CLAUDE=1` in your environment to stub the `claude` CLI with a
no-op script during automated wiring checks (subprocess orchestration is verified
without requiring a live Anthropic API key).
Roles are always hosted by Claude Code; Codex is reachable only as a sub-agent
via the `codex-subagent` MCP and is not exercised by this scenario.

---

## Prerequisites

- `./install.sh` completed without errors.
- `uv`, `node >=16`, and `git` are on PATH.
- EACN3 source is present (`mcp-servers/eacn3/pyproject.toml` exists).
- At least one free port in 37596–37999.

---

## Steps

### Step 1 — Doctor check

```
./mos doctor
```

Expected: all checks pass (uv, node, git, EACN3 plugin built, port range available).
No `[FAIL]` lines.

### Step 2 — Status on empty state

```
./mos status
```

Expected: "No active projects." (or equivalent empty dashboard). Exit 0.

### Step 3 — Launch Gru (fake mode)

```
MINIONS_FAKE_CLAUDE=1 ./gru
```

Expected: Gru session starts (or fake stub exits 0). No Python import errors.

### Step 4 — Create a project via MCP tool

Inside a Gru session (or via direct tool call in test harness):

```python
project_create(real_name="Smoke Test Paper", venue="NeurIPS 2026")
```

Expected: returns `{port: <N>, path: "project_<N>/"}` where N is in 37596–37999.
`minions/state/projects.json` is created/updated with the new entry.
`project_<N>/` directory exists with `meta.json`, `CLAUDE.md`, and `AGENTS.md`.

### Step 5 — Verify EACN3 backend started

```
curl http://127.0.0.1:<PORT>/health
```

Expected: HTTP 200 with `{"status": "ok"}` (or equivalent).
`project_<N>/logs/backend.log` exists and contains startup lines.

### Step 6 — List projects

```
./mos project list
```

Expected: one row showing the project created in Step 4 with status `active`.

### Step 7 — Spawn default roles via MCP

Default roles are not auto-spawned by `project_create`. Inside a Gru
session, spawn the standard set:

```python
mos_spawn_role(port=<PORT>, role_name="noter")
mos_spawn_role(port=<PORT>, role_name="coder")
mos_spawn_expert(port=<PORT>, expert_slug="dl-arch")
```

Expected: `./mos role list <PORT>` lists `noter`, `coder`, `expert-dl-arch`
as `active`. `project_<N>/logs/role-noter.log` etc. exist. Each role runs
in its own tmux session named `mos-<PORT>-<role>`.

### Step 8 — Bridge a message between projects (requires two projects)

Create a second project (repeat Step 4 with a different name), then:

```python
mos_project_bridge(
    from_port=<PORT1>,
    to_port=<PORT2>,
    to_agent_id="gru",
    content="Hello from P1",
    mode="quote",
)
```

Expected: returns `{ok: true}`. Message appears in `project_<PORT2>` EACN event
stream addressed to `gru` (check via `eacn3_get_events` or backend log).

### Step 9 — Make project dormant

```python
project_dormant(port=<PORT>)
```

Expected: EACN3 backend subprocess stops. `meta.json` status = `dormant`.
Git tag `minionsos/dormant/project-<N>-<ts>` exists in the parent repo.

### Step 10 — Verify dormant in status

```
./mos status
```

Expected: project shows as `dormant`.

### Step 11 — Revive project

```python
project_revive(port=<PORT>)
```

Expected: EACN3 backend restarts on the same port. `meta.json` status = `active`.
Roles from `meta.json.active_roles` are respawned.

### Step 12 — Revive with external feedback

```python
project_revive(
    port=<PORT>,
    external_feedback="External reviewer suggested adding ablation study.",
    feedback_source="NeurIPS 2026 Area Chair"
)
```

Expected: feedback archived under
`project_<N>/branches/main/handoffs/external-feedback/<ts>.md`.
EACN broadcast sent to all roles.

### Step 13 — Close project

```python
project_close(port=<PORT>)
```

Expected: `meta.json` status = `closed`. Git tags
`minionsos/dormant/project-<N>-<ts>` (if the project was still active) and
`minionsos/closed/project-<N>` exist in the parent repo.
Port added to `retired_ports` in `projects.json`.

### Step 14 — Verify port is retired

Attempt to create a new project and confirm the closed port is NOT reused:

```python
p = project_create(real_name="New Paper")
assert p["port"] != <CLOSED_PORT>
```

### Step 15 — Wipe

```
./mos wipe <PORT>
```

Expected: `project_<N>/eacn3_data/` removed. Confirmation message printed.
`projects.json` entry updated or removed. No errors.

---

## Automated subset (MINIONS_FAKE_CLAUDE=1)

Steps 1, 2, 3, 4 (state file creation only), 6, 9 (state transition only),
10, 13 (state transition only), and 14 can be run without a live claude CLI
by setting `MINIONS_FAKE_CLAUDE=1`. The fake stub writes a sentinel file
`minions/state/fake_claude_invoked` so tests can assert the subprocess was
called with the correct arguments.
