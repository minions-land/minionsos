# MinionsOS Module Path Index

**Generated:** 2026-06-04
**Last updated:** 2026-06-04
**Purpose:** Document the main runtime module locations, dependency boundaries,
and high-traffic callers.

This file is an implementation map, not the public product overview. For the
repository-wide Markdown asset map, see `MARKDOWN_INDEX.md`.

## Executive Summary

Runtime code is organised around current public entry modules and focused
support modules. Public callers should use the entry modules listed below;
supporting modules are implementation boundaries.

## Book L2 Memory Modules

### Facade

- `minions/tools/book.py` - public Book API entry point.

### Supporting modules

| Module | Role |
|---|---|
| `minions/tools/book_utils.py` | Basic utilities: quoting, timestamps, component validation, atomic writes. |
| `minions/tools/book_helpers.py` | Internal path, frontmatter, token, and injection helpers. |
| `minions/tools/book_index.py` | Index and log rendering helpers. |
| `minions/tools/book_contradiction.py` | Claim-candidate and contradiction detection. |
| `minions/tools/book_query.py` | BM25 search and `BookQueryResult`. |
| `minions/tools/book_special.py` | Open-question and dead-end pages. |
| `minions/tools/book_lint.py` | Book integrity checks. |
| `minions/tools/book_audit.py` | Audit walk and contradiction-resolution tools. |
| `minions/tools/book_promote.py` | Verified-knowledge promotion and Ethics ratification. |
| `minions/tools/book_crystallize.py` | Session crystallization and synthesis saving. |
| `minions/tools/book_ingest.py` | Source ingestion and batch ingestion. |

### Public API

Import from `minions.tools.book`:

```python
from minions.tools.book import (
    mos_book_ingest,
    mos_book_ingest_batch,
    mos_book_query,
    mos_book_promote_verified,
    mos_book_ratify,
    mos_book_crystallize_session,
    mos_book_save_synthesis,
    mos_book_open_question,
    mos_book_dead_end,
    mos_book_audit_walk,
    mos_book_resolve_contradiction,
    mos_book_lint,
)
```

### Main callers

- `minions/tools/draft.py` calls `mos_book_ingest`.
- `minions/tools/mcp/memory_tools.py` wraps the memory tools for MCP.
- Unit and integration tests cover Book, Draft/Reel integration, memory
  provenance, contradiction handling, and Ethics audit chains.

## Draft L1 Memory Modules

### Facade

- `minions/tools/draft.py` - main Draft API entry point.

### Supporting modules

| Module | Role |
|---|---|
| `minions/tools/draft_nodes.py` | Node append and node mutation operations. |
| `minions/tools/draft_edges.py` | Edge append and graph relationship operations. |
| `minions/tools/draft_query.py` | Draft querying and traversal. |
| `minions/tools/draft_decay.py` | Confidence-decay computation. |
| `minions/tools/draft_helpers.py` | Draft loading, saving, and shared helpers. |

### Public API

```python
from minions.tools.draft import (
    mos_draft_append,
    mos_draft_view,
    mos_draft_annotate,
    mos_draft_commit_shared,
)
```

## Experiment Scheduler Modules

### Facade

- `minions/tools/experiment_scheduler.py` - MCP-facing scheduler entry point.

### Supporting modules

| Module | Role |
|---|---|
| `minions/tools/scheduler_queue.py` | Queue submission, status queries, pending and blocked state. |
| `minions/tools/scheduler_gpu.py` | GPU slot allocation, eviction, drain, and pool state. |
| `minions/tools/scheduler_packing.py` | Candidate selection and multi-GPU placement. |
| `minions/tools/scheduler_helpers.py` | Constants, JSON helpers, IDs, and anomaly detection. |

### Public API

```python
from minions.tools.experiment_scheduler import (
    mos_exp_queue_submit,
    mos_exp_queue_plan,
    mos_exp_queue_status,
    mos_exp_gpu_pool_set,
    mos_exp_gpu_pool_get,
)
```

## Project Lifecycle Modules

### Lifecycle Entry Point

- `minions/lifecycle/project.py` - lifecycle entry point used by project commands.

### Supporting modules

| Module | Role |
|---|---|
| `minions/lifecycle/project_backend.py` | EACN3 backend process management, health checks, PID handling, Gru registration. |
| `minions/lifecycle/project_create.py` | Project creation, role bootstrap, Expert bootstrap, Draft seed nodes. |
| `minions/lifecycle/project_lifecycle.py` | Dormant, close, kill, revive, and phase lifecycle operations. |
| `minions/lifecycle/project_metadata.py` | `meta.json` read/write, extra-field preservation, `RoleEntry` validation. |
| `minions/lifecycle/project_paths.py` | Author repo resolution, per-project repo seeding, tags, directory layout. |
| `minions/lifecycle/project_worktree.py` | Git worktree creation/removal and Claude settings seeding. |

### Public API

```python
from minions.lifecycle.project import (
    mos_project_create,
    mos_project_close,
    mos_project_dormant,
    mos_project_revive,
    mos_project_kill,
    mos_project_list,
    mos_project_set_phase,
    mos_project_checkpoint_workspace,
    mos_project_bridge,
)
```

## Import Conventions

Use facade imports for application code:

```python
from minions.tools.book import mos_book_ingest
from minions.tools.draft import mos_draft_view
from minions.lifecycle.project import mos_project_create
```

Package-level imports remain acceptable when an existing caller already uses
them:

```python
from minions.tools import book
book.mos_book_ingest(...)
```

Direct submodule imports are reserved for focused tests or internal helpers:

```python
from minions.tools.book_helpers import _book_root, _parse_frontmatter
from minions.tools.draft_helpers import _load_draft
```

## Dependency Map

### Book

```text
External:
  minions.paths
  minions.tools._returns
  minions.errors
  minions.config
  minions.tools.publish

Internal:
  book.py
    -> book_utils
    -> book_helpers
    -> book_index
    -> book_contradiction
    -> book_query -> book_helpers
    -> book_special -> book_helpers, book_index
    -> book_lint -> book_helpers
    -> book_audit -> book_helpers
    -> book_promote -> book_helpers, book_index
    -> book_crystallize -> book_helpers
    -> book_ingest -> book_helpers, book_index, book_contradiction
```

### Draft

```text
External:
  minions.paths
  minions.errors
  minions.tools.book

Internal:
  draft.py
    -> draft_nodes
    -> draft_edges
    -> draft_query -> draft_helpers
    -> draft_decay -> draft_helpers
    -> draft_helpers
```

### Scheduler

```text
External:
  minions.paths
  minions.config
  sqlite3

Internal:
  experiment_scheduler.py
    -> scheduler_queue -> scheduler_helpers
    -> scheduler_gpu -> scheduler_helpers
    -> scheduler_packing -> scheduler_helpers
    -> scheduler_helpers
```

### Project Lifecycle

```text
External:
  minions.config
  minions.paths
  minions.lifecycle.*
  git

Internal:
  project.py
    -> project_backend
    -> project_create -> project_backend, project_paths, project_worktree
    -> project_lifecycle -> project_backend, project_metadata
    -> project_metadata
    -> project_paths
    -> project_worktree -> project_paths
```

## Health Notes

- Keep public callers pointed at the facade modules unless a direct helper import
  is intentional and test-scoped.
- Keep submodules small enough to review independently. The largest extracted
  module after this pass is under 800 lines.
- When moving new code out of a facade, update this file and add focused tests
  for the extracted behavior.
