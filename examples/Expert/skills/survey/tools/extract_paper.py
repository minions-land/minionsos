"""
ModernKnowledge — extract_paper.py
Per-paper three-dimensional LLM extraction via claude CLI.

Usage:
    python tools/extract_paper.py --topic T --paper-id <paperId>
    python tools/extract_paper.py --topic T --all
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import resolve_topic, add_topic_arg

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# ── LLM Helpers ─────────────────────────────────────────────

def _call_claude(prompt: str, max_retries: int = 2) -> str:
    """Call claude CLI via subprocess."""
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                if attempt < max_retries:
                    print(f"[extract] claude error (attempt {attempt+1}): {result.stderr.strip()[:200]}",
                          file=sys.stderr)
                    continue
                raise RuntimeError(f"claude CLI failed: {result.stderr.strip()[:300]}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                continue
            raise RuntimeError("claude CLI timed out")
        except FileNotFoundError:
            raise RuntimeError("claude CLI not found in PATH")
    raise RuntimeError("All retries exhausted")


def _extract_json(response: str) -> dict:
    """Extract JSON from claude response, handling markdown code blocks."""
    # Try ```json ... ``` blocks
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try entire response
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    # Try first balanced { ... }
    depth = 0
    start = -1
    for i, ch in enumerate(response):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(response[start:i + 1])
                except json.JSONDecodeError:
                    start = -1
    raise ValueError(f"No valid JSON in response: {response[:300]}...")


def _load_prompt(name: str) -> str:
    """Load a prompt template from prompts/ directory."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ── Extraction Functions ────────────────────────────────────

def extract_methods(paper_text: str, meta: dict | None = None) -> dict:
    """Extract method components at three granularity levels."""
    meta_ctx = ""
    if meta:
        meta_ctx = (f"Paper metadata:\n- Title: {meta.get('title', 'N/A')}\n"
                    f"- Authors: {', '.join(meta.get('authors', []))}\n"
                    f"- Year: {meta.get('year', 'N/A')}\n- Venue: {meta.get('venue', 'N/A')}")
    template = _load_prompt("extract_methods.txt")
    prompt = template.replace("{meta_context}", meta_ctx).replace("{paper_text}", paper_text)
    result = _extract_json(_call_claude(prompt))
    if "method_components" not in result:
        result = {"method_components": result if isinstance(result, list) else []}
    return result


def extract_experiments(paper_text: str) -> dict:
    """Extract experiments as five-tuples with baselines and ablations."""
    template = _load_prompt("extract_experiments.txt")
    prompt = template.replace("{paper_text}", paper_text)
    result = _extract_json(_call_claude(prompt))
    if "experiments" not in result:
        result = {"experiments": result if isinstance(result, list) else [], "experiment_gaps": []}
    result.setdefault("experiment_gaps", [])
    return result


def extract_theory(paper_text: str) -> dict:
    """Extract theoretical contributions and empirical-theory gaps."""
    template = _load_prompt("extract_theory.txt")
    prompt = template.replace("{paper_text}", paper_text)
    result = _extract_json(_call_claude(prompt))
    if "theoretical_contributions" not in result:
        result = {"theoretical_contributions": [], "empirical_theory_gaps": []}
    result.setdefault("empirical_theory_gaps", [])
    return result


def extract_full(paper_text: str, meta: dict | None = None) -> dict:
    """Run all three extractions and merge."""
    print("[extract] Extracting method components...", file=sys.stderr)
    methods = extract_methods(paper_text, meta)
    print("[extract] Extracting experiments...", file=sys.stderr)
    experiments = extract_experiments(paper_text)
    print("[extract] Extracting theory...", file=sys.stderr)
    theory = extract_theory(paper_text)
    result = {}
    result.update(methods)
    result.update(experiments)
    result.update(theory)
    return result


# ── Pipeline Integration ────────────────────────────────────

def load_paper_list(topic_dir: Path) -> list[dict]:
    """Load paper_list.json for a topic."""
    path = topic_dir / "paper_list.json"
    if not path.exists():
        raise FileNotFoundError(f"No paper_list.json in {topic_dir}. Run discover_papers.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def paper_id_to_slug(paper: dict) -> str:
    """Generate a filesystem-safe slug from paper metadata."""
    ext = paper.get("externalIds", {})
    if ext.get("ArXiv"):
        return f"arxiv_{ext['ArXiv'].replace('.', '_')}"
    if ext.get("DOI"):
        return ext["DOI"].replace("/", "_").replace(".", "_")[:60]
    # Fallback: sanitize title
    title = paper.get("title", "unknown")[:50]
    return re.sub(r"[^a-zA-Z0-9]", "_", title).strip("_").lower()


def extract_paper(paper: dict, topic_dir: Path) -> Path:
    """Extract a single paper and save to extractions/."""
    slug = paper_id_to_slug(paper)
    out_path = topic_dir / "extractions" / f"{slug}.json"

    # Use abstract as paper text (full text would require PDF parsing)
    paper_text = paper.get("abstract", "")
    if not paper_text:
        print(f"[extract] WARNING: No abstract for {paper.get('title', '?')}", file=sys.stderr)
        paper_text = paper.get("title", "")

    meta = {
        "title": paper.get("title", ""),
        "authors": paper.get("authors", []),
        "year": paper.get("year"),
        "venue": paper.get("venue", ""),
    }

    result = extract_full(paper_text, meta)
    result["paper_id"] = slug
    result["title"] = paper.get("title", "")
    result["year"] = paper.get("year")
    result["venue"] = paper.get("venue", "")
    result["authors"] = paper.get("authors", [])
    result["abstract"] = paper.get("abstract", "")
    result["externalIds"] = paper.get("externalIds", {})
    result["extracted_at"] = datetime.now(timezone.utc).isoformat()

    (topic_dir / "extractions").mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[extract] Saved → {out_path}", file=sys.stderr)
    return out_path


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract paper knowledge via LLM")
    add_topic_arg(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper-id", type=str, help="Slug or index of paper in paper_list.json")
    group.add_argument("--all", action="store_true", help="Extract all pending papers")
    args = parser.parse_args()

    topic_dir = resolve_topic(args.topic)
    papers = load_paper_list(topic_dir)

    if args.all:
        pending = [p for p in papers if p.get("status") == "pending"]
        print(f"[extract] {len(pending)} pending papers to extract")
        for i, p in enumerate(pending, 1):
            print(f"\n[extract] ({i}/{len(pending)}) {p.get('title', '?')[:60]}")
            try:
                extract_paper(p, topic_dir)
                p["status"] = "extracted"
            except Exception as e:
                print(f"[extract] ERROR: {e}", file=sys.stderr)
                p["status"] = "extract_failed"
        # Update paper_list.json with new statuses
        (topic_dir / "paper_list.json").write_text(
            json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        # Find paper by slug or index
        target = args.paper_id
        paper = None
        if target.isdigit():
            idx = int(target)
            if 0 <= idx < len(papers):
                paper = papers[idx]
        else:
            for p in papers:
                if paper_id_to_slug(p) == target or target in p.get("title", ""):
                    paper = p
                    break
        if not paper:
            print(f"Paper '{target}' not found in paper_list.json", file=sys.stderr)
            sys.exit(1)
        extract_paper(paper, topic_dir)
