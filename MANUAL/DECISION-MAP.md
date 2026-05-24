# DECISION MAP — "I want to do X" → tool

Read top to bottom; first matching row wins.

## Wake / read state

| Goal | Tool | Chapter |
|---|---|---|
| I just woke up — what should I read first? | `mos_draft_summary` then `mos_book_hot_get` | 04, 05 |
| Drain new EACN events, blocking until something happens | `mos_await_events` | 02 |
| (Noter only) Wait the timer | `mos_noter_wait` | 11 |
| Peek at events without consuming | `mos_get_events` | 02 |
| Count unread + see suggested action | `mos_unread_summary` | 02 |
| Find a Draft node by type / role / substring | `mos_draft_query` | 04 |
| Find a Book page by topic | `mos_book_query` | 05 |
| Look up which agents are on this project EACN | `eacn3_list_agents` | 02 |
| Look up open tasks | `eacn3_list_open_tasks` | 02 |
| Drill into a subagent's raw transcript | `mos_reel_get(ref)` | 06 |

## Communicate

| Goal | Tool | Chapter |
|---|---|---|
| DM another role | `eacn3_send_message` | 02 |
| Open a broadcast task | `eacn3_create_task(visibility="broadcast")` | 02 |
| Open a directed task to one role | `eacn3_create_task(targets=[...])` | 02 |
| Bid on a task | `eacn3_submit_bid` | 02 |
| Submit a result | `eacn3_submit_result` | 02 |
| Ask Gru to relay something cross-project | `mos_project_bridge` (Gru only — request via DM) | 13 |
| Raise a phase-transition vote | `mos_signboard_set` | 01 |

## Work the data

| Goal | Tool | Chapter |
|---|---|---|
| Run one experiment now | `mos_exp_run` | 03 |
| Submit a sweep | `mos_exp_queue_submit` | 03 |
| Reap finished cells, dispatch next | `mos_exp_queue_reconcile` | 03 |
| See queue state | `mos_exp_queue_status` | 03 |
| Reserve GPUs for the queue | `mos_exp_gpu_pool_set` | 03 |
| Ship an artifact to another role | `mos_publish_to_shared` | 07 |

## Persist knowledge

| Goal | Tool | Chapter |
|---|---|---|
| Append a node to Draft | `mos_draft_append` | 04 |
| Mark a Draft node verified / refuted | `mos_draft_annotate` | 04 |
| Promote a settled artifact into Book | `mos_book_ingest` (Noter) | 05 |
| Cross-link Book pages into a synthesis | `mos_book_save_synthesis` (Noter) | 05 |
| Resolve a contradiction Ethics flagged | `mos_book_resolve_contradiction` | 05 |
| Refresh `book/hot.md` | `mos_book_hot_update` (Noter) | 05 |
| Promote verified Draft → durable Book | `mos_book_promote_verified` (Noter) | 05 |

## Find papers

| Goal | Tool | Chapter |
|---|---|---|
| One source | `mos_search_arxiv` (etc.) | 08 |
| All sources at once | `mos_search_papers_federated` | 08 |
| Read PDF text from arXiv id | `mos_download_arxiv` then `mos_read_arxiv_paper` | 08 |

## Render / inspect images

| Goal | Tool | Chapter |
|---|---|---|
| Render a LaTeX/HTML/MD snippet | `mos_visual_render` | 10 |
| Get a vision-model description | `mos_visual_inspect` | 10 |
| Render + inspect + verdict | `mos_visual_check` | 10 |

## Submit + close out

| Goal | Tool | Chapter |
|---|---|---|
| Surface a deliverable to Gru | EACN message → Gru calls `mos_submit` | 09 |
| Run a peer-review round | (Gru) `mos_review_run` | 09 |
| Score a deliverable | (Gru) `mos_evaluate` | 09 |
| Pre-grader audit on an answer | (Gru) `mos_adjudicate` | 09 |

## When something is wrong

| Goal | Tool | Chapter |
|---|---|---|
| File a structured P0/P1/P2 issue | `mos_issue_report` | 12 |
| Tool denied — figure out why | Read `12-issues-debug.md` § "tool denied" | 12 |
| Subagent failed — recover its trace | `mos_reel_get(ref)` then `mos_reel_window` | 06 |
| Need to reset to a clean wake | `mos_reset_context` | 11 |
| Context too big | `mos_compact_context` | 11 |

## Lifecycle (Gru only)

| Goal | Tool |
|---|---|
| New project | `mos_project_create` |
| Spawn a writer / ethics | `mos_spawn_role(role="writer")` |
| Spawn a domain expert | `mos_spawn_expert(name="<slug>")` |
| Sleep / wake / kill a project | `mos_project_dormant` / `_revive` / `_kill` |
| Move phase | `mos_project_set_phase` |
| Recommend role evolution | `mos_role_evolve_evaluate` (read-only) |
