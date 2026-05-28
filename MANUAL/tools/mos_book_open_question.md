---
id: mos_book_open_question
kind: tool
domain: memory
auth: [gru, coder, ethics, writer, expert]
source: minions/tools/mcp/memory_tools.py:377
since: stable
keywords: [book, open-question, gap, unresolved, research, question]
related: [mos_book_ingest, mos_book_query, mos_book_dead_end, mos_book_ratify]
status: stable
---

# mos_book_open_question

**One line:** Record an open research question as a durable Book page at `book/open_questions/<slug>.md`.

## Signature
```py
mos_book_open_question(
  question: str,                   # non-empty question text
  related_pages: list[str] | None, # optional list of book/... paths
  slug: str | None,                # optional explicit slug; defaults to slugified question prefix
  port: int | None,
) -> {
  slug: str,
  book_path: str,                  # "book/open_questions/<slug>.md"
  publish_result: dict,
}
```

## When to call
- When you identify a gap or unresolved question during investigation that
  future work (same or other projects) should address.
- Before abandoning a line of inquiry — capturing the open question lets
  `mos_shelf_query` surface it cross-project.
- Do NOT use for definitively refuted claims — use `mos_book_dead_end` instead.

## Authz
All EACN-visible roles may call this. Noter is excluded (uses timer-based
workflow; contributes open questions via EACN message → shared handoffs).

## Page location
Pages land at `branches/shared/book/open_questions/<slug>.md` with
`status: open_question`. They are indexed and returned by `mos_book_query`.
Update `status` to `resolved` (via `mos_book_ingest` or direct edit) when
the question is answered.

## Pitfalls
- **Duplicate questions**: run `mos_book_query` first; if a page already
  covers the topic, link via `related_pages` rather than creating a
  near-duplicate.
- `question` must be non-empty; blank input raises `BookError`.
- Slugs are auto-generated from the question text if omitted; very long
  questions truncate at 60 chars.

## See also
- domain-memory
- mos_book_dead_end
- mos_book_query
