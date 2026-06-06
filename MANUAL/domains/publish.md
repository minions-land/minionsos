---
id: domain-publish
kind: domain
domain: publish
auth: ['*']
source: minions/tools/mcp/publish_tools.py:15
since: stable
keywords: [publish, share, handoff, cross-role, commit]
related: [mos_publish_to_shared]
status: stable
---

# Domain: Publish + handoffs

Cross-role writes have **exactly one legal path**: `mos_publish_to_shared`.
Anything else (`cp`, `mv`, `git commit` into another role's branch) corrupts state.

## Single tool

```bash
lookup.py --id mos_publish_to_shared
```

## Whitelist (which dst_subpath your role can write)

| Role | Allowed `dst_subpath` top-level |
|---|---|
| `gru` | `*` |
| `expert*` | `handoffs`, `governance` |
| `ethics` | `ethics`, `handoffs`, `governance` |

**Reserved** (rejected for everyone except their owner tool):
- `reviews/` → `mos_review_run` only
- `submissions/` → `mos_submit` only
- `draft/draft.json` → `mos_draft_commit_shared` only

## Rules

- `src_path` MUST be absolute.
- `dst_subpath` does NOT include the `branches/main/` prefix.
- Multiple parallel publishes serialise on `state/shared.lock` — batch when possible.
- Cross-role READ is just the watchdog's git pull. Don't try to read another
  role's branch directly.
