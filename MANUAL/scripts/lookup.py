#!/usr/bin/env python3
"""MANUAL lookup — agent-facing retrieval over the atomic-page index.

Usage:
    lookup.py "queue dispatch retry"        # top 5 hits + first 12 lines each
    lookup.py "<query>" -k 3                # top 3 hits
    lookup.py "<query>" --role expert       # filter by role
    lookup.py --id mos_exp_run              # fetch one page verbatim
    lookup.py --id mos_exp_run --section signature
    lookup.py --domain experiments          # list domain pages
    lookup.py --pitfalls "queue"            # only pitfalls
    lookup.py --decision "I want to publish" # decision-map style query

The output budget is ≤ 1 KB unless --full / -v is passed. Mirrors ToolSearch
ergonomics: a query → a small payload that contains exactly the right page
ids and snippets to act on.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "INDEX.json"
REPO_ROOT = ROOT.parent


def _extract_py_docstring(rel_path: str, lineno: int) -> str | None:
    """Pull the docstring of the function defined at/after ``lineno``.

    The MANUAL ``source:`` ref points at the ``@mcp.tool()`` decorator or the
    ``def`` line. We scan forward for the ``def``, then capture the triple-
    quoted docstring that follows. Single source of truth = the code; this is
    why stub pages never need a hand-copied body.
    """
    src = REPO_ROOT / rel_path
    if not src.exists():
        return None
    try:
        lines = src.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    i = max(0, lineno - 1)
    # advance to the def line (decorator-tolerant; handles `async def`)
    def _is_def(ln: str) -> bool:
        s = ln.lstrip()
        return s.startswith("def ") or s.startswith("async def ")

    while i < len(lines) and i < lineno + 8 and not _is_def(lines[i]):
        i += 1
    if i >= len(lines) or not _is_def(lines[i]):
        return None
    # the signature may span multiple lines — advance to the line that closes
    # it (`)` then optional `-> T` then `:`), and look for the docstring after.
    sig_end = i
    while sig_end < len(lines) and sig_end < i + 20:
        if re.search(r"\)\s*(->[^:]+)?:\s*(#.*)?$", lines[sig_end]):
            break
        sig_end += 1
    # find the opening triple quote within the next few lines
    j = sig_end + 1
    quote = None
    while j < len(lines) and j < sig_end + 6:
        s = lines[j].lstrip()
        if s.startswith('"""') or s.startswith("'''"):
            quote = s[:3]
            break
        if s and not s.startswith("#"):
            break  # first real statement is not a docstring
        j += 1
    if quote is None:
        return None
    first = lines[j].lstrip()[3:]
    if quote in first:  # single-line docstring
        return first.split(quote)[0].strip()
    rest = []
    k = j + 1
    while k < len(lines):
        if quote in lines[k]:
            rest.append(lines[k].split(quote)[0])
            break
        rest.append(lines[k])
        k += 1
    import textwrap

    body = textwrap.dedent("\n".join(rest)).strip()
    head = first.strip()
    return (head + "\n\n" + body).strip() if body else head


def _extract_ts_description(rel_path: str, lineno: int) -> str | None:
    """Pull the ``description:`` string from an EACN3 registerTool block."""
    src = REPO_ROOT / rel_path
    if not src.exists():
        return None
    try:
        text = src.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()
    window = "\n".join(lines[max(0, lineno - 1) : lineno + 40])
    m = re.search(r'description:\s*"((?:[^"\\]|\\.)*)"', window, re.DOTALL)
    if not m:
        return None
    return m.group(1).replace('\\"', '"').replace("\\n", "\n").strip()


def backfill_from_source(text: str) -> str:
    """If a page body is a stub, append the live source docstring/description.

    Stubs are detected by ``status: stub`` frontmatter or the placeholder
    body. The contract docs ("look it up in the MANUAL") only pay off if the
    lookup returns the real thing — so we resolve it from the code at read
    time rather than maintaining a hand-copied duplicate that drifts.
    """
    is_stub = (
        "status: stub" in text
        or "No curated MANUAL page yet" in text
        or "STUB — fill in" in text
    )
    if not is_stub:
        return text
    m = re.search(r"^source:\s*(\S+):(\d+)\s*$", text, re.MULTILINE)
    if not m:
        return text
    rel_path, lineno = m.group(1), int(m.group(2))
    if rel_path.endswith(".py"):
        doc = _extract_py_docstring(rel_path, lineno)
    elif rel_path.endswith(".ts"):
        doc = _extract_ts_description(rel_path, lineno)
    else:
        doc = None
    if not doc:
        return text
    return (
        text.rstrip()
        + "\n\n## Contract (from source docstring)\n\n"
        + doc.strip()
        + f"\n\n_(Auto-surfaced from `{rel_path}:{lineno}` — the code is the "
        "single source of truth; this page is a stub with no hand-curated "
        "additions yet.)_\n"
    )


def load_index() -> dict:
    if not INDEX_PATH.exists():
        print(f"ERR: {INDEX_PATH} missing — run scripts/build_index.py first", file=sys.stderr)
        sys.exit(2)
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def tokenize(s: str) -> list[str]:
    return [t for t in re.split(r"[\s,;./_\-:]+", s.lower()) if t]


def score_page(page_id: str, page: dict, query_tokens: list[str]) -> float:
    score = 0.0
    id_tokens = set(tokenize(page_id))
    kw_tokens = set(t.lower() for t in page.get("keywords", []))
    summary_tokens = set(tokenize(page.get("summary", "")))
    related_tokens = set(tokenize(" ".join(page.get("related", []))))
    for q in query_tokens:
        if q in id_tokens:
            score += 5.0
        if q in kw_tokens:
            score += 3.0
        if any(q in tk for tk in id_tokens):
            score += 1.5
        if q in summary_tokens:
            score += 1.0
        if q in related_tokens:
            score += 0.5
    return score


def page_excerpt(page: dict, lines: int = 12) -> str:
    p = ROOT / page["path"]
    if not p.exists():
        return "(missing page file)"
    text = p.read_text(encoding="utf-8")
    body = text.split("---\n", 2)[-1] if text.startswith("---") else text
    out = []
    for ln in body.splitlines():
        if not ln.strip() and not out:
            continue
        out.append(ln)
        if len(out) >= lines:
            break
    return "\n".join(out)


def fmt_hit(idx: int, page_id: str, page: dict, with_excerpt: bool = True) -> str:
    head = f"[{idx}] {page_id}  ({page['kind']}, {page.get('domain', '')}) — {page['path']}"
    if page.get("source"):
        head += f"  src={page['source']}"
    if not with_excerpt:
        return head
    return f"{head}\n  summary: {page.get('summary', '')[:200]}\n"


def cmd_query(idx: dict, query: str, k: int, role: str | None, kind: str | None) -> int:
    qt = tokenize(query)
    if not qt:
        print("ERR: empty query", file=sys.stderr)
        return 2
    items = idx["pages"].items()
    if role:
        items = [(i, p) for i, p in items if role in p.get("auth", []) or "*" in p.get("auth", [])]
    if kind:
        items = [(i, p) for i, p in items if p.get("kind") == kind]
    scored = [(score_page(i, p, qt), i, p) for i, p in items]
    scored = [t for t in scored if t[0] > 0]
    scored.sort(key=lambda t: -t[0])
    if not scored:
        print("(no matches)")
        return 0
    out_lines = [
        f"# lookup: {query!r}  →  {min(k, len(scored))}/{len(scored)} hits  "
        f"(index v{idx['version']}, {idx['page_count']} pages)"
    ]
    for i, (_score, pid, page) in enumerate(scored[:k], start=1):
        out_lines.append(fmt_hit(i, pid, page))
    out_lines.append("")
    out_lines.append(
        "Fetch a page in full:  python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --id <id>"
    )
    print("\n".join(out_lines))
    return 0


def cmd_id(idx: dict, page_id: str, section: str | None, full: bool) -> int:
    page = idx["pages"].get(page_id)
    if not page:
        # try fuzzy
        cands = [pid for pid in idx["pages"] if page_id in pid]
        if len(cands) == 1:
            page_id = cands[0]
            page = idx["pages"][page_id]
        else:
            print(f"ERR: id {page_id!r} not found. Did you mean: {cands[:5]}", file=sys.stderr)
            return 2
    p = ROOT / page["path"]
    text = p.read_text(encoding="utf-8")
    text = backfill_from_source(text)
    if full:
        sys.stdout.write(text)
        return 0
    if section:
        # extract a markdown section
        pat = re.compile(
            rf"^##\s+{re.escape(section)}\s*$.*?(?=^##\s+|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        m = pat.search(text)
        if not m:
            print(f"ERR: section {section!r} not found in {page_id}", file=sys.stderr)
            return 2
        sys.stdout.write(m.group(0).rstrip() + "\n")
        return 0
    sys.stdout.write(text)
    return 0


def cmd_domain(idx: dict, domain: str) -> int:
    pages = idx["domains"].get(domain, [])
    if not pages:
        print(f"(no pages in domain {domain!r}; known: {sorted(idx['domains'].keys())})")
        return 1
    print(f"# domain: {domain}  —  {len(pages)} pages")
    for pid in pages:
        p = idx["pages"][pid]
        auth = ",".join(p.get("auth", [])) or "*"
        print(f"  {pid:40s}  [{p['kind']:7s}] {auth:20s}  {p.get('summary', '')[:100]}")
    return 0


def cmd_decision(idx: dict, query: str) -> int:
    """Decision-map style: given a goal, recommend tool ids in order."""
    qt = tokenize(query)
    boosts = {
        "publish": ["mos_publish_to_shared"],
        "wake": ["mos_await_events"],
        "queue": ["mos_exp_queue_status", "mos_exp_queue_submit", "mos_exp_queue_reconcile"],
        "spawn": ["mos_spawn_role", "mos_spawn_expert"],
        "review": ["mos_review_run"],
        "submit": ["mos_submit"],
        "evaluate": ["mos_evaluate"],
        "draft": ["mos_draft_view", "mos_draft_append", "mos_draft_annotate"],
        "book": ["mos_book_query", "mos_book_ingest"],
        "search": ["mos_search_papers_federated", "mos_search_arxiv"],
        "denied": ["pitfall-tool-denied", "pitfall-empty-authz"],
        "fail": ["pitfall-empty-authz", "pitfall-deferred-schema", "pitfall-queue-deadlaunch-fp"],
    }
    cands: list[str] = []
    for q in qt:
        for k, ids in boosts.items():
            if q in k or k in q:
                cands.extend(ids)
    seen = set()
    cands = [c for c in cands if not (c in seen or seen.add(c))]
    cands = [c for c in cands if c in idx["pages"]]
    if not cands:
        return cmd_query(idx, query, k=5, role=None, kind=None)
    print(f"# decision-map: {query!r}")
    for i, pid in enumerate(cands[:6], 1):
        page = idx["pages"][pid]
        print(fmt_hit(i, pid, page, with_excerpt=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("-k", type=int, default=5, help="top-k hits")
    ap.add_argument("--id", dest="id_", help="fetch a page by id")
    ap.add_argument("--section", help="with --id: extract a single ## section")
    ap.add_argument("--full", "-v", action="store_true", help="full page output")
    ap.add_argument("--role", help="filter by role auth")
    ap.add_argument("--kind", choices=["tool", "pitfall", "recipe", "domain"])
    ap.add_argument("--domain", help="list pages in a domain")
    ap.add_argument("--pitfalls", action="store_true", help="search only pitfalls")
    ap.add_argument("--decision", help="goal-driven recommendation (decision-map)")
    args = ap.parse_args()

    idx = load_index()
    if args.id_:
        return cmd_id(idx, args.id_, args.section, args.full)
    if args.domain:
        return cmd_domain(idx, args.domain)
    if args.decision:
        return cmd_decision(idx, args.decision)
    if not args.query:
        ap.print_help()
        return 0
    kind = "pitfall" if args.pitfalls else args.kind
    return cmd_query(idx, args.query, args.k, args.role, kind)


if __name__ == "__main__":
    sys.exit(main())
