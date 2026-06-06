---
id: mos_promote_to_book
kind: tool
domain: deliverables
auth: [gru]
source: minions/tools/mcp/evaluator_tools.py:51
since: stable
keywords: [book, promote, gru, ethics, sealed, main]
related: [mos_submit, mos_book_ratify, mos_book_promote_verified]
status: stable
---

# mos_promote_to_book

**One line:** Gru promotes an Ethics-sealed artifact into the main-branch Book layout.

## Signature
```py
mos_promote_to_book(
  port: int,
  src_path: str,
  dst_subpath: str,
  commit_message: str | None = None,
  mode: "replace" | "append" = "replace",
) -> {
  port: int,
  dst_path: str,
  commit_sha: str | None,
}
```

## Args
- `src_path` is absolute or project-relative and must stay under `project_{port}/`.
- `dst_subpath` is relative to the main Book layout: `logic/`, `src/`, `evidence/`, `proposal/`, `book/`, or `Book.md`.
- `mode="append"` concatenates onto an existing destination; `replace` overwrites it.

## Pitfalls
- This is Gru-only. Ethics seals evidence; Gru performs the control-plane move.
- Do not pass a path under another project or outside `project_{port}/`.
- `dst_subpath` is not prefixed with `branches/main/`.

## See also
- domain-deliverables
- domain-memory
