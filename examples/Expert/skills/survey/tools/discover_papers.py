"""
ModernKnowledge — discover_papers.py
Discover papers via Semantic Scholar API for a given topic.

Usage:
    python tools/discover_papers.py --topic T --query "multivariate time series forecasting" --limit 30
    python tools/discover_papers.py --topic T --query "..." --seeds "arxiv:2211.14730,arxiv:2310.06625"
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from common import resolve_topic, add_topic_arg, init_topic

API_BASE = "https://api.semanticscholar.org/graph/v1/"
SEARCH_FIELDS = "paperId,title,abstract,year,venue,citationCount,authors,externalIds,url"
DETAIL_FIELDS = "paperId,title,abstract,year,venue,citationCount,referenceCount,authors,externalIds,url,tldr,fieldsOfStudy"
REFERENCE_FIELDS = "paperId,title,year,venue,citationCount,authors,externalIds"

_last_request_time = 0.0
_MIN_INTERVAL = 0.5


def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _api_request(url: str, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        _rate_limit()
        try:
            req = Request(url, headers={"User-Agent": "ModernKnowledge/1.0"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 1)
                print(f"[discover] Rate limited. Waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
            elif e.code == 404:
                raise RuntimeError(f"Not found (404): {url}")
            elif e.code >= 500:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"HTTP {e.code}: {e.reason}")
        except URLError as e:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"All {max_retries} retries exhausted for {url}")


def _normalize_paper(paper: dict) -> dict:
    if not paper:
        return {}
    return {
        "paperId": paper.get("paperId"),
        "title": paper.get("title", ""),
        "abstract": paper.get("abstract", ""),
        "year": paper.get("year"),
        "venue": paper.get("venue", ""),
        "citationCount": paper.get("citationCount", 0),
        "authors": [a.get("name", "") for a in paper.get("authors", [])],
        "externalIds": paper.get("externalIds", {}),
        "url": paper.get("url", ""),
    }


# ── API Functions ───────────────────────────────────────────

def search_by_topic(query: str, limit: int = 50) -> list[dict]:
    """Search papers by keyword query via Semantic Scholar."""
    results = []
    offset = 0
    per_page = min(limit, 100)

    while len(results) < limit:
        batch_size = min(per_page, limit - len(results))
        params = urlencode({"query": query, "offset": offset,
                            "limit": batch_size, "fields": SEARCH_FIELDS})
        url = f"{API_BASE}paper/search?{params}"
        try:
            data = _api_request(url)
        except RuntimeError as e:
            print(f"[discover] Search error: {e}", file=sys.stderr)
            break
        papers = data.get("data", [])
        if not papers:
            break
        for p in papers:
            results.append(_normalize_paper(p))
        offset += len(papers)
        if offset >= data.get("total", 0):
            break

    return results[:limit]


def get_paper_details(paper_id: str) -> dict:
    """Get detailed info for a single paper by ID (e.g. 'arxiv:2211.14730')."""
    encoded = quote(paper_id, safe=":")
    url = f"{API_BASE}paper/{encoded}?fields={DETAIL_FIELDS}"
    data = _api_request(url)
    result = _normalize_paper(data)
    result["tldr"] = data.get("tldr", {}).get("text", "") if data.get("tldr") else ""
    result["fieldsOfStudy"] = data.get("fieldsOfStudy", [])
    return result


def get_references(paper_id: str, limit: int = 100) -> list[dict]:
    """Get papers referenced by the given paper."""
    results = []
    offset = 0
    encoded = quote(paper_id, safe=":")
    while len(results) < limit:
        batch_size = min(100, limit - len(results))
        params = urlencode({"offset": offset, "limit": batch_size,
                            "fields": REFERENCE_FIELDS})
        url = f"{API_BASE}paper/{encoded}/references?{params}"
        try:
            data = _api_request(url)
        except RuntimeError:
            break
        items = data.get("data", [])
        if not items:
            break
        for item in items:
            cited = item.get("citedPaper", {})
            if cited and cited.get("paperId"):
                results.append(_normalize_paper(cited))
        offset += len(items)
        if offset >= data.get("total", offset):
            break
    return results[:limit]


# ── Discovery Pipeline ──────────────────────────────────────

def detect_foundational(core_papers: list[dict], min_refs: int = 3) -> list[dict]:
    """
    Find foundational papers: highly-cited works referenced by 3+ core papers.
    Scans references of each core paper, counts co-references.
    """
    ref_counter = Counter()  # paperId -> count of core papers referencing it
    ref_info = {}            # paperId -> paper dict

    core_ids = {p["paperId"] for p in core_papers if p.get("paperId")}
    citation_counts = [p.get("citationCount", 0) for p in core_papers]
    median_citations = sorted(citation_counts)[len(citation_counts) // 2] if citation_counts else 0

    print(f"[discover] Scanning references of {len(core_papers)} core papers for foundational works...",
          file=sys.stderr)

    for paper in core_papers[:20]:  # limit to top-20 to control API calls
        pid = paper.get("paperId")
        if not pid:
            continue
        try:
            refs = get_references(pid, limit=50)
        except RuntimeError:
            continue
        for ref in refs:
            rid = ref.get("paperId")
            if rid and rid not in core_ids:
                ref_counter[rid] += 1
                if rid not in ref_info:
                    ref_info[rid] = ref

    foundational = []
    for rid, count in ref_counter.items():
        if count >= min_refs:
            info = ref_info[rid]
            if info.get("citationCount", 0) > median_citations:
                info["is_foundational"] = True
                info["referenced_by_core_count"] = count
                foundational.append(info)

    foundational.sort(key=lambda x: -x.get("citationCount", 0))
    print(f"[discover] Found {len(foundational)} foundational papers", file=sys.stderr)
    return foundational


def discover(query: str, topic_dir: Path, limit: int = 30,
             seeds: list[str] | None = None) -> list[dict]:
    """
    Full discovery pipeline:
    1. Search by query
    2. Fetch seed papers
    3. Merge and deduplicate
    4. Sort by citations
    5. Detect foundational papers
    6. Save paper_list.json
    """
    # Step 1: keyword search (fetch 2x limit for filtering headroom)
    print(f"[discover] Searching: '{query}' (limit={limit*2})...", file=sys.stderr)
    search_results = search_by_topic(query, limit=limit * 2)
    print(f"[discover] Found {len(search_results)} papers from search", file=sys.stderr)

    # Step 2: fetch seed papers
    seed_papers = []
    if seeds:
        for sid in seeds:
            sid = sid.strip()
            if not sid:
                continue
            try:
                print(f"[discover] Fetching seed: {sid}", file=sys.stderr)
                detail = get_paper_details(sid)
                detail["is_seed"] = True
                seed_papers.append(detail)
            except RuntimeError as e:
                print(f"[discover] Could not fetch seed {sid}: {e}", file=sys.stderr)

    # Step 3: merge and deduplicate
    seen_ids = set()
    merged = []
    for p in seed_papers + search_results:
        pid = p.get("paperId")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            p.setdefault("is_seed", False)
            p.setdefault("is_foundational", False)
            merged.append(p)

    # Step 4: sort by citations, take top N
    merged.sort(key=lambda x: -x.get("citationCount", 0))
    core = merged[:limit]

    # Step 5: detect foundational papers
    foundational = detect_foundational(core)
    for fp in foundational:
        if fp["paperId"] not in seen_ids:
            seen_ids.add(fp["paperId"])
            core.append(fp)

    # Step 6: add status field and save
    for p in core:
        p["status"] = "pending"

    output = topic_dir / "paper_list.json"
    output.write_text(json.dumps(core, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[discover] Saved {len(core)} papers → {output}", file=sys.stderr)
    return core


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover papers for a topic")
    add_topic_arg(parser)
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument("--limit", type=int, default=30, help="Max papers (default: 30)")
    parser.add_argument("--seeds", type=str, default=None,
                        help="Comma-separated seed paper IDs (e.g. arxiv:2211.14730)")
    args = parser.parse_args()

    topic_dir = resolve_topic(args.topic)
    seed_list = args.seeds.split(",") if args.seeds else None
    papers = discover(args.query, topic_dir, limit=args.limit, seeds=seed_list)
    print(f"\nDiscovered {len(papers)} papers:")
    for i, p in enumerate(papers[:10], 1):
        flags = []
        if p.get("is_seed"):
            flags.append("SEED")
        if p.get("is_foundational"):
            flags.append("FOUND")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        print(f"  {i}. [{p.get('year', '?')}] {p['title'][:70]}  (cit={p.get('citationCount', 0)}){flag_str}")
    if len(papers) > 10:
        print(f"  ... and {len(papers) - 10} more")
