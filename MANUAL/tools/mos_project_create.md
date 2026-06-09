---
id: mos_project_create
kind: tool
domain: lifecycle
auth: [gru]
source: minions/tools/mcp/project_tools.py:33
since: stub
keywords: []
related: [mos_project_revive, mos_project_list, mos_spawn_expert, mos_list_roles]
status: stable
---

# mos_project_create

Create one new MinionsOS project and bootstrap its project-local runtime.

## Signature

```python
mos_project_create(
    real_name: str,
    venue: str | None = None,
    brief: str = "",
    base_branch: str = "HEAD",
    topic_doc: str | None = None,
    template_dir: str | None = None,
    profile: str = "scientific-paper",
)
```

## Use

Call this once when the author asks for a new project. The tool allocates
the port, seeds the per-project git repo and worktrees, starts the EACN3
backend, registers Gru, writes project metadata, and launches the profile's
initial Roles.

After success, keep the returned `port` as the project handle. Continue
with `mos_project_list`, `mos_list_roles`, `mos_spawn_expert`, direct
`eacn3_send_message` briefings, or `mos_project_revive` later.

## Do not

- Do not call this against an existing `projects/project_<port>` tree.
- Do not edit `minions/state/projects.json` to reserve or skip ports.
- Do not delete git refs or worktrees to force creation through.
- Do not call `minions.lifecycle.project_create` from ad-hoc Python.

If a directory, per-project bare repo, branch, worktree, backend, or tmux
session already exists, switch to the existing-project tools:
`mos_project_list`, `mos_project_revive`, `mos project repair <port>`,
`mos_list_roles`, and `mos_spawn_expert`.
