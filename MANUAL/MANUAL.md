# MinionsOS Manual — Agent Quickstart

**You are a Role agent inside a MinionsOS project. This file is the only one
always in your context. Everything else you fetch on demand via `lookup.py`.**

## How the manual works (3 layers)

| Layer | What | Cost |
|---|---|---|
| **L0** | This file. Always loaded. | ~700 tokens |
| **L1** | Domain cards: `MANUAL/domains/<domain>.md`. ~15 files, ~40 lines each. Fetch when you've narrowed to a domain. | ~400 tok each |
| **L2** | Atomic pages: `MANUAL/tools/<id>.md`, `MANUAL/pitfalls/<id>.md`. Each ≤ 80 lines. Fetch the one page you need. | ~300 tok each |

**The lookup CLI** (use this exactly like `ToolSearch`; Role worktrees use
`$MINIONS_ROOT` to reach the repository manual):
```bash
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py "queue dispatch retry"        # top 5 hits + paths
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --id mos_exp_queue_submit     # full page
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --id mos_exp_run --section signature
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --domain experiments          # list a domain
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --decision "I want to publish" # goal-driven
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --pitfalls "queue"            # known traps
```

Every page carries `source: <file>:<line>`. If the page isn't enough, read source.

## MCP map

MinionsOS exposes four MCP layers:

| Layer | Server | Current use |
|---|---|---|
| OS tools | `minionsos` | 92 `mos_*` project, memory, lifecycle, review, experiment, visual, and runtime tools |
| Network substrate | `eacn3` | 39 `eacn3_*` agent-network tools for messages, tasks, bids, results, registry, and observability |
| Runtime keepalive | `keepalive` | `wait_bg` and `keepalive_now` for long background work |
| Workflow plugins | per Expert | Optional tools such as `evo_*`, attached by `mos_spawn_expert(..., workflow_plugin=...)` |

Claude Code may show a broad tool list for cache parity. Actual execution is
server-side authorized per role. If a page says a tool is Gru-only or Role-only,
follow that page even if the tool name appears in the visible list.

## Cold-start protocol (every wake)

For Expert and Ethics resident roles:

```
1. mos_draft_view              # what was I doing? what did past-me leave? (no-arg orient)
2. mos_await_events            # what's new on EACN?
   → for each event: act
3. when context > 70%: mos_compact_context
   when phase boundary:        mos_reset_context
```

For Gru project intake:

```
1. mos_unread_summary          # which active projects have Gru events?
2. mos_get_events({port})      # drain one project's Gru queue, mirror to disk
3. act via direct message, spawn/dismiss, review, bridge, or lifecycle tools
```

## Domains (run `lookup.py --domain <name>` for the card)

| Domain | What |
|---|---|
| `eacn3` | EACN messaging, tasks, bids, agent registration |
| `lifecycle` | (Gru) projects, roles, spawn, dismiss, phase, signboard |
| `experiments` | (Expert) `mos_exp_*`, queue, GPU pool |
| `memory` | Reel (L0), Draft (L1), Book (L2) |
| `publish` | Cross-role writes via `mos_publish_to_shared` (THE only legal path) |
| `papers` | (Expert) arXiv / PubMed / bioRxiv / Scholar / Semantic |
| `deliverables` | (Gru) `mos_submit`, `mos_evaluate`, `mos_review_run` |
| `visual` | LaTeX/HTML/MD render + vision-model inspect |
| `runtime` | MCP map, wake loop, compact, reset, attach |
| `skills` | Repository Role skill files and workflow-plugin skill mounting |
| `debug` | `mos_issue_report` + log triage |
| `bridge` | (Gru) cross-project read |
| `evolution` | (Gru) SPLIT / MERGE / DISMISS |
| `subagent-handoff` | What every spawned subagent prompt must carry (5 required fields) |

## Two non-negotiable rules

1. **Cross-role writes go through `mos_publish_to_shared` only.**
   `cp` / `mv` into another role's branch corrupts git state.
2. **Tool not loaded? Use the MANUAL → ToolSearch chain — never fuzzy-search.**
   The top-30 hot-path tools are eagerly loaded; the long tail is deferred. When you reach for a deferred tool:
   ```bash
   python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py "<topic>"     # 0-cost, returns exact tool id
   ```
   ```
   ToolSearch(query="select:<exact-id-from-lookup>")   # loads the schema
   ```
   Then call the tool. **Do NOT call `ToolSearch` with a fuzzy keyword query** — MANUAL is the canonical name catalog and answers in 0ms; reaching for ToolSearch first wastes a turn on LLM-side fuzzy matching. (PITFALLS: `pitfall-deferred-schema`.)

## Top pitfalls — read once, save hours

```bash
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --pitfalls ""   # list all
```

Highest-impact:
- `pitfall-deferred-schema` — "tool not found" when ToolSearch hasn't loaded it yet
- `pitfall-empty-authz` — slug-SUFFIX expert names get empty whitelist (P0)
- `pitfall-queue-deadlaunch-fp` — `{project_workspace}` not expanded → false-OOM, retry storm
- `pitfall-opus-empty-input` — long CJK / LaTeX heredoc → empty `tool_use.input`

## Maintenance (when MinionsOS changes)

When a tool is added / renamed / removed in `minions/tools/mcp/*.py` or
`mcp-servers/eacn3/plugin/index.ts`:
```bash
python3 $MINIONS_ROOT/MANUAL/scripts/gen_tool_stubs.py     # scaffold missing pages
python3 $MINIONS_ROOT/MANUAL/scripts/gen_eacn3_stubs.py    # same for EACN3
python3 $MINIONS_ROOT/MANUAL/scripts/build_index.py        # rebuild INDEX.json
python3 $MINIONS_ROOT/MANUAL/scripts/validate.py           # detect drift; CI-safe
python3 $MINIONS_ROOT/MANUAL/scripts/validate_mcp_operability.py # hot-path MCP gate
python3 $MINIONS_ROOT/MANUAL/scripts/validate_skill_operability.py # Skill exposure gate
```

`validate.py` exits 1 on real drift (BAD_SOURCE / DRIFT) and 0 on warnings only.
