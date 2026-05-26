---
slug: coder-graph-mcp
summary: Open before reading code, planning a refactor, or estimating impact. Routes the nine mcp__codegraph__* read tools — symbol lookup, callers, blast radius, source survey — to the right question. Replaces grep/find/Read for code-structure questions.
layer: scheduling
tools:
version: 1
status: active
references: shelf-mcp, coding-methodology
provenance: human
---

# Skill — Coder graph MCP manual (L3 structural index over code)

The Coder graph is the project's L3 structural index over **source code**,
the counterpart to the Shelf graph (L3 over compiled prose). It is
rebuilt automatically by `@colbymchenry/codegraph`'s bundled OS-event
watcher (~1s debounce on save, $0 in API spend) — Roles do not write to
it. The `mcp__codegraph__*` MCP tools are read-only queries against the
live SQLite + FTS5 index at `<scope>/.codegraph/codegraph.db`, where
`<scope>` is `project_${PORT}/branches/coder/` for project work or the
repo root for system-maintenance.

The Coder graph answers questions raw `Bash grep` is bad at: "what calls
this function", "what would break if I rename this", "where is this
symbol defined across 19 supported languages", "which framework route
lands in this controller". A direct Coder-graph answer is typically 1–3
calls; a grep + Read exploration is dozens.

## When to invoke

Open this skill when the next code action benefits from structural context
the local file cannot supply on its own. Typical triggers:

- About to refactor a function — call `codegraph_impact` first to scope the blast radius.
- Tracing how a request reaches a handler — `codegraph_callers` walks the chain in milliseconds.
- Reading unfamiliar code — `codegraph_context` returns the relevant area as one bundle, not a fan-out of file reads.
- Verifying "X is unused" — `codegraph_callers` returns empty if so; grep would miss dynamic calls.
- Picking where to land a new method — `codegraph_search` finds the host class plus its members.

If your question is fact-shaped and answerable from a single file you
already have open, edit directly; do not open the Coder graph for a
1-line change.

## Boundary with the Shelf graph and other layers

| Question shape | Answer here |
|---|---|
| "What calls X / what does X call / what breaks if X changes" | **Coder graph** (`codegraph_callers`, `codegraph_callees`, `codegraph_impact`) |
| "Show me X's source / signature / docstring" | **Coder graph** (`codegraph_node`) |
| "Survey this code area" | **Coder graph** (`codegraph_explore` — one capped call) |
| "Which concepts cluster, god-nodes, community" | **Shelf graph** (`mcp__graphify__*`, see [[shelf-mcp]]) |
| "What did exp-042 report" | **Book / Draft**, not a graph |

The two graphs index disjoint data (code vs prose) and update on different
clocks (codegraph: ~1s OS-event watcher; graphify: role-on-demand). The
cross-reference: a graphify concept node whose label looks like a code
identifier is a pivot opportunity — call `codegraph_search` on the label
to jump from "this paper claim" to "this function".

## The nine tools, by question shape

**Light surface (cheap, structural — universally available):**

| Tool | The question it answers |
|---|---|
| `mcp__codegraph__codegraph_search` | "What is the symbol named X?" — entry point. Returns kind + location + signature. |
| `mcp__codegraph__codegraph_callers` | "What calls this function?" — call-site list. |
| `mcp__codegraph__codegraph_callees` | "What does this call?" — outgoing call edges. |
| `mcp__codegraph__codegraph_impact` | "What would break if I change this?" — transitive blast radius. |
| `mcp__codegraph__codegraph_node` | "Tell me about this single symbol." — full attributes; for class/struct/interface, returns structural outline (members + signatures), not a multi-thousand-character source dump. |
| `mcp__codegraph__codegraph_files` | "What's in this directory?" — indexed file structure. |
| `mcp__codegraph__codegraph_status` | "Is the index ready / how big is it?" — health and stats. |

**Heavy surface (returns source code — Coder + Expert only at server-side authz):**

| Tool | The question it answers |
|---|---|
| `mcp__codegraph__codegraph_context` | "What's the deal with this task / area?" — composes search + node + callers + callees in one call. PRIMARY entry for unfamiliar code. |
| `mcp__codegraph__codegraph_explore` | "Show me several related symbols' source." — ONE capped call across multiple files. Prefer over many `codegraph_node` / Read. |

## Procedure (the canonical flow)

1. State the question in one sentence. If it is content-shaped (fact
   about prose, exp result, paper claim), abandon this skill — use
   Draft / Book / [[shelf-mcp]].
2. Call `codegraph_status`. If `node_count == 0`, the index is stub
   (fresh scope, never bootstrapped). Read directly via `Read` and tell
   Gru the scope needs `codegraph init -i` (the launcher refuses to
   start without an index, so the bootstrap is one-time per scope).
3. Pick the question shape:
   - **Refactor planning**: `codegraph_search` → `codegraph_callers` → `codegraph_impact`. Blast radius from `impact`, not from walking callers manually.
   - **Onboarding / unfamiliar area**: `codegraph_context` first. If still unclear, `codegraph_explore` for breadth, then `codegraph_node` on specific symbols.
   - **Single-symbol detail**: `codegraph_node`.
4. Make the edit. Wait for the next turn before re-querying — the
   watcher needs ~500ms–1s to debounce and sync after a save.

## Pitfalls

- **Grepping first.** `codegraph_search` is faster, returns kind + location + signature in one shot, and handles 19 languages without language-specific flags. Reach for grep only to confirm a detail codegraph could not surface.
- **Looping `codegraph_node` over many symbols.** Each call re-reads the whole context. One `codegraph_explore` call returns them all grouped by file at a fraction of the cost.
- **Querying the index immediately after editing.** The watcher needs ~500ms–1s to debounce. Wait for the next turn.
- **Treating ambiguous calls as authoritative.** Cross-file resolution is best-effort name matching; an ambiguous call may return multiple candidates. Confirm with `codegraph_node` on the candidate that fits the call site's imports.
- **Asking heavy tools for what light tools can answer.** Heavy tools dump source into your context; if you only need "who calls this", the lighter tool is the right answer.
- **Loading every tool reflexively.** Form the structural question first, pick one tool, call it.
- **Missing index.** If `codegraph_status` reports stub, do not block — read the file directly. Bootstrap is `codegraph init -i` at the relevant scope; report this to Gru rather than retrying the MCP tools.
