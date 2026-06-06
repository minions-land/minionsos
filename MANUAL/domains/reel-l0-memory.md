---
id: domain-reel-l0-memory
kind: domain
domain: memory
auth: ['*']
source: minions/tools/reel.py:1
since: stable
keywords: [reel, memory, provenance, claude_jsonl, draft, book]
related: [mos_reel_get, mos_reel_window, mos_draft_append, mos_book_ingest]
status: stable
---

# Reel (L0) — Pointer Index Memory Layer

Reel is MinionsOS's lowest memory layer. It does not copy transcript files into
the project worktree. Each role owns a flat `reel-index.jsonl` that points to
native Claude session JSONL and records the tool-use frame that produced later
Draft or Book evidence.

## Memory stack

| Layer | What | Where | Audience | Lifetime |
|---|---|---|---|---|
| **L0 Reel** | Pointer index to native Claude session JSONL | `branches/<role>/reel-index.jsonl` | Own role; Gru and Ethics cross-role | Project lifetime |
| **L1 Draft** | Working coordination graph | `branches/main/draft/draft.json` | All roles | Decay sidecar by node type |
| **L2 Book** | Compiled durable knowledge | `branches/main/book/` | All roles read; Ethics writes | No decay |

Higher layers carry `reel_ref` pointers, so an auditor can drill from a claim to
the execution frame that produced it.

## Design rules

1. Roles never call Reel write tools. The `reel_capture` PostToolUse hook appends index entries after `Agent` and `Task` tool use.
2. Reel is drill-down only. It is read on demand through `mos_reel_get` and `mos_reel_window`.
3. The project stores pointers, not transcript copies. The `claude_jsonl` field is an absolute path to the native session file.
4. Cross-role reads are restricted to Gru and Ethics. Experts read their own Reel entries only.

## Index layout

```
project_{port}/branches/<role>/reel-index.jsonl
```

Each line is a JSON object:

```json
{
  "ref": "<role>/<session_id>/<tool_use_id>",
  "ts": "2026-05-22T12:34:56.789Z",
  "kind": "subagent",
  "tool_name": "Agent",
  "claude_jsonl": "/abs/path/to/<session_id>.jsonl",
  "draft_node_refs": ["H-003", "Q-007"]
}
```

## Reference format

```
<role>/<session_id>/<tool_use_id>
```

Example: `expert/sess-20260522-123456/toolu-001`.

## MCP tools

`mos_reel_get(ref)` reads the matching index entry and returns parsed lines from
the native `claude_jsonl` file when the file is available.

`mos_reel_window(ref, span=5)` returns nearby index entries without loading the
full native JSONL.

## Auto-injection

When `MINIONS_ROLE_NAME` and `MINIONS_SESSION_ID` are set, Draft append helpers
can attach `metadata.reel_ref = "<role>/<session_id>"` to new nodes. Book ingest
can carry `reel_ref:` in page frontmatter. The hook itself uses
`CLAUDE_SESSION_ID` to locate the native JSONL file for indexed tool-use frames.

## Hook behavior

The `reel_capture` hook:

1. Reads the PostToolUse payload from stdin.
2. Skips tool names other than `Agent` and `Task`.
3. Reads `MINIONS_PROJECT_PORT`, `MINIONS_ROLE_NAME`, and `CLAUDE_SESSION_ID`.
4. Appends one entry to `branches/<role>/reel-index.jsonl`.
5. Exits 0 even when capture fails, because Reel capture is advisory.

## Authz matrix

| Role | Own Reel | Cross-role Reel |
|---|---|---|
| Gru | read | read |
| Ethics | read | read |
| Expert | read | denied |

## Code map

| Concern | File |
|---|---|
| Storage + read operations | `minions/tools/reel.py` |
| MCP wrappers | `minions/tools/mcp/reel_tools.py` |
| Hook | `minions/hooks/reel_capture.py` |
| Hook registration | `.claude/settings.json` |
| Authz | `minions/config/__init__.py` |
| Draft integration | `minions/tools/draft_nodes.py` |
| Book integration | `minions/tools/book_helpers.py` |
| Role env setup | `minions/lifecycle/role_launcher.py` |
