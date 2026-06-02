# MinionsOS Role Quickstart Guide

You are reading this on your **first wake** after spawn. By the time you reach
this file, you already have:

- **SYSTEM.md** — the full 12-section common contract (injected into the system
  prompt via `--append-system-prompt` before this process started).
- **initial_prompt** — cold-start steps, steady-state loop, keepalive protocol,
  compact vs reset rules (the first user message delivered at launch).
- **mos_draft_view()** — your wake orientation: a no-arg call returns a Draft
  orientation header (totals, pending_plans, counts) plus a node/edge slice.

This file is **not** a second copy of those rules. Its job is different: give
you the **project map** — what exists, where it lives, who owns it — so you can
navigate without rereading the contract on every operation.

---

## Where everything lives

### Documents — who reads what, when

| Document | Injected how | Read by | When |
|---|---|---|---|
| `minions/roles/SYSTEM.md` | `--append-system-prompt` (T=0) | All roles | Every wake, as system prompt |
| `initial_prompt` (in code) | First user message (T=1) | All roles | Every cold start |
| `minions/roles/QUICKSTART.md` (this file) | Agent `Read()` call (T=2) | All roles | First wake only |
| `MANUAL/` via `lookup.py` | Agent `Bash()` call (on demand) | All roles | Before calling an unfamiliar tool |
| `minions/roles/{role}/SYSTEM.md` | Appended to initial_prompt | That role | Every cold start |
| `minions/roles/{role}/skills/*.md` | Agent `Read()` (on demand) | That role | Before non-trivial actions |
| `minions/roles/common/skills/*.md` | Agent `Read()` (on demand) | All roles | Before framing-sensitive decisions |
| `CLAUDE.md` (root) | cwd CLAUDE.md walk (automatic) | Developer / agent* | Automatic unless hermetic mode |

*Note: In non-hermetic mode (default), Claude Code's cwd walk reaches
`MinionsOS/CLAUDE.md` automatically. That file is developer documentation;
rules that apply to you as a Role agent live in SYSTEM.md, not CLAUDE.md.

### Retrieval surfaces — three jobs, one each

| Surface | Job | When to use |
|---|---|---|
| `roles/{role}/skills/*.md` | Procedure — how to do something well | Before a non-trivial action with a known good procedure |
| `roles/common/skills/*.md` | Cross-role reasoning disciplines | Before framing-sensitive decisions |
| `MANUAL/` via `lookup.py` | Reference + authz — tool signatures, error patterns, pitfalls | Before calling a tool you haven't called recently |

Never substitute rereading SYSTEM.md or grepping source for a `lookup.py` call.

---

## Project layout

```
projects/project_{port}/
├── branches/
│   ├── {role}/              ← your workspace ($MINIONS_WORKSPACE)
│   │   └── .minionsos/heartbeat   ← updated every mos_await_events cycle
│   └── shared/
│       ├── draft/draft.json ← L1 Draft (process graph, pending_plans)
│       ├── book/            ← L2 Book (full, noter-curated)
│       └── shelf/           ← L3 Shelf (cross-project index, Gru only)
└── events/                  ← per-agent EACN event audit stream
```

L0 Reel (raw subagent transcripts) lives at `branches/{role}/reel/{session_id}/`.
Full memory-layer reference: `python3 MANUAL/scripts/lookup.py --domain memory`.

---

## Tool quick-reference

Signatures and full docs are in MANUAL. These one-liners are reminders only.

**Event loop**
- `mos_await_events()` — block until EACN delivers events; returns annotated batch
- `mos_noter_wait()` — timer-based wake, Noter only
- `mos_get_events(port)` — drain Gru's queue once, non-blocking, Gru only

**Draft (L1)**
- `mos_draft_summary()` — wake-injection summary; surfaces `pending_plan` nodes first
- `mos_draft_append(nodes=[...], edges=[...])` — add nodes/edges
- `mos_draft_commit_shared()` — flush to shared branch (Noter calls this; others call `mos_draft_append` freely)

**EACN**
- `eacn3_send_message(to, content)` — DM or broadcast
- `eacn3_create_task(...)` — publish work for bidding
- `eacn3_submit_bid(task_id)` — claim a task
- `eacn3_submit_result(task_id, result)` — deliver result

**Context**
- `mos_compact_context(reason, pending_plans)` — compress history, keep process alive
- `mos_reset_context(reason)` — hard reset, kills session; watchdog respawns cold

**Diagnostics**
- `mos_issue_report(title, description, severity, component)` — file a bug; fire-and-forget

For any tool not listed here, or before calling one you haven't used recently:
```bash
python3 MANUAL/scripts/lookup.py "<keyword>"
python3 MANUAL/scripts/lookup.py --id <tool_id>
python3 MANUAL/scripts/lookup.py --pitfalls ""
```

---

## One non-obvious rule not in SYSTEM.md

**Tool input hard cap: ~50 lines / ~3 KB per `tool_use` input.**

This is a host-level bug (Opus 4.7), not a context limit. Affects `Write.content`,
`Edit.new_string`, and `Bash.command` heredocs. Large structured inputs (LaTeX,
CJK, multi-section Markdown) are silently dropped with `InputValidationError`.

For any content larger than ~50 lines, use the **Tier 0 seed-and-Edit** recipe
from `roles/common/skills/reliable-file-io.md`:
1. Seed the file with a short `Write` (preamble + closing placeholder, ≤50 lines)
2. Append content in successive `Edit` calls (each ≤50 lines, each anchored on the placeholder)
3. Never put the full document into a Bash heredoc

Canonical source: `~/.claude/CLAUDE.md` (host-level). This file and
`minions/roles/SYSTEM.md §4` restate the rule so it reaches roles regardless of
hermetic-mode settings.

---

## Document map — where each rule lives

| Topic | Canonical home |
|---|---|
| Wake loop, triage, Plan→Workflow→Verify | SYSTEM.md §3, §4 |
| Context compact vs reset | SYSTEM.md §5 |
| Memory layers L0–L3 | SYSTEM.md §6; `lookup.py --domain memory` |
| Inter-role EACN rules | SYSTEM.md §7 |
| Write boundaries + publish paths | SYSTEM.md §8; `lookup.py --domain publish` |
| Evidence-first EACN style | SYSTEM.md §9 |
| Subagent handoff contract | SYSTEM.md §10 |
| Tool signatures + authz | `MANUAL/` via `lookup.py` |
| Pitfalls + error patterns | `lookup.py --pitfalls ""` |
| Role-specific scope + deviations | `minions/roles/{role}/SYSTEM.md` |
| Procedures for non-trivial actions | `roles/{role}/skills/` |

---

**You are oriented. Proceed to your role-specific SYSTEM.md for scope and
deviations, then enter the event loop.**
