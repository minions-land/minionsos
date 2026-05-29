# Error Reference

All public exception classes exported from `minions/errors.py`.

---

## MinionsError

**Parent**: `Exception`  
**Raised when**: Base class — not raised directly. Catch this to handle any MinionsOS error.

---

## ConfigError

**Parent**: `MinionsError`  
**Raised when**: `gru.yaml` fails to load or a required field is missing/invalid.  
**Example**: Missing `eacn_host` field; unreadable config path.

---

## StateError

**Parent**: `MinionsError`  
**Raised when**: Atomic state-store read or write fails (`projects.json`, role registry).  
**Example**: `StateStore.write()` cannot rename the `.tmp` file into place (disk full, permission denied).

---

## PortError

**Parent**: `MinionsError`  
**Raised when**: Port allocator cannot find a free port, or a port pre-check detects the target port is already bound.  
**Example**: All ports in the configured allocator range are occupied; project port pre-check fails after retry budget exhausted.

---

## ProjectError

**Parent**: `MinionsError`  
**Raised when**: Project lifecycle operation fails — `project_create`, `project_close`, `project_dormant`, `project_revive`.  
**Example**: git worktree creation fails because the target path already exists; project metadata write rejected.

---

## RoleError

**Parent**: `MinionsError`  
**Raised when**: A role spawn or dismiss operation fails.  
**Example**: `register_role` cannot create the role workspace directory; `dismiss_role` cannot find the named role in the registry.

---

## AlreadyActive

**Parent**: `RoleError`  
**Raised when**: `register_role` / `register_expert` is called for a slug that is already registered and active in the project.  
**Example**: Gru calls `mos_spawn_role(role="coder")` while a Coder process is already running on the same project port.

---

## BackendError

**Parent**: `MinionsError`  
**Raised when**: The EACN3 backend subprocess fails to start, does not become healthy within the timeout, or crashes unexpectedly.  
**Example**: The `eacn3` binary exits non-zero at startup; health probe returns non-200 after the retry window.

---

## ProjectBridgeError

**Parent**: `MinionsError`  
**Raised when**: `mos_project_bridge` cannot deliver a cross-project message — target project not found, target backend unreachable, or EACN send fails.  
**Example**: Gru relays an event to project port `9042`, but that project has been closed.

---

## ExperimentError

**Parent**: `MinionsError`  
**Raised when**: An experiment execution step fails — SSH connection error, remote script non-zero exit, GPU allocation failure, or result-bundle write error.  
**Example**: `mos_exp_run` SSH session drops mid-run; remote GPU reports OOM and exits with status 1.

---

## CircuitBreakError

**Parent**: `ExperimentError`  
**Raised when**: Three consecutive failures of the same script hash trip the experiment circuit breaker; further runs of that script are blocked until Coder explicitly resets the breaker.  
**Example**: A training script exits non-zero three times in a row; the fourth call raises `CircuitBreakError` immediately without launching.

---

## PermissionError

**Parent**: `MinionsError`  
**Raised when**: A Role attempts to call a tool outside its authorized boundary — caught by server-side authorization in `minions/tools/mcp_server.py` or by `resolve_allowed_tools`.  
**Example**: A Coder subagent attempts to call `mos_project_create`; Ethics attempts to call `mos_exp_run`.  
**Note**: This class shadows the Python built-in `PermissionError` within the `minions` package namespace. Import as `from minions.errors import PermissionError` and qualify carefully when mixing with `builtins.PermissionError`.

---

## ReelError

**Parent**: `MinionsError`  
**Raised when**: A Reel (L0 raw transcripts) operation cannot complete — malformed `<role>/<session>/<id>` ref, missing `MINIONS_PROJECT_PORT`, ref not found in the role's `reel-index.jsonl`, or unreadable `claude_jsonl` transcript file.  
**Example**: `mos_reel_get("writer/sess-7/missing")` looks up an entry not present in the writer reel index.  
**Note**: Cross-role authorization failures still raise `PermissionError`, not `ReelError`.

---

## DraftError

**Parent**: `MinionsError`  
**Raised when**: A Draft (L1 process graph) operation cannot complete — out-of-range confidence, malformed edge strength, missing `MINIONS_PROJECT_PORT`, or a node id referenced by `mos_draft_annotate` / `mos_draft_path` does not exist.  
**Example**: `mos_draft_annotate(node_id="H-999")` when no such node has been appended; `mos_draft_append` called with `confidence=1.5`.

---

## BookError

**Parent**: `MinionsError`  
**Raised when**: A Book (L2 durable product memory) operation cannot complete — page-kind violation, missing required fields (claim / question / evidence_review), source path outside the project workspace, ratify call from a non-Ethics role, or contradiction page lookup miss.  
**Example**: `mos_book_ratify(slug="X", ...)` invoked with `ratifier_role="coder"`; `mos_book_dead_end(claim="", evidence="...")`.  
**Note**: This class is also re-exported from `minions.tools.book` for backward compatibility with existing `pytest.raises(BookError)` call sites.

---

## Class hierarchy

```
Exception
└── MinionsError
    ├── ConfigError
    ├── StateError
    ├── PortError
    ├── ProjectError
    ├── RoleError
    │   └── AlreadyActive
    ├── BackendError
    ├── ProjectBridgeError
    ├── ExperimentError
    │   └── CircuitBreakError
    ├── PermissionError
    ├── ReelError
    ├── DraftError
    └── BookError
```

*Source of truth: `minions/errors.py`. Keep this reference in sync when adding new exception classes.*

