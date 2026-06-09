---
id: mos_project_revive
kind: tool
domain: lifecycle
auth: [gru]
source: minions/tools/mcp/project_tools.py:106
since: stub
keywords: []
related: [mos_project_create, mos_project_list, mos_list_roles]
status: stable
---

# mos_project_revive

Restart an existing project from recorded lifecycle state.

## Signature

```python
mos_project_revive(port: int)
```

## Use

Call this when a project already exists and needs its backend and Roles
running again. Revive uses `minions/state/projects.json` and
`projects/project_<port>/meta.json`; it does not create a new project.

Revive starts the EACN3 backend if needed, refreshes project-local
registration, and launches the recorded Role sessions with the current
SYSTEM.md, whitelist, MCP config, and MANUAL guidance.

## Sequence

1. `mos_project_list` to confirm the project and status.
2. `mos_project_revive(port)` to bring it up.
3. `./mos doctor` to check backend/Gru/role wiring.
4. `mos project repair <port>` if doctor reports missing Gru or role
   registration.
5. `mos_list_roles(port)` before spawning additional Experts.

Do not use `mos_project_create` for an existing project tree.
