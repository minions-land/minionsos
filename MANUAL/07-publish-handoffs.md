# 07 — Publish + handoffs

> **L2 card.** Cross-role writes have exactly one legal path: `mos_publish_to_shared`. Anything else (cp, mv, direct git commit into another role's branch) is a bug.
> Top tool: `mos_publish_to_shared` (the only tool here).

---

## mos_publish_to_shared

```python
args:
  role: str                # the calling role; must match your env
  src_path: str            # absolute path inside YOUR branch
  dst_subpath: str         # path under branches/shared/, e.g. "exp/exp-abc/result.json"
  commit_message: str
returns: {
  dst_path: str,
  shared_commit_sha: str,
  files_changed: int,
}
```

**Behaviour.**
1. Acquires `state/shared.lock` (flock).
2. Verifies `dst_subpath`'s top-level directory is in your role's whitelist (see table below).
3. Copies file → commits on `branches/shared` with the supplied message.
4. Releases lock.

**Per-role whitelist** (from `minions/tools/publish.py:_ROLE_ALLOWED_SHARED_SUBDIRS` — overridden per profile):

| Role | Allowed `dst_subpath` top-level |
|---|---|
| `gru` | `*` (any) |
| `noter` | `notes`, `draft`, `handoffs`, `book` |
| `coder` | `exp`, `handoffs`, `governance` |
| `writer` | `handoffs`, `governance` |
| `expert*` | `handoffs`, `governance` |
| `ethics` | `ethics`, `handoffs`, `governance` |

**Reserved (rejected for everyone except their owners):**
- `reviews/` → `mos_review_run` only
- `submissions/` → `mos_submit` only (profile may grant per-role)
- `draft/draft.json` → `mos_draft_commit_shared` only

---

## Patterns

### Coder publishes an experiment bundle

```python
mos_publish_to_shared(
  role="coder",
  src_path="/abs/path/to/branches/coder/exp/p3-width-falsifier/result.json",
  dst_subpath="exp/p3-width-falsifier/result.json",
  commit_message="coder: p3-width-falsifier — c_grok ∝ h FAILS at 52% MARE",
)
```

### Coder hands off a settled experiment to Writer

```python
mos_publish_to_shared(
  role="coder",
  src_path="/abs/branches/coder/handoffs/coder-p3-width-falsifier.md",
  dst_subpath="handoffs/coder-p3-width-falsifier.md",
  commit_message="handoff: p3-width-falsifier ready for paper",
)
```

### Ethics publishes an audit

```python
mos_publish_to_shared(
  role="ethics",
  src_path="/abs/branches/ethics/audit-B-repro.md",
  dst_subpath="ethics/audit-B-repro.md",
  commit_message="ethics: audit-B reproducibility verdict",
)
```

---

## Pitfalls

- **`src_path` must be absolute.** Relative paths break the flock-protected copy.
- **Don't include leading `branches/shared/`** in `dst_subpath`; the tool prepends it.
- **Multiple parallel `mos_publish_to_shared` calls serialise** on the flock. If you have N artifacts, batch them or accept the queue.
- **Cross-role read** is just `git pull` on the shared branch, which the watchdog does automatically. Don't try to read another role's branch directly.
- **Direct write into `branches/<other-role>/`** will commit into your own worktree first (because git), and the next pull on the destination role will refuse to fast-forward. project_37596 hit this once when an expert tried to drop a memo into another expert's branch — both roles got merge-conflict noise for an hour.
