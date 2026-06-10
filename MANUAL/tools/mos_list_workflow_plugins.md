---
id: mos_list_workflow_plugins
kind: tool
domain: lifecycle
auth: [gru]
source: minions/tools/mcp/spawn_tools.py:86
since: stable
keywords: [workflow, plugin, expert, mcp, evoany, spawn]
related: [mos_spawn_expert]
status: stable
---

# mos_list_workflow_plugins

**One line:** Gru-only discovery for workflow plugins that can be attached to a spawned Expert.

## Signature
```py
mos_list_workflow_plugins() -> {
  "workflow_plugins": [
    {
      "slug": str,
      "name": str,
      "description": str,
      "version": str,
      "has_mcp": bool,
      "has_domain_pack": bool,
      "skills_count": int,
      "eacn_domains": [str],
    }
  ],
  "count": int,
}
```

## Behaviour
- Scans `workflow-plugins/*/manifest.yaml`.
- Reports plugin metadata and whether the plugin provides its own MCP server.
- Does not start any process and does not mutate project state.

## Use
```py
plugins = mos_list_workflow_plugins()
mos_spawn_expert({
    "project_port": 37597,
    "domain": "evolutionary-optimization",
    "workflow_plugin": "evoany",
    "init_brief": "Use the plugin tools on the assigned target.",
})
```

When spawned, the Expert gets the base MCP servers plus the plugin's per-instance
MCP server and plugin skills/domain context.

## Don't
- Don't add plugin servers to global `.mcp.json`; spawn generates the
  per-instance MCP config.
- Don't call plugin tools from Gru; the spawned Expert owns them.
