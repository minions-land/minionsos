# MinionsOS Manual — Agent's Tool Book

You are an agent inside a MinionsOS project. This folder is your tool-book.
Read in this order, **only as deep as needed**:

| Layer | When | File |
|---|---|---|
| **L1** | Every wake — keep open | `README.md`, `INDEX.md`, `DECISION-MAP.md`, `PITFALLS.md` |
| **L2** | When you've picked a domain | First ~10 lines of each `NN-*.md` |
| **L3** | When you're about to call a specific tool | The matching entry inside `NN-*.md` |

## How to use

1. **Got a goal?** → open `DECISION-MAP.md`, find row, jump to the chapter it points to.
2. **Heard a tool name?** → grep it in `INDEX.md`, jump to the entry.
3. **About to take a destructive / cross-role action?** → grep it in `PITFALLS.md` first.
4. **Tool failed?** → check `12-issues-debug.md` and `PITFALLS.md` before retrying.

## Chapter map

| File | Domain |
|---|---|
| `01-lifecycle.md` | Projects, roles, spawn, dismiss, phase, signboard |
| `02-eacn3-comms.md` | EACN messaging, tasks, bids, `mos_await_events` |
| `03-experiments.md` | `mos_exp_*`, queue, GPU pool |
| `04-memory-draft.md` | L1 process memory (Draft) |
| `05-memory-book.md` | L2 compiled knowledge (Book) |
| `06-memory-shelf-reel.md` | L3 Shelf + L0 Reel |
| `07-publish-handoffs.md` | Cross-role writes via `mos_publish_to_shared` |
| `08-paper-search.md` | arXiv / PubMed / bioRxiv / Scholar / Semantic |
| `09-deliverables.md` | `mos_submit`, `mos_evaluate`, `mos_adjudicate`, review |
| `10-visual-render.md` | `mos_visual_render/inspect/check` |
| `11-runtime-control.md` | Wake loop, context reset, compact, attach, kill |
| `12-issues-debug.md` | `mos_issue_report` + log triage |
| `13-bridge.md` | `mos_project_bridge` (Gru only) |
| `14-role-evolution.md` | SPLIT / MERGE / DISMISS (Gru only) |
| `99-source-evidence.md` | Where the rules in this manual came from |

## Two rules every role must know

1. **Read your whitelist first.** Tools you don't have access to will fail with `not allowed for role 'X'`. Don't retry the same call hoping it appears — see `12-issues-debug.md` § "tool denied".
2. **Cross-role writes go through `mos_publish_to_shared` only.** Never `cp` into another role's branch. See `07-publish-handoffs.md`.
