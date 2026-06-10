#!/usr/bin/env python3
"""Build MANUAL/INDEX.json from atomic pages under tools/, pitfalls/, recipes/, domains/."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL_ROOT = ROOT
PROJECT_ROOT = ROOT.parent

PAGE_DIRS = ["tools", "pitfalls", "recipes", "domains"]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_STUB_MARKERS = ("status: stub", "No curated MANUAL page yet", "STUB — fill in")
_SOURCE_RE = re.compile(r"^source:\s*(\S+):(\d+)\s*$", re.MULTILINE)

# Reuse the single source-of-truth docstring extractors from lookup.py so the
# index and the read-time page render agree on what a stub resolves to.
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from lookup import _extract_py_docstring, _extract_ts_description  # type: ignore
except Exception:  # pragma: no cover
    _extract_py_docstring = _extract_ts_description = None  # type: ignore

_WORD_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
_STOPWORDS = {
    "the", "and", "for", "this", "that", "with", "from", "into", "via", "use",
    "used", "uses", "when", "what", "which", "your", "you", "are", "its", "it",
    "not", "only", "per", "see", "all", "any", "one", "two", "returns", "return",
    "each", "plus", "optional", "keys", "dict", "list", "str", "bool", "int",
}


def _source_docstring(text: str) -> str | None:
    """Return the live source docstring/description for a stub page, if any."""
    if _extract_py_docstring is None:
        return None
    m = _SOURCE_RE.search(text)
    if not m:
        return None
    rel_path, lineno = m.group(1), int(m.group(2))
    if rel_path.endswith(".py"):
        return _extract_py_docstring(rel_path, lineno)
    if rel_path.endswith(".ts"):
        return _extract_ts_description(rel_path, lineno)
    return None


def _harvest_keywords(doc: str, limit: int = 12) -> list[str]:
    seen: dict[str, None] = {}
    for w in _WORD_RE.findall(doc.lower()):
        if w in _STOPWORDS or w.startswith("mos_") or w.startswith("eacn3_"):
            continue
        seen.setdefault(w, None)
        if len(seen) >= limit:
            break
    return list(seen)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text, body = m.group(1), text[m.end() :]
    fm: dict = {}
    cur_key = None
    for line in fm_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and cur_key:
            fm[cur_key].append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        cur_key = key
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [s.strip().strip("'\"") for s in inner.split(",")] if inner else []
        elif val == "":
            fm[key] = []
        else:
            fm[key] = val.strip("'\"")
    return fm, body


def extract_summary(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("**One line:**"):
            return line.removeprefix("**One line:**").strip()
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("```"):
            return s[:160]
    return ""


def get_repo_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def main() -> int:
    pages: dict[str, dict] = {}
    domains: dict[str, list[str]] = {}
    by_role: dict[str, list[str]] = {}
    by_keyword: dict[str, list[str]] = {}

    for sub in PAGE_DIRS:
        d = MANUAL_ROOT / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            if "id" not in fm:
                rel = p.relative_to(MANUAL_ROOT)
                print(f"WARN: {rel} has no `id:` — skipping", file=sys.stderr)
                continue
            pid = fm["id"]
            summary = extract_summary(body)
            keywords = fm.get("keywords", []) if isinstance(fm.get("keywords"), list) else []
            # Stub pages carry a noise summary ("No curated page yet") and empty
            # keywords, so they neither display nor retrieve. Backfill both from
            # the live source docstring — the same content lookup.py renders at
            # read time — so search recall and the summary line agree with it.
            is_stub = any(marker in text for marker in _STUB_MARKERS)
            if is_stub:
                doc = _source_docstring(text)
                if doc:
                    first = re.split(r"(?<=[.!?])\s", doc.strip(), maxsplit=1)[0]
                    summary = first.strip()[:160]
                    if not keywords:
                        keywords = _harvest_keywords(doc)
            # Even curated pages often ship `keywords: []`, so retrieval only
            # sees id+summary and misses the body's vocabulary (the concept-
            # vocabulary gap that made `revive` unfindable from "activate role").
            # When no keywords are declared, harvest them from the page body
            # plus any source docstring — every page becomes retrievable by the
            # words it actually uses, not just its title.
            if not keywords:
                corpus = body
                doc = _source_docstring(text) if fm.get("source") else None
                if doc:
                    corpus = corpus + "\n" + doc
                keywords = _harvest_keywords(corpus, limit=16)
            page = {
                "kind": fm.get("kind", sub.rstrip("s")),
                "path": str(p.relative_to(MANUAL_ROOT)),
                "domain": fm.get("domain", ""),
                "auth": fm.get("auth", []) if isinstance(fm.get("auth"), list) else [fm["auth"]],
                "source": fm.get("source", ""),
                "since": fm.get("since", ""),
                "status": fm.get("status", "stable"),
                "summary": summary,
                "keywords": keywords,
                "related": fm.get("related", []) if isinstance(fm.get("related"), list) else [],
            }
            pages[pid] = page
            domains.setdefault(page["domain"], []).append(pid)
            for role in page["auth"]:
                by_role.setdefault(role, []).append(pid)
            for kw in page["keywords"]:
                by_keyword.setdefault(kw.lower(), []).append(pid)

    out = {
        "version": get_repo_sha(),
        "built_at": datetime.now(UTC).isoformat(),
        "page_count": len(pages),
        "pages": pages,
        "domains": {k: sorted(v) for k, v in domains.items()},
        "by_role": {k: sorted(v) for k, v in by_role.items()},
        "by_keyword": {k: sorted(v) for k, v in by_keyword.items()},
    }
    out_path = MANUAL_ROOT / "INDEX.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=False), encoding="utf-8")
    print(
        f"OK wrote {out_path.relative_to(PROJECT_ROOT)} — {len(pages)} pages, "
        f"{len(domains)} domains, {len(by_role)} roles, {len(by_keyword)} keywords"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
