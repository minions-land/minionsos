# INDEX — every MCP tool, one line each

`✓` = role-callable. `Gru` = Gru-only. `Noter` = Noter-only. `+auth` = restricted by profile/whitelist.
Names are exact MCP tool names. Prefix is `mcp__minionsos__` unless noted.

## Lifecycle (chapter 01)

| Tool | Auth | One line |
|---|---|---|
| `mos_project_create` | Gru | Spawn a new project on a free port. |
| `mos_project_list` | Gru | List all known projects (active+dormant+closed). |
| `mos_project_dormant` | Gru | Sleep a project; keeps git + EACN state. |
| `mos_project_revive` | Gru | Wake a dormant project; respawns roles. |
| `mos_project_close` | Gru | Permanently retire a project. |
| `mos_project_kill` | Gru | Hard-kill a project process tree. |
| `mos_project_set_phase` | Gru | Move project between exploration / experiment / writing / review. |
| `mos_project_checkpoint_workspace` | Gru | Snapshot all role worktrees to a tag. |
| `mos_spawn_role` | Gru | Spawn a fixed-name role (writer, ethics, ...). |
| `mos_spawn_expert` | Gru | Spawn a domain Expert with a slug name. |
| `mos_dismiss_role` | Gru | Retire a role; preserves branch/audit. |
| `mos_list_roles` | Gru | List active roles for a project. |
| `mos_kill_role` | Gru | Hard-kill a role tmux session. |
| `mos_attach_role` | Gru | Get tmux attach command for a role. |
| `mos_list_workflow_plugins` | Gru | List external workflow plugins available to spawn as Experts. |

## EACN3 comms (chapter 02)

| Tool | Auth | One line |
|---|---|---|
| `mos_await_events` | EACN roles | **Default wake driver.** Long-poll, drains, idle-checks. |
| `mos_get_events` | +auth | One-shot peek at events without consuming. |
| `mos_unread_summary` | EACN roles | Count unread + suggested-next-tool. |
| `eacn3_send_message` | EACN roles | DM another agent on the same project EACN. |
| `eacn3_create_task` | EACN roles | Open a broadcast or directed task. |
| `eacn3_submit_bid` | EACN roles | Bid on an open task. |
| `eacn3_submit_result` | EACN roles | Post a task result. |
| `eacn3_get_messages` / `eacn3_get_task` / `eacn3_get_task_results` | EACN roles | Read history. |
| `eacn3_list_open_tasks` / `eacn3_list_tasks` / `eacn3_list_agents` | EACN roles | Browse. |
| `eacn3_close_task` / `eacn3_reject_task` / `eacn3_select_result` | task owner | Close out. |
| `eacn3_heartbeat` | EACN roles | Liveness ping (auto). |
| `eacn3_*` (rest) | varies | See `02-eacn3-comms.md` § "the long tail". |

## Experiments (chapter 03)

| Tool | Auth | One line |
|---|---|---|
| `mos_exp_run` | Coder | Run a one-off experiment with a long timeout. |
| `mos_exp_status` / `mos_exp_tail` / `mos_exp_get` / `mos_exp_list` | Coder | Inspect an experiment. |
| `mos_exp_wait` | Coder | Block until an experiment ends. |
| `mos_exp_kill` | Coder | Cancel a running experiment. |
| `mos_exp_put` | Coder | Stage an asset into the project. |
| `mos_query_gpus` | Coder | List local GPUs. |
| `mos_exp_queue_submit` | Coder | Submit cells into the project sweep queue. |
| `mos_exp_queue_status` / `mos_exp_queue_plan` | Coder | Inspect queue. |
| `mos_exp_queue_reconcile` | Coder | Reap finished cells, dispatch next. **Watch retry budget.** |
| `mos_exp_gpu_pool_set` / `mos_exp_gpu_pool_get` | Coder | Reserve/release GPUs for the queue. |

## Memory — Draft / Book / Shelf / Reel (chapters 04 – 06)

| Tool | Auth | One line |
|---|---|---|
| `mos_draft_summary` | EACN roles | First call after wake; lists recent + pending_plan. |
| `mos_draft_query` | EACN roles | Filter Draft nodes (type / role / contains / related). |
| `mos_draft_append` | EACN roles | Add nodes/edges. |
| `mos_draft_annotate` | EACN roles | Update support_status / evidence_tag / metadata. |
| `mos_draft_path` | EACN roles | Trace ancestry to root. |
| `mos_draft_decay_compute` | Noter / Gru | Score nodes for retirement. |
| `mos_draft_commit_shared` | Noter / Gru | Flush Draft to shared branch (timer-driven). |
| `mos_book_query` / `mos_book_hot_get` | EACN roles | Read durable knowledge. |
| `mos_book_ingest` / `mos_book_ingest_batch` | Noter | Promote a source artifact into Book. |
| `mos_book_save_synthesis` | Noter | Cross-link sources into a synthesis page. |
| `mos_book_audit_walk` | Ethics / Noter | Find isolated/bridge pages. |
| `mos_book_resolve_contradiction` | Ethics | Verdict on a contradiction. |
| `mos_book_lint` | Noter | Audit Book structure. |
| `mos_book_promote_verified` | Noter | Promote Draft → Book once verified. |
| `mos_book_crystallize_session` | Noter | Compact a session's Draft activity into a Book page. |
| `mos_book_hot_update` | Noter | Re-render `book/hot.md`. |
| `mos_shelf_register` | Gru | Build per-project shelf graph from Book + handoffs. |
| `mos_shelf_query` / `mos_shelf_shared_concepts` | EACN roles | Structural search. |
| `mos_reel_get` / `mos_reel_window` | EACN roles (own reel) | Drill into raw subagent transcripts. |

## Publish + handoffs (chapter 07)

| Tool | Auth | One line |
|---|---|---|
| `mos_publish_to_shared` | EACN roles | **The only legal cross-role write.** Locks `state/shared.lock`, copies, commits. |

## Paper search (chapter 08)

| Tool | Auth | One line |
|---|---|---|
| `mos_search_arxiv` / `mos_download_arxiv` / `mos_read_arxiv_paper` / `mos_resolve_arxiv_ids` | Writer (+ on request) | arXiv. |
| `mos_search_pubmed` / `mos_download_pubmed` / `mos_read_pubmed_paper` | Writer | PubMed. |
| `mos_search_biorxiv` / `mos_download_biorxiv` / `mos_read_biorxiv_paper` | Writer | bioRxiv. |
| `mos_search_medrxiv` / `mos_download_medrxiv` / `mos_read_medrxiv_paper` | Writer | medRxiv. |
| `mos_search_google_scholar` / `mos_search_semantic` | Writer | Scholar / Semantic Scholar. |
| `mos_search_papers_federated` | Writer | Fan-out across all sources. |

## Deliverables + review (chapter 09)

| Tool | Auth | One line |
|---|---|---|
| `mos_submit` | Gru | Persist a deliverable under `branches/shared/submissions/`. |
| `mos_evaluate` | Gru | Run profile-defined evaluation strategy. |
| `mos_adjudicate` | Gru | Pre-evaluation answer audit (depth=single / panel). |
| `mos_review_run` | Gru | Spawn one peer-review round (Pass A/B/C). |

## Visual render (chapter 10)

| Tool | Auth | One line |
|---|---|---|
| `mos_visual_render` | EACN roles non-Noter | LaTeX/HTML/MD → image. |
| `mos_visual_inspect` | EACN roles non-Noter | Vision-model report on an image. |
| `mos_visual_check` | EACN roles non-Noter | Render + inspect + verdict in one call. |

## Runtime control (chapter 11)

| Tool | Auth | One line |
|---|---|---|
| `mos_noter_wait` | Noter | Timer-based wake (3 min default). Noter's loop. |
| `mos_compact_context` | EACN roles | Ask harness to compact and resume. |
| `mos_reset_context` | EACN roles | Drop a marker so next wake is a fresh boot. |
| `mos_start_monitor` | Gru | Start the project Gru monitor loop. |

## Issues + debug (chapter 12)

| Tool | Auth | One line |
|---|---|---|
| `mos_issue_report` | All roles (universal) | File a structured P0/P1/P2 issue. |

## Bridge (chapter 13)

| Tool | Auth | One line |
|---|---|---|
| `mos_project_bridge` | Gru | Read another project's events / artifacts (Gru-only). |

## Role evolution (chapter 14)

| Tool | Auth | One line |
|---|---|---|
| `mos_role_evolve_evaluate` | Gru | Read-only; recommend SPLIT / MERGE / DISMISS. |
| `mos_role_split` | Gru | Realise a SPLIT. Requires `evidence_refs`. |
| `mos_role_merge` | Gru | Realise a convergence MERGE. |
| `mos_role_evolve_dismiss` | Gru | Realise a starvation DISMISS. |

## Signboard (chapter 01 § signboard)

| Tool | Auth | One line |
|---|---|---|
| `mos_signboard_set` | EACN roles | Raise a phase-transition sign. |
| `mos_signboard_read` / `mos_signboard_evaluate` | EACN roles | Read consensus. |
| `mos_signboard_consume` / `mos_signboard_reopen` | Gru | Close / reopen a sign. |

## Keepalive (cache warmth — global skill, not project-bounded)

| Tool | Auth | One line |
|---|---|---|
| `mcp__keepalive__wait_bg` | All | Block on a bg task ID; keeps prompt cache warm. |
| `mcp__keepalive__keepalive_now` | All | Force a cache touch now. |
