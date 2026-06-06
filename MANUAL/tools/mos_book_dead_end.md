---
id: mos_book_dead_end
kind: tool
domain: memory
auth: [gru, expert, ethics]
source: minions/tools/mcp/memory_tools.py:427
since: stable
keywords: [book, dead-end, refuted, negative-knowledge, refutation, do-not-repeat]
related: [mos_book_ingest, mos_book_open_question, mos_book_resolve_contradiction]
status: stable
---

# mos_book_dead_end

**One line:** Record a refuted claim as a permanent dead-end Book page so other projects do not re-run the same failed experiment.

## Signature
```py
mos_book_dead_end(
  claim: str,                # non-empty claim that was refuted
  refutation_evidence: str,  # non-empty evidence text that refutes it
  slug: str | None,          # optional suffix; final slug = "dead-end-<slug>"
  port: int | None,
) -> {
  slug: str,                 # full slug, e.g. "dead-end-foo-bar"
  book_path: str,            # "book/sources/dead-end-<slug>.md"
  publish_result: dict,
}
```

## Critical invariant
**REFUTED PAGES MUST NEVER BE DELETED.** They are negative knowledge that
prevents other projects from re-running the same failed experiment. The page
is written under `book/sources/` with `status: refuted`; downstream tooling
(book-promote, audit walks) treats `status: refuted` as terminal.

## When to call
- After running an experiment that definitively refutes a hypothesis you
  previously held (or the literature held).
- After a literature review surfaces refutation evidence for a claim that
  was previously ingested as `verified` — pair this with
  `mos_book_resolve_contradiction` to mark the conflict.
- Do NOT use for claims that are merely "unsupported" or "unconfirmed" —
  use `mos_book_open_question` for those.

## What it writes
- A new page at `branches/main/book/sources/dead-end-<slug>.md` with
  V2 frontmatter (`page_kind: source`, `status: refuted`, title prefixed
  `Dead end:`).
- Body has two sections: `## Claim` and `## Refutation evidence`.
- Index entry + log entry on the shared branch.

## Pitfalls
- Both `claim` and `refutation_evidence` must be non-empty.
- The slug auto-prefixes `dead-end-`; do not include `dead-end-` yourself or
  you'll get `dead-end-dead-end-...`.
- Refutation evidence must be cite-able — write it like a Book source
  paragraph, not like a private gripe.

## See also
- domain-memory
- mos_book_open_question
- mos_book_resolve_contradiction
