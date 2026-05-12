# MinionsOS — Session Acceptance Report

Date: 2026-05-10
Scope: one autonomous sitting covering batches **C2-step1**, the earlier
**E / C1 / B** trio, **Rust archival**, and the full **batch 3.1 series**
(MOS Agent Pool migration).

---

## 1. Headline result

Every internal MinionsOS role — Coder, Writer, Experimenter, Reviewer,
Ethics, Expert, Noter, and Gru — now talks to EACN3 through a single
MinionsOS-owned wrapper layer (the **MOS Agent Pool**, `mos_*`). The
wrapper adds a per-wake local ACK crash-shim while delegating to EACN3's
real protocol underneath. Gru retains raw `eacn3_*` tools specifically so
it can act as the human operator's agent terminal on Global EACN3 where
the MinionsOS-side shim does not apply.

- **EACN3**: zero changes. Every `mos_*` call routes through the existing
  `minions/lifecycle/eacn_client` HTTP wrappers.
- **`other/`**: zero changes.
- **`minions-viz/`**: zero changes.
- **All 397 unit tests green.** Viz smoke tests green (4/4). Other smoke
  scripts still import-clean.
- Ruff clean on both `minions/` and `tests/`; ruff format --check clean.

---

## 2. Cumulative git log (this session)

```
d8767a2 Version 5 Commit: chore: clean up residual eacn3_* references after MOS Agent Pool migration
708c8dd Version 5 Commit: feat: Gru SYSTEM.md routes internal work through MOS Agent Pool
179737a Version 5 Commit: feat: migrate Writer / Experimenter / Reviewer / Ethics / Expert / Noter to mos_*
30d1c16 Version 5 Commit: feat: migrate Coder to mos_* tools + extract shared whitelist constants
513e685 Version 5 Commit: feat: common role contract switches to mos_* + ultrathink-before-act
628e6e9 test: update mcp profile ceiling for Gru mos_* additions
d57fcae Version 5 Commit: feat: grant Gru access to mos_* tools alongside eacn3_*
38ba64d Version 5 Commit: feat: register mos_* MCP tools (no role wiring yet)
dcb8541 Version 5 Commit: feat: add mos_pool module — EACN3 wrapper + per-wake local ACK
e472241 Version 5 Commit: feat: noter reads role session archives non-destructively
343574d Version 5 Commit: feat: archive host session jsonl into role branch after each wake
b481ed4 Version 5 Commit: feat: role wake loop is eacn3_await_events(120s) with graceful exit
a184cf1 Version 5 Commit: feat: inject role SYSTEM.md into Codex via per-branch AGENTS.md
11eed56 Version 5 Commit: refactor: archive rust, restructure to branches/, wire lifecycle hooks
```

15 commits since the previous `Version 5 Commit: fix: align wake routing...`. Each is
single-purpose and individually revertable.

---

## 3. What changed, grouped by intent

### 3.1 Rust archived (single commit earlier in session)

- `crates/`, `Cargo.toml`, `Cargo.lock` moved to
  `other/rust-archive/`. `.gitignore` `target/` block removed. Docs
  references in `AGENTS.md`, `minions/CLAUDE.md`, and
  `docs/rust_proposal/minionsos-proposal.md` updated to describe
  archival status. The Rust crate is no longer in the active tree; it can
  be revived by moving the directory back.

### 3.2 Batch E — git_utils extraction

- New `minions/lifecycle/git_utils.py` with `run_git`, `is_git_work_tree`,
  `git_ref_exists`, `is_git_dirty`. Project.py now routes through these
  for 6 of its 7 git helpers (the two `git worktree add` call sites kept
  their own argv construction because tests pin specific argv).

### 3.3 Batch C1 — WakeupScheduler default

- `WakeupScheduler(mode="hooks")` is the default now. Legacy polling path
  preserved behind `mode="legacy"`; every test that exercises that path
  is explicitly pinned.

### 3.4 Batch B — LifecycleEvent extension + hook handlers

- `LifecycleEvent` gains 5 wake events
  (`wake_direct_message`, `wake_task_invitation`,
  `wake_eacn_queue_pending`, `wake_phase_change`, `wake_human_trigger`).
- `wake_signals` module registers default handlers on module import.
- Callers that used to directly invoke signal emitters wrapped in
  `try/except + logger.warning` now `hooks.fire(LifecycleEvent.*, data)`.
  Exception-swallow is centralised in `HookRegistry.fire`.

### 3.5 Batch C2-step1 — branches/ + .minionsos/ restructure

- Filesystem tier rename: `project_{port}/workspace/main/` →
  `project_{port}/branches/main/` (Gru now owns main worktree), plus
  `branches/<role>/` per role (flat, not nested under `roles/`).
- Scratchpad location: `memory/{role}.md` → `branches/{role}/.minionsos/scratchpad.md`,
  tracked by git on each role's own branch.
- `migrate_legacy_scratchpads(port)` runs on project revive and on Gru
  startup — safe-idempotent.
- Autouse conftest fixtures redirect `MINIONS_PROJECTS_ROOT` to a tmp dir
  per session and stub `ensure_role_workspace` / `project_scratchpad` /
  `project_role_log`. Unit tests can no longer pollute `/Users/mjm/project_*`
  or create real `minionsos/project-*` branches on the live repo.

### 3.6 Batch 2.1–2.4 (done in previous session seam)

- **2.1** Codex role SYSTEM.md injection via per-branch `AGENTS.md`. Codex
  stdin no longer inlines SYSTEM.md; Codex auto-discovers `AGENTS.md`
  from the branch cwd and treats it as instruction-layer. Claude keeps
  `--append-system-prompt`.
- **2.2** Role wake loop protocol rewritten: `await_events(120)` loop,
  graceful disconnect + commit + exit. No main-loop `/compact`, no
  scratchpad writes.
- **2.3** Host session jsonl archival. After each wake exits, MinionsOS
  copies the Claude/Codex session file into
  `branches/<role>/.minionsos/sessions/<timestamp>-wake<NNN>.jsonl`.
  This is Noter's source material. Full test coverage of Claude cwd
  encoding and Codex session_meta cwd matching.
- **2.4** Noter observation skill + narrowed whitelist: non-destructive
  EACN3 reads only; session-diff-timeline skill tells Noter how to read
  the archive dirs.

### 3.7 Batch 3.1 — MOS Agent Pool migration (main focus of this session)

**3.1.1 — `minions/lifecycle/mos_pool.py` (new module, 342 lines, 18 unit tests)**

Six callable functions:

| Function | Purpose |
|---|---|
| `mos_await_events(port, role, agent_id, timeout_seconds=60)` | Drain EACN3 events + copy to `pending.jsonl` |
| `mos_send_message(port, to, from, content)` | Thin wrapper over `eacn_client.send_message` |
| `mos_create_task(port, ...)` | Thin wrapper over `eacn_client.create_task` |
| `mos_pending_read(port, role)` | Read pending.jsonl |
| `mos_pending_wipe(port, role)` | Delete pending.jsonl entirely |
| `mos_ack_clear(port, role, event_ids)` | Remove ACK'd events by id; deletes file when empty |

Pending inbox path:
`project_{port}/branches/<role>/.minionsos/inbox/pending.jsonl`.
`_event_id` extracts a stable id from `msg_id` → `id` → `event_id` →
`task_id` → JSON-dump fallback.

Timeout clamp: `[0, 60]` to match EACN3 backend `Query(ge=0, le=60)`
constraint (verified by reading `EACN3/eacn/network/api/routes.py:641`).

**3.1.2 — MCP tool registration**

Six `@mcp.tool()` wrappers for the above. Added to `_MINIONS_MCP_TOOL_NAMES`
so per-role whitelist filtering and profile filtering work.

**3.1.3 — Gru whitelist**

Added `mos_*` alongside existing `eacn3_*` (Gru keeps both).

**3.1.4 — Coder migration**

Coder's whitelist: `eacn3_*` wildcard → `_INTERNAL_ROLE_EACN_TOOLS`.
Coder SYSTEM.md §Collaboration rules updated.

Introduced 3 shared whitelist constants in `minions/config/__init__.py`:

- `_MOS_POOL_TOOLS` — the 5 mos_* tools internal roles routinely use.
- `_EACN3_READONLY_TOOLS` — non-destructive EACN3 reads + writes that do
  not drain event queues (`submit_bid`, `submit_result`, `reject_task`,
  `create_subtask`, etc.).
- `_INTERNAL_ROLE_EACN_TOOLS` — the combination; the default EACN surface
  for every internal work role.

**3.1.5 — common SYSTEM.md contract**

Wake window protocol rewritten:

- Main loop calls `mos_await_events(..., timeout_seconds=60)` — corrected
  from the previous wrong `120` (EACN3's actual cap is 60).
- **Mandatory "ultrathink / plan-before-act"** — every event gets a 3-6
  line plan before the agent operates.
- After each event the agent calls `mos_ack_clear(port, role, [event_id])`
  to keep the pending inbox in sync during normal operation.
- New §"Pending-inbox recovery (crash replay)" describes how to handle an
  init-prompt block titled "Pending from previous wake" (verify via
  `eacn3_get_task` / `eacn3_get_messages` first, then ack either way).

Shared `eacn-network-collaboration` skill rewritten to match.

**3.1.6 — remaining roles**

Writer / Experimenter / Reviewer / Ethics / Expert all migrated to
`_INTERNAL_ROLE_EACN_TOOLS`. Noter received a narrower subset
(`mos_await_events`, `mos_send_message`, `mos_ack_clear`,
`mos_pending_read` plus its non-destructive eacn3 reads) — no
`mos_create_task` because Noter is not part of the task-market.

Writer and Expert SYSTEM.md §Collaboration rules updated. Noter
SYSTEM.md §Can-do reworked for mos_*-on-own-queue + non-destructive
reads on other queues.

**3.1.7 — Gru SYSTEM.md**

Gru's §EACN-only communication rewritten to document the two scopes:

- **MinionsOS-internal** (projects Gru manages) → MOS Agent Pool. Main
  wake loop uses `mos_await_events(port, "gru", gru_agent_id, 60)`.
- **Global EACN3** (other operators' servers) → raw `eacn3_*`.

`gru_inbox_poll` demoted from "main activation path" to "legacy / debug
adapter". The tool is still registered so operators can use it for
recovery; the main loop no longer depends on it.

Updated everywhere Gru previously said `project_eacn_send_message` /
`project_eacn_create_task` to say `mos_send_message` / `mos_create_task`.

`test_gru_system_invariants.py` was updated to pin the new contract
(assertions now check `mos_*` presence and the Global-vs-internal
distinction, and one assertion was made line-wrap tolerant).

### 3.8 Residual cleanup commit

- `role.py:_format_event_message` preamble's `response_tools` text updated
  so Gru and non-Gru roles see the correct tool vocabulary in every wake
  init message.
- Two role SYSTEM.md files (Writer, Expert) had stale generic
  `Use eacn3_*` lines; now match the new contract.

---

## 4. Your two earlier concerns — status

### Concern A: "Noter can wreck other roles' EACN3 queues"

**Fixed at the whitelist layer for Claude host.** Noter's whitelist no
longer includes `eacn3_get_events` / `eacn3_await_events` / `eacn3_next`.
Claude's `--allowed-tools` enforces this physically. Noter drains only
its own queue (via `mos_await_events` with its own `agent_id`).

**Codex host: prompt-level only.** The shared EACN3 MCP proxy
(`minions/tools/eacn3_mcp_proxy.py`) still uses a single per-profile
whitelist (`CODEX_CORE_TOOL_NAMES`) rather than per-role filtering. A
malicious or confused Codex-side Noter could physically call the drain
tools. It is forbidden by Noter's SYSTEM.md, but not by the tool
advertisement. **This is a known gap filed for a follow-up batch.**

### Concern B: "Gru's outgoing messages get eaten by Inbox"

**Diagnosis changed during the session.** Root cause is not the inbox
adapter — `project_eacn_send_message` / `_post_message_raw` POST directly
to EACN3 HTTP without going through any MinionsOS buffer. The real issue
is that `_post_message_raw` sends **empty `server_id` and `network_id`**
in the three-layer addressing payload. For pure project-local messages
that's fine; for cross-node (you on one IP, peer on another, both on the
same EACN3 Network server) that leaves the message sitting in your local
backend store addressed to an agent who isn't polling locally.

**Not fixed in this session.** The fix belongs inside
`minions/lifecycle/eacn_client._post_message_raw` (look up target
AgentCard and fill in `server_id` / `network_id` before POSTing). I
intentionally routed Coder / Writer / etc. through `mos_send_message`
which delegates to `eacn_client.send_message` so that when the fix lands
it benefits every internal role automatically. **Listed as a follow-up.**

---

## 5. Known follow-ups (not in this session)

1. **Per-role Codex EACN3 proxy filtering.** Let
   `minions/tools/eacn3_mcp_proxy.py` read `MINIONS_ROLE_NAME` env and
   call `resolve_whitelist` so Codex hosts enforce the same tool surface
   Claude hosts enforce. Without this, Codex-side Noter cannot be
   prevented from calling `eacn3_get_events` at the advertisement layer.

2. **`_post_message_raw` three-layer addressing.** Populate `server_id`
   and `network_id` in the payload by resolving the target AgentCard.
   This fixes cross-node Gru → remote-agent delivery. All internal roles
   already route through the MOS Agent Pool which calls `eacn_client` so
   they will benefit transparently.

3. **Global vs internal tool naming in `project_eacn_*`.** The wrappers
   `project_eacn_send_message` and `project_eacn_create_task` still
   exist as MCP tools; they duplicate `mos_send_message` /
   `mos_create_task`. Candidate for deprecation + removal in a later
   cleanup once call sites are audited.

4. **Spread the inbox-ACK shim to Gru**. Gru still uses `gru_inbox_poll`
   as a retained debug path but its primary wake loop uses
   `mos_await_events` (same shim as other roles). If you later decide to
   remove `gru_inbox_poll` entirely, that's a small single-commit batch.

---

## 6. Test surface

- **Unit:** 397 tests (up from 371 at session start; +18 for mos_pool, +8
  for pending injection).
- **Smoke (viz_lifecycle.py):** 4/4 green.
- **Smoke (script-style):** codex_project_collaboration, project_eacn_network,
  lifecycle — import-clean.
- **Test isolation hardening:** new autouse fixtures in
  `tests/conftest.py` prevent tests from polluting `/Users/mjm/project_*`
  and the live MinionsOS repo's branch list. A pre-existing leak was
  discovered and fixed during C2-step1.

---

## 7. Files changed this session

```
 AGENTS.md                                                |   3 -
 CLAUDE.md ... (unchanged)
 docs/rust_proposal/minionsos-proposal.md              |  16 +-
 minions/CLAUDE.md                                        |   4 -
 minions/config/__init__.py                               | 119 +++++-
 minions/gru/loop.py                                      |  24 ++
 minions/lifecycle/agent_host.py                          |  53 +--
 minions/lifecycle/git_utils.py                           |  70 ++++
 minions/lifecycle/hooks.py                               |  33 +-
 minions/lifecycle/mos_pool.py                            | 342 ++++++++++++++++
 minions/lifecycle/project.py                             | ~150
 minions/lifecycle/role.py                                | 109 ++++-
 minions/lifecycle/session_archive.py                     | 203 ++++++++++
 minions/lifecycle/wake_signals.py                        |  62 +++
 minions/lifecycle/wakeup.py                              |  45 +-
 minions/paths.py                                         |  66 +++-
 minions/roles/SYSTEM.md                                  | 115 +++++--
 minions/roles/coder/SYSTEM.md                            |   7 +-
 minions/roles/common/skills/eacn-network-collaboration.md|  47 +-
 minions/roles/expert/SYSTEM.md                           |   7 +-
 minions/roles/gru/SYSTEM.md                              | 135 +++++--
 minions/roles/noter/SYSTEM.md                            |  31 +-
 minions/roles/noter/skills/role-session-diff-timeline.md |  71 ++++
 minions/roles/writer/SYSTEM.md                           |   7 +-
 minions/tools/mcp_server.py                              | 159 +++++++++
 tests/conftest.py                                        |  50 ++-
 tests/smoke/*                                            |   4 +-
 tests/unit/test_agent_host.py                            |  12 +-
 tests/unit/test_ethics_role.py                           |   7 +-
 tests/unit/test_gru_inbox.py                             |  62 +-
 tests/unit/test_gru_system_invariants.py                 |  43 +-
 tests/unit/test_mcp_profiles.py                          |   7 +-
 tests/unit/test_mos_pool.py                              | 349 ++++++++++++++
 tests/unit/test_project_checkpoint.py                    |   ~
 tests/unit/test_project_create_extras.py                 |   2 +-
 tests/unit/test_role_crash_detection.py                  |   2 +-
 tests/unit/test_role_skill_prompt.py                     |  13 +-
 tests/unit/test_scratchpad.py                            |  ~
 tests/unit/test_session_archive.py                       | 160 ++++++++
 tests/unit/test_team_bug_report_2026_04_24.py            |   ~
 tests/unit/test_wakeup.py                                |  44 +-
 tests/unit/test_wakeup_phase2.py                         |  50 +-
 + other/rust-archive/ (moved from top level)
 + minions/lifecycle/git_utils.py, mos_pool.py, session_archive.py (new)
 + minions/roles/noter/skills/role-session-diff-timeline.md (new)
 + tests/unit/test_mos_pool.py, test_session_archive.py (new)
```

---

## 8. Operational notes for next boot

- Existing old-layout projects (if any appear) will auto-migrate on
  Gru startup via `migrate_legacy_scratchpads(port)`. The migration is
  idempotent and best-effort.
- If a wake dies mid-flight leaving a non-empty
  `branches/<role>/.minionsos/inbox/pending.jsonl`, the next wake's init
  prompt will surface the leftover events in a `[Pending from previous
  wake]` block (implemented in `role.py:_format_event_message` via
  `_read_pending_safely` + `_summarize_pending_entry`). The agent then
  follows the common SYSTEM.md "Pending-inbox recovery" procedure:
  verify relevance via non-destructive `eacn3_get_task` /
  `eacn3_get_messages`, handle if still relevant, and call
  `mos_ack_clear(port, role, [event_id])` to retire it from the inbox.
  Normal wake cycles leave `pending.jsonl` empty, so the block is
  omitted entirely — zero overhead on the happy path.
- No runtime processes or project_* directories exist on disk at the
  end of this session.

---

**End of report.** Commit hash at session end: `d8767a2`.
