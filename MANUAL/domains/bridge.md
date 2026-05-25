---
id: domain-bridge
kind: domain
domain: bridge
auth: [gru]
source: minions/tools/mcp/project_tools.py:1
since: stable
keywords: [bridge, cross-project, gru, federation]
related: [mos_project_bridge]
status: stable
---

# Domain: Cross-project bridge (Gru only)

Cross-project visibility is **strictly Gru-only**. Roles inside a project see
nothing of any other project. Gru relays digested results.

## Single tool

```bash
lookup.py --id mos_project_bridge
```

## Hard rules

- Roles never bridge directly. A role wanting cross-project data DMs Gru.
- Bridges are read-only. No writes across project boundaries.
- Each call appends to `branches/shared/governance/bridges.jsonl` (audit).
- Bridges expire — re-bridge if acting on a digest > 1 h old.
