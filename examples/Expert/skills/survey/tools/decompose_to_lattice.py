"""
ModernKnowledge — decompose_to_lattice.py
Map raw LLM extraction into lattice-layer-aligned candidate nodes.

Usage:
    python tools/decompose_to_lattice.py --topic T --paper-id <slug>
    python tools/decompose_to_lattice.py --topic T --all
"""

import argparse
import json
import sys
from pathlib import Path

from common import resolve_topic, add_topic_arg
from extract_paper import _call_claude, _extract_json, _load_prompt

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _build_lattice_context(topic_dir: Path) -> str:
    """Build a compact summary of existing lattice for the decompose prompt."""
    lattice_path = topic_dir / "lattice.json"
    if not lattice_path.exists():
        return "No existing lattice yet. This is the first paper."

    lattice = json.loads(lattice_path.read_text(encoding="utf-8"))
    nodes = lattice.get("nodes", [])

    lines = []
    for ntype in ["paradigm", "direction", "method"]:
        items = [n for n in nodes if n.get("type") == ntype]
        if items:
            lines.append(f"\n{ntype.upper()}S ({len(items)}):")
            for n in items:
                extra = ""
                if n.get("belongs_to"):
                    extra = f" [belongs_to: {n['belongs_to']}]"
                lines.append(f"  - {n['id']}: {n.get('label', '?')}{extra}")

    # Also include existing claims for contradiction/support matching
    claims = [n for n in nodes if n.get("type") == "claim"]
    if claims:
        lines.append(f"\nCLAIMS ({len(claims)}):")
        for c in claims:
            lines.append(f"  - {c['id']}: {c.get('label', '?')}")

    # Include existing components for dedup awareness
    components = [n for n in nodes if n.get("type") == "component"]
    if components:
        lines.append(f"\nCOMPONENTS ({len(components)}):")
        for c in components[:50]:  # cap to avoid prompt bloat
            lines.append(f"  - {c['id']}: {c.get('label', '?')}")
        if len(components) > 50:
            lines.append(f"  ... and {len(components) - 50} more")

    return "\n".join(lines) if lines else "Empty lattice."


def decompose_paper(extraction_path: Path, topic_dir: Path) -> Path:
    """Decompose a single paper's extraction into lattice candidates."""
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    slug = extraction_path.stem

    lattice_ctx = _build_lattice_context(topic_dir)
    template = _load_prompt("decompose_to_lattice.txt")

    prompt = (template
              .replace("{lattice_context}", lattice_ctx)
              .replace("{title}", extraction.get("title", ""))
              .replace("{year}", str(extraction.get("year", "?")))
              .replace("{venue}", extraction.get("venue", ""))
              .replace("{authors}", ", ".join(extraction.get("authors", [])))
              .replace("{extraction_json}", json.dumps(extraction, ensure_ascii=False, indent=2)[:8000]))

    print(f"[decompose] Calling LLM for {slug}...", file=sys.stderr)
    result = _extract_json(_call_claude(prompt))

    # Attach paper metadata for downstream use
    result["_paper_id"] = slug
    result["_title"] = extraction.get("title", "")
    result["_year"] = extraction.get("year")
    result["_venue"] = extraction.get("venue", "")
    result["_authors"] = extraction.get("authors", [])
    result["_externalIds"] = extraction.get("externalIds", {})

    out_path = topic_dir / "candidates" / f"{slug}.json"
    (topic_dir / "candidates").mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[decompose] Saved → {out_path}", file=sys.stderr)
    return out_path


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decompose extractions into lattice candidates")
    add_topic_arg(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper-id", type=str, help="Extraction slug (filename without .json)")
    group.add_argument("--all", action="store_true", help="Decompose all extractions without candidates")
    args = parser.parse_args()

    topic_dir = resolve_topic(args.topic)
    extractions_dir = topic_dir / "extractions"
    candidates_dir = topic_dir / "candidates"

    if args.all:
        existing_candidates = {p.stem for p in candidates_dir.glob("*.json")} if candidates_dir.exists() else set()
        to_process = [p for p in sorted(extractions_dir.glob("*.json"))
                      if p.stem not in existing_candidates]
        print(f"[decompose] {len(to_process)} extractions to decompose")
        for i, ep in enumerate(to_process, 1):
            print(f"\n[decompose] ({i}/{len(to_process)}) {ep.stem}")
            try:
                decompose_paper(ep, topic_dir)
            except Exception as e:
                print(f"[decompose] ERROR: {e}", file=sys.stderr)
    else:
        ep = extractions_dir / f"{args.paper_id}.json"
        if not ep.exists():
            print(f"Extraction not found: {ep}", file=sys.stderr)
            sys.exit(1)
        decompose_paper(ep, topic_dir)
