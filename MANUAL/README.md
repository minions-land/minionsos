# MANUAL — agent's tool book for MinionsOS

A retrieval-shaped manual that replaces "read the source" or "read CLAUDE.md" as
the default way for Gru and Role agents to learn MinionsOS / EACN3.

## Why this exists

The MinionsOS surface is ~134 MCP tools across `minions/tools/mcp/*.py` and
`mcp-servers/eacn3/plugin/index.ts` plus ~12 governance / lifecycle / memory
domains. Reading source on every wake costs **~890 KB / ~2.4 M tokens** for a
batch of operational questions. Reading the right manual page costs **~25 KB
/ ~250 K tokens** — measured in `TEST-RESULTS.md`.

## Structure

```
MANUAL/
├── MANUAL.md             ← L0: ALWAYS-ON entry doc (~700 tokens)
├── INDEX.json            ← machine-readable index built from page frontmatter
├── SCHEMA.md             ← page schema; read once, never again
├── TEST-RESULTS.md       ← A/B test of source-only vs manual+lookup
├── domains/              ← L1 domain cards (~12 files, ~40 lines each)
│   ├── eacn3.md
│   ├── lifecycle.md
│   ├── experiments.md
│   ├── memory.md
│   ├── publish.md
│   └── ...
├── tools/                ← L2 atomic tool pages (~134 files, ~30-80 lines each)
│   ├── mos_await_events.md      (curated)
│   ├── mos_publish_to_shared.md (curated)
│   ├── eacn3_send_message.md    (auto-generated from plugin description)
│   └── ...
├── pitfalls/             ← L2 known-failure pages (real project_37596 evidence)
│   ├── pitfall-deferred-schema.md
│   ├── pitfall-empty-authz.md
│   ├── pitfall-queue-deadlaunch-fp.md
│   └── ...
├── recipes/              ← L2 multi-step recipes (currently sparse; grows over time)
├── scripts/
│   ├── lookup.py            ← agent-facing retrieval CLI
│   ├── build_index.py       ← rebuilds INDEX.json from pages
│   ├── gen_tool_stubs.py    ← scaffolds Python @mcp.tool() pages
│   ├── gen_eacn3_stubs.py   ← scaffolds EACN3 TS plugin pages
│   ├── validate.py          ← drift detector (CI-safe)
│   └── test-questions.yaml  ← 10 grounded operational questions
└── legacy/               ← original prose chapters; preserved for back-reference only
```

## Agent workflow (the load-bearing part)

```bash
# Once at startup
read MANUAL/MANUAL.md       # ~700 tokens

# Per question
python3 MANUAL/scripts/lookup.py "queue dispatch retry"
python3 MANUAL/scripts/lookup.py --id mos_exp_queue_submit
python3 MANUAL/scripts/lookup.py --decision "I want to publish a result"
python3 MANUAL/scripts/lookup.py --pitfalls "queue"
python3 MANUAL/scripts/lookup.py --domain experiments
```

Mirrors ToolSearch ergonomics: query → minimal payload of page ids + snippets,
then optional full-page fetch. Output budget ≤ 1 KB per query call.

## Maintenance workflow (when MinionsOS changes)

```bash
python3 MANUAL/scripts/gen_tool_stubs.py        # scaffold missing Python tool pages
python3 MANUAL/scripts/gen_eacn3_stubs.py       # scaffold missing EACN3 tool pages
python3 MANUAL/scripts/build_index.py           # rebuild INDEX.json
python3 MANUAL/scripts/validate.py              # drift detector
```

The validator checks three things:
1. Every `@mcp.tool()` Python decorator and every EACN3 `name: "..."` entry
   has a page under `tools/`.
2. Every page's `id:` matches a real tool (or is explicitly marked
   `status: deprecated`).
3. Every page's `source: <file>:<line>` resolves — line still hits the
   actual decorator or `name:` line.

Exit code 0 = clean, 1 = real drift, 0 with warnings = orphan pages only.
Suitable for CI.

## Coverage today

- **134 tool pages** (95 Python `@mcp.tool()` + 39 EACN3 plugin tools)
- **12 domain cards**
- **8 pitfall pages** (every one grounded in project_37596 log evidence)
- **17 hand-curated tool pages** for the high-traffic surface
- The remaining ~117 tool pages are auto-generated stubs with correct
  frontmatter and source line. They surface in `lookup.py` correctly and
  link to the source file for full signature.

## Validation

```bash
$ python3 MANUAL/scripts/validate.py
OK — 134 tools, 134 pages, no drift
```

## Test results summary

| | Source only | Manual + lookup |
|---|---:|---:|
| Bytes agent read | 890 596 | 24 946 |
| Codex input tokens | 2 392 620 | 248 215 |
| Wall-clock | 44 s | 1 s |
| Questions answered | 10/10 | 10/10 (2 more precise) |

See `TEST-RESULTS.md` for per-question detail.
