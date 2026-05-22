# Reel (L0) — Raw Session-Level Memory Layer

## Concept

Reel is the lowest layer of MinionsOS's multi-agent memory architecture. It captures **verbatim transcripts** of every subagent and codex dispatch, providing the unalterable audit trail that backs every Draft node, Book page, and Shelf entry.

**Memory stack:**

| Layer | What | Where | Audience | Lifetime |
|---|---|---|---|---|
| **L0 Reel** | Raw verbatim session traces | `branches/<role>/reel/<session_id>/` | Role-private (Gru cross-role) | Indefinite, archive-marked after 30d if unreferenced |
| **L1 Draft** | Working coordination graph | `branches/shared/draft/draft.json` | All roles | Decay by node type (30d–365d half-life) |
| **L2 Book** | Compiled durable knowledge | `branches/shared/book/` | All roles read; Noter writes | No decay |
| **L3 Shelf** | Cross-project structural index | `~/.minionsos/shelf.json` | Gru only | No decay |
| **L4 Library** (future) | Global federated project archive | EACN3 network | Public (federated) | Forever |

L0 is the foundation: every higher layer carries `reel_ref` pointers back to L0, so any auditor can drill down from a high-level claim to the raw execution frame that produced it.

## Design principles

1. **Zero role burden.** Roles never call reel-write tools. The `reel_capture` PostToolUse hook archives `Agent` / `Task` / `mcp__codex-subagent__codex` outputs automatically.
2. **Drill-down only.** Reel is never injected at wake-up. It is read on-demand via `mos_reel_get` / `mos_reel_window`.
3. **Full fidelity.** Transcripts are copied verbatim, not summarized. Large files are accepted as a deliberate trade-off for replayability.
4. **Role-private by default.** Each role writes to its own branch under `branches/<role>/reel/`. Gru holds cross-role read permission for coordination and audit.
5. **Library-ready.** The directory layout and reel_ref pointer scheme are designed so a future `mos_library_export(port)` can bundle reels with Draft/Book/Shelf into a single replayable package.

## File layout

```
project_{port}/branches/<role>/reel/<session_id>/
├── index.jsonl          # One line per captured event
└── transcripts/
    ├── <task_id>.jsonl  # Verbatim subagent/codex transcript
    ├── <task_id>.jsonl
    └── ...
```

**Index entry schema** (one JSON object per line in `index.jsonl`):

```json
{
  "seq": 17,
  "ts": "2026-05-22T12:34:56.789Z",
  "kind": "subagent" | "codex" | "role_main",
  "task_id": "a1b2c3d4e5f6",
  "draft_refs": ["H-003", "Q-007"]
}
```

**Reel reference format:**

```
<role>/<session_id>/<task_id>
```

Example: `coder/sess-20260522-123456/agent-001-math`

## MCP tools

### `mos_reel_get(ref) → dict`

Read a single transcript by reference.

**Args:**
- `ref` (str): Reel reference in the form `<role>/<session_id>/<task_id>`

**Returns:**
```python
{
  "ref": "coder/sess-...",
  "role": "coder",
  "session_id": "sess-...",
  "task_id": "...",
  "kind": "subagent",
  "ts": "2026-05-22T...",
  "draft_refs": [],
  "lines": [  # Parsed JSON objects from the transcript
    {"type": "user", "content": "..."},
    {"type": "assistant", "content": "..."},
    ...
  ]
}
```

**Raises:**
- `PermissionError` — non-Gru role tries to read another role's reel
- `ValueError` — malformed ref or missing transcript

### `mos_reel_window(ref, span=5) → list[dict]`

Read a window of index entries around a reference (without loading full transcripts).

**Returns:** List of index entries (seq, ts, kind, task_id, draft_refs) sorted by seq.

## Auto-injection of `reel_ref`

When `MINIONS_ROLE_NAME` and `MINIONS_SESSION_ID` are set in the role's environment, `reel_ref` is automatically injected into:

1. **Draft nodes** — `mos_draft_append` sets `node.metadata.reel_ref = "<role>/<session_id>"` on every appended node (without `task_id` because Draft writes happen between tool calls, not after a specific one).
2. **Book source pages** — `mos_book_ingest` embeds `reel_ref:` in the YAML frontmatter.
3. **Future** — Shelf entries and Library exports will follow the same pattern.

## Hook configuration

The `reel_capture` hook is registered in `.claude/settings.json`:

```json
{
  "PostToolUse": [
    {
      "matcher": "Agent|Task|mcp__codex-subagent__codex",
      "hooks": [
        {
          "type": "command",
          "command": ".venv/bin/python minions/hooks/reel_capture.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

The hook:
1. Reads the PostToolUse payload from stdin.
2. Skips if `tool_name` is not in `{Agent, Task, mcp__codex-subagent__codex}` or if `output_file` is missing.
3. Reads `MINIONS_PROJECT_PORT`, `MINIONS_ROLE_NAME`, `MINIONS_SESSION_ID` from env.
4. Copies `tool_response.output_file` to `branches/<role>/reel/<session_id>/transcripts/<task_id>.jsonl`.
5. Appends an index entry to `branches/<role>/reel/<session_id>/index.jsonl`.

Failures are logged to stderr but never fail the hook (exit 0 always).

## Authz matrix

| Role | `mos_reel_get` (own) | `mos_reel_get` (other role) | `mos_reel_window` (own) | `mos_reel_window` (other role) |
|---|---|---|---|---|
| Gru | ✅ | ✅ | ✅ | ✅ |
| Coder | ✅ | ❌ | ✅ | ❌ |
| Writer | ✅ | ❌ | ✅ | ❌ |
| Ethics | ✅ | ❌ | ✅ | ❌ |
| Expert | ✅ | ❌ | ✅ | ❌ |
| Noter | ❌ (denied at MCP level) | ❌ | ❌ | ❌ |

Noter is excluded because it observes the project through `events/*.jsonl` and the Draft, not through subagent transcripts. Reel-level data would be redundant noise for Noter's role.

## Pluggable / migrable design

The Reel system is intentionally portable:

- **Storage** is plain JSONL files under git worktrees — no database, no special format
- **Pointer scheme** is a simple string (`<role>/<session>/<task>`) — portable across machines
- **Auto-injection** is opt-in: if `MINIONS_SESSION_ID` is unset, no reel_ref is added (graceful degradation)
- **Hook is optional** — if removed, the system still works; just no auto-capture

A future `mos_library_export(port)` can:
1. Bundle `branches/<role>/reel/*` from every role
2. Bundle `branches/shared/draft/`, `book/`, etc.
3. Strip any author-local paths (already a v12.1 invariant)
4. Produce a portable archive that another machine can `mos_library_import(url)` to fully replay the project

## Pain points and open questions

- **Storage growth.** Subagent transcripts can be 1–80 MB each. A long-running project may accumulate hundreds. Mitigation: Noter periodic lint marks unreferenced sessions as `archived: true` after 30 days. Hard deletion is deferred until storage pressure is observed.
- **No cross-session linkage yet.** Two reel entries for the same conceptual task across sessions are not auto-linked. The Draft's `pending_plan` mechanism already handles this for explicit handoffs.
- **No replay tooling yet.** Reel transcripts can be read but there's no "rehydrate the agent's context" command. Library export will need this.

## Code map

| Concern | File |
|---|---|
| Storage + read operations | `minions/tools/reel.py` |
| MCP wrappers | `minions/tools/mcp/reel_tools.py` |
| Hook | `minions/hooks/reel_capture.py` |
| Hook registration | `.claude/settings.json` (PostToolUse matcher) |
| Authz | `minions/config/__init__.py` (`_REEL_TOOLS`, server authz lists) |
| Tool surface registry | `minions/tools/mcp/_common.py` (`_MINIONS_MCP_TOOL_NAMES`) |
| Draft integration | `minions/tools/draft.py` (`_env_reel_context`, auto-injection in `mos_draft_append`) |
| Book integration | `minions/tools/book.py` (`_render_source_frontmatter` accepts `reel_ref`) |
| Role env setup | `minions/lifecycle/role_launcher.py` (`_role_env` generates `MINIONS_SESSION_ID`) |
| Tests | `tests/unit/test_reel.py` (8) + `test_reel_hook.py` (5) + `test_draft_reel_integration.py` (6) + `test_mcp_authz.py` (2) |
