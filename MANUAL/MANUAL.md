# MinionsOS Manual — Agent Quickstart

**You are a Role agent inside a MinionsOS project. This file is the only one
always in your context. Everything else you fetch on demand via `lookup.py`.**

## How the manual works (3 layers)

| Layer | What | Cost |
|---|---|---|
| **L0** | This file. Always loaded. | ~700 tokens |
| **L1** | Domain cards: `MANUAL/domains/<domain>.md`. ~14 files, ~40 lines each. Fetch when you've narrowed to a domain. | ~400 tok each |
| **L2** | Atomic pages: `MANUAL/tools/<id>.md`, `MANUAL/pitfalls/<id>.md`. Each ≤ 80 lines. Fetch the one page you need. | ~300 tok each |

**The lookup CLI** (use this exactly like `ToolSearch`):
```bash
python3 MANUAL/scripts/lookup.py "queue dispatch retry"        # top 5 hits + paths
python3 MANUAL/scripts/lookup.py --id mos_exp_queue_submit     # full page
python3 MANUAL/scripts/lookup.py --id mos_exp_run --section signature
python3 MANUAL/scripts/lookup.py --domain experiments          # list a domain
python3 MANUAL/scripts/lookup.py --decision "I want to publish" # goal-driven
python3 MANUAL/scripts/lookup.py --pitfalls "queue"            # known traps
```

Every page carries `source: <file>:<line>`. If the page isn't enough, read source.

## Cold-start protocol (every wake)

```
1. mos_draft_view              # what was I doing? what did past-me leave? (no-arg orient)
2. mos_await_events            # what's new on EACN?
   → for each event: act
3. when context > 70%: mos_compact_context
   when phase boundary:        mos_reset_context
```

## Domains (run `lookup.py --domain <name>` for the card)

| Domain | What |
|---|---|
| `eacn3` | EACN messaging, tasks, bids, agent registration. **Project_37596 thrash zone.** |
| `lifecycle` | (Gru) projects, roles, spawn, dismiss, phase, signboard |
| `experiments` | (Coder) `mos_exp_*`, queue, GPU pool |
| `memory` | Reel (L0), Draft (L1), Book (L2) |
| `publish` | Cross-role writes via `mos_publish_to_shared` (THE only legal path) |
| `papers` | (Writer) arXiv / PubMed / bioRxiv / Scholar / Semantic |
| `deliverables` | (Gru) `mos_submit`, `mos_evaluate`, `mos_adjudicate`, `mos_review_run` |
| `visual` | LaTeX/HTML/MD render + vision-model inspect |
| `runtime` | wake loop, compact, reset, attach |
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
   python3 MANUAL/scripts/lookup.py "<topic>"     # 0-cost, returns exact tool id
   ```
   ```
   ToolSearch(query="select:<exact-id-from-lookup>")   # loads the schema
   ```
   Then call the tool. **Do NOT call `ToolSearch` with a fuzzy keyword query** — MANUAL is the canonical name catalog and answers in 0ms; reaching for ToolSearch first wastes a turn on LLM-side fuzzy matching. (PITFALLS: `pitfall-deferred-schema`.)

## Top pitfalls — read once, save hours

```bash
python3 MANUAL/scripts/lookup.py --pitfalls ""   # list all
```

Highest-impact (from project_37596):
- `pitfall-deferred-schema` — "tool not found" when ToolSearch hasn't loaded it yet
- `pitfall-empty-authz` — slug-SUFFIX expert names get empty whitelist (P0)
- `pitfall-queue-deadlaunch-fp` — `{project_workspace}` not expanded → false-OOM, retry storm
- `pitfall-opus-empty-input` — long CJK / LaTeX heredoc → empty `tool_use.input`
- `pitfall-adjudicate-misuse` — `mos_adjudicate` is for final answers, not mid-run closure

## Maintenance (when MinionsOS changes)

When a tool is added / renamed / removed in `minions/tools/mcp/*.py` or
`mcp-servers/eacn3/plugin/index.ts`:
```bash
python3 MANUAL/scripts/gen_tool_stubs.py     # scaffold missing pages
python3 MANUAL/scripts/gen_eacn3_stubs.py    # same for EACN3
python3 MANUAL/scripts/build_index.py        # rebuild INDEX.json
python3 MANUAL/scripts/validate.py           # detect drift; CI-safe
```

`validate.py` exits 1 on real drift (BAD_SOURCE / DRIFT) and 0 on warnings only.
