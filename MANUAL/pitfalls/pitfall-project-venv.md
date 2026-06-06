---
id: pitfall-project-venv
kind: pitfall
domain: experiments
auth: ['*']
source: minions/tools/experiment_ssh.py:1
since: stable
keywords: [venv, pandas, torch, module, not, found, environment, uv, conda]
related: [mos_exp_run]
status: stable
---

# pitfall: `ModuleNotFoundError: No module named 'pandas' / 'torch' / 'mcp_minionsos'`

**Symptom:**
```
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'torch'
ModuleNotFoundError: No module named 'mcp_minionsos'
... no PROJECT venv
```

## Cause

Roles run inside the MinionsOS uv env which intentionally does NOT carry the
project's data-science deps. The project has its own venv (or conda env)
inside the project directory or `parent_repo`.

## Recipe

For ad-hoc analysis:
```python
mos_exp_run(
  command="cd /path/to/project && source .venv/bin/activate && python -c '...'",
  execution="local",
  log_path="/abs/branches/expert-math/exp/probe.log",
)
```

Or use the project venv's interpreter directly:
```python
mos_exp_run(
  command="/abs/path/to/project/.venv/bin/python script.py",
  execution="local",
  ...
)
```

## Don't

- **Don't `uv sync` from inside `branches/<role>/...`** — creates a nested
  `.venv` and breaks the role's MCP servers. project_37596 / expert-mathematician
  hit `os error 17 File exists` exactly this way.
- **Don't `import mcp_minionsos`** — the MCP server lives at `minions.tools.mcp`.
  But you almost never need to import it; call the tool through the MCP surface.
