---
id: mos_publish_to_shared
kind: tool
domain: publish
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/publish_tools.py:15
since: stable
keywords: [publish, share, handoff, cross, role, commit, lock, shared]
related: [domain-publish, mos_draft_commit_shared, mos_submit, mos_review_run]
status: stable
---

# mos_publish_to_shared

**One line:** The only legal cross-role write — locks `state/shared.lock`, copies, commits.

## Signature
```py
mos_publish_to_shared(
  role: str,            # MUST match your env role
  src_path: str,        # MUST be absolute, inside YOUR branch
  dst_subpath: str,     # path UNDER branches/shared/, no leading "branches/shared/"
  commit_message: str,
) -> { dst_path, shared_commit_sha, files_changed }
```

## Whitelist (top-level dir of `dst_subpath`)
| Role | Allowed |
|---|---|
| `gru` | `*` |
| `noter` | `notes`, `draft`, `handoffs`, `book` |
| `coder` | `exp`, `handoffs`, `governance` |
| `writer` | `handoffs`, `governance` |
| `expert*` | `handoffs`, `governance` |
| `ethics` | `ethics`, `handoffs`, `governance` |

Reserved (rejected for everyone except their owner tool):
- `reviews/` → `mos_review_run` only
- `submissions/` → `mos_submit` only
- `draft/draft.json` → `mos_draft_commit_shared` only

## Real example (project_37596)
```py
mos_publish_to_shared(
  role="coder",
  src_path="/abs/branches/coder/exp/p3-width-falsifier/result.json",
  dst_subpath="exp/p3-width-falsifier/result.json",
  commit_message="coder: p3-width-falsifier — c_grok ∝ h FAILS at 52% MARE",
)
```

## Pitfalls
- `src_path` MUST be absolute. Relative paths break flock-protected copy.
- `dst_subpath` does NOT include `branches/shared/`.
- Parallel publishes serialise on the flock — batch when possible.
- Cross-role READ: let watchdog's git pull surface it. Do NOT read another role's
  `branches/<other-role>/` directly.
- Never `cp` / `mv` between branches — corrupts git state, causes merge conflicts
  on next pull (project_37596 hit this; ~1 h of conflict noise).
