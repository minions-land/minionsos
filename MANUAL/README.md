# MANUAL — agent's tool book for MinionsOS

A retrieval-shaped manual that replaces "read the source" or "read CLAUDE.md" as
the default way for Gru and Role agents to learn MinionsOS / EACN3.

## Why this exists

The MinionsOS surface is 131 MCP tools across `minions/tools/mcp/*.py` and
`mcp-servers/eacn3/plugin/index.ts` plus 15 governance / lifecycle / memory
domains. Reading source on every wake costs **~890 KB / ~2.4 M tokens** for a
batch of operational questions. Reading the right manual page costs a small
targeted lookup instead of a full source scan.

## Structure

```
MANUAL/
├── MANUAL.md             ← L0: ALWAYS-ON entry doc (~700 tokens)
├── INDEX.json            ← machine-readable index built from page frontmatter
├── SCHEMA.md             ← page schema; read once, never again
├── domains/              ← L1 domain cards (15 files, ~40 lines each)
│   ├── eacn3.md
│   ├── lifecycle.md
│   ├── experiments.md
│   ├── memory.md
│   ├── publish.md
│   └── ...
├── tools/                ← L2 atomic tool pages (131 files, ~30-80 lines each)
│   ├── mos_await_events.md      (curated)
│   ├── mos_publish_to_shared.md (curated)
│   ├── eacn3_send_message.md    (curated EACN direct-message page)
│   └── ...
├── pitfalls/             ← L2 known-failure pages from runtime evidence
│   ├── pitfall-deferred-schema.md
│   ├── pitfall-empty-authz.md
│   ├── pitfall-queue-deadlaunch-fp.md
│   └── ...
├── scripts/
│   ├── lookup.py            ← agent-facing retrieval CLI
│   ├── build_index.py       ← rebuilds INDEX.json from pages
│   ├── gen_tool_stubs.py    ← scaffolds Python @mcp.tool() pages
│   ├── gen_eacn3_stubs.py   ← scaffolds EACN3 TS plugin pages
│   ├── validate.py          ← drift detector (CI-safe)
│   ├── validate_mcp_operability.py ← hot-path MCP MANUAL gate
│   ├── validate_skill_operability.py ← Skill exposure / registration gate
│   └── test-questions.yaml  ← grounded operational questions
```

## Agent workflow (the load-bearing part)

```bash
# Once at startup
read $MINIONS_ROOT/MANUAL/MANUAL.md       # ~700 tokens

# Per question
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py "queue dispatch retry"
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --id mos_exp_queue_submit
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --decision "I want to publish a result"
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --pitfalls "queue"
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --domain experiments
```

Mirrors ToolSearch ergonomics: query → minimal payload of page ids + snippets,
then optional full-page fetch. Output budget ≤ 1 KB per query call.

## Maintenance workflow (when MinionsOS changes)

```bash
python3 $MINIONS_ROOT/MANUAL/scripts/gen_tool_stubs.py        # scaffold missing Python tool pages
python3 $MINIONS_ROOT/MANUAL/scripts/gen_eacn3_stubs.py       # scaffold missing EACN3 tool pages
python3 $MINIONS_ROOT/MANUAL/scripts/build_index.py           # rebuild INDEX.json
python3 $MINIONS_ROOT/MANUAL/scripts/validate.py              # drift detector
python3 $MINIONS_ROOT/MANUAL/scripts/validate_mcp_operability.py # critical MCP pages usable
python3 $MINIONS_ROOT/MANUAL/scripts/validate_skill_operability.py # Role Skill exposure usable
```

The validator checks three things:
1. Every `@mcp.tool()` Python decorator and every EACN3 `name: "..."` entry
   has a page under `tools/`.
2. Every page's `id:` matches a real tool.
3. Every page's `source: <file>:<line>` resolves — line still hits the
   actual decorator or `name:` line.

Exit code 0 = clean, 1 = real drift, 0 with warnings = orphan pages only.
Suitable for CI.

The MCP operability validator checks the hot-path Gru / Role pages that must be
usable without reading source: event intake wrappers, raw EACN event pages,
direct messages, task/bid/result protocol pages, review, and workflow-plugin
discovery. It fails when a critical page is still a stub or when its `auth:` /
`domain:` frontmatter disagrees with server-side MCP authorization.

The Skill operability validator checks the MinionsOS delivery shape: Role
skills must use repository `slug:` / `summary:` metadata, Role-facing docs must
route skills through `minions/roles/**/skills` markdown reads, workflow-plugin
sources must render into project-local bundles, and the resident Role prompt
must carry a `[Skills]` block.

## Coverage today

- **131 tool pages** (Python `@mcp.tool()` wrappers plus EACN3 plugin tools)
  - **15 domain cards**
- **8 pitfall pages** grounded in runtime evidence
- High-traffic tool pages are hand-curated; the remaining tool pages are auto-generated stubs with correct
  frontmatter and source line. They surface in `lookup.py` correctly and
  link to the source file for full signature.

## Validation

```bash
$ python3 $MINIONS_ROOT/MANUAL/scripts/validate.py
OK — 131 tools, 131 pages, no drift
$ python3 $MINIONS_ROOT/MANUAL/scripts/validate_mcp_operability.py
OK — 131 MCP tool pages have aligned metadata; 11 critical pages are operational
$ python3 $MINIONS_ROOT/MANUAL/scripts/validate_skill_operability.py
OK — Skill exposure matches Claude Code and MinionsOS Role semantics
```
