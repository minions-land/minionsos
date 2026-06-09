---
id: mos_book_ratify
kind: tool
domain: memory
auth: [ethics]
source: minions/tools/mcp/memory_tools.py:394
since: stable
keywords: [book, ratify, ethics, verify, promote, ratification]
related: [mos_book_promote_verified, mos_book_audit_walk, mos_book_query]
status: stable
---

# mos_book_ratify

**One line:** Ethics ratifies a promoted Book source page by appending a signed review and setting `ratified_by: ethics`.

## Signature
```py
mos_book_ratify(
  slug: str,              # slug of an existing book/sources/<slug>.md page
  evidence_review: str,   # Ethics review text appended verbatim as ## Ratification
  ratifier_role: str,     # must be "ethics" — server enforces this
  port: int | None,
) -> {
  slug: str,
  book_path: str,         # "book/sources/<slug>.md"
  ratified_at: str,       # ISO timestamp
  publish_result: dict,
}
```

## Authz
**Ethics only.** The server enforces `ratifier_role == "ethics"`; any other value raises `BookError`. This is the only tool that writes `ratified_by` / `ratified_at` frontmatter fields.

## What it does
1. Opens the existing `book/sources/<slug>.md` page (must already exist — typically promoted via `mos_book_promote_verified`).
2. Updates YAML frontmatter: sets `ratified_by: ethics` and `ratified_at: <iso>`.
3. Appends a `## Ratification` section containing the `evidence_review` text.
4. Commits updated page + log entry on the project main branch via `mos_publish_to_shared`.

## When to call
- After Ethics finishes a cross-role audit that vindicates a claim in the Book.
- As the terminal step in the evidence-review pipeline (ingest → promote → ratify).
- Do NOT call this on unverified pages — ratification is a permanent marker.

## Pitfalls
- Page must already exist under `book/sources/`. If it doesn't, call `mos_book_ingest` first.
- `evidence_review` must be non-empty; the server rejects blank strings.
- Ratification is not reversible via MCP — the marker persists. Corrections require a new ingest.

## See also
- domain-memory
- mos_book_promote_verified
- mos_book_audit_walk
