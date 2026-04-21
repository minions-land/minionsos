"""
ModernKnowledge — orchestrate.py
End-to-end pipeline orchestrator: Discover → Extract → Decompose → Merge → Build.

Usage:
    python tools/orchestrate.py --topic T --query "..." --limit 30
    python tools/orchestrate.py --topic T --stage discover --query "..."
    python tools/orchestrate.py --topic T --from-stage decompose
    python tools/orchestrate.py --topic T --stage build
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from common import resolve_topic, add_topic_arg, init_topic

STAGES = ["discover", "extract", "decompose", "merge", "build"]


def _load_state(topic_dir: Path) -> dict:
    path = topic_dir / "pipeline_state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"topic": topic_dir.name, "stages_completed": [], "last_run": None}


def _save_state(topic_dir: Path, state: dict):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    (topic_dir / "pipeline_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_discover(topic_dir: Path, query: str, limit: int, seeds: list[str] | None):
    from discover_papers import discover
    discover(query, topic_dir, limit=limit, seeds=seeds)


def run_extract(topic_dir: Path):
    from extract_paper import load_paper_list, extract_paper, paper_id_to_slug
    papers = load_paper_list(topic_dir)
    extractions_dir = topic_dir / "extractions"
    existing = {p.stem for p in extractions_dir.glob("*.json")} if extractions_dir.exists() else set()

    pending = [p for p in papers if paper_id_to_slug(p) not in existing]
    print(f"\n[orchestrate] EXTRACT: {len(pending)} papers to process")
    for i, p in enumerate(pending, 1):
        print(f"\n  ({i}/{len(pending)}) {p.get('title', '?')[:60]}")
        try:
            extract_paper(p, topic_dir)
            p["status"] = "extracted"
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            p["status"] = "extract_failed"
    # Update statuses
    (topic_dir / "paper_list.json").write_text(
        json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")


def run_decompose(topic_dir: Path):
    from decompose_to_lattice import decompose_paper
    extractions_dir = topic_dir / "extractions"
    candidates_dir = topic_dir / "candidates"
    existing = {p.stem for p in candidates_dir.glob("*.json")} if candidates_dir.exists() else set()
    to_process = [p for p in sorted(extractions_dir.glob("*.json")) if p.stem not in existing]

    print(f"\n[orchestrate] DECOMPOSE: {len(to_process)} extractions to process")
    for i, ep in enumerate(to_process, 1):
        print(f"\n  ({i}/{len(to_process)}) {ep.stem}")
        try:
            decompose_paper(ep, topic_dir)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)


def run_merge(topic_dir: Path):
    from anchor_merge import merge_paper
    candidates_dir = topic_dir / "candidates"
    reports_dir = topic_dir / "reports"
    existing = {p.stem.replace("merge_", "") for p in reports_dir.glob("merge_*.md")} if reports_dir.exists() else set()
    to_merge = [p for p in sorted(candidates_dir.glob("*.json")) if p.stem not in existing]

    print(f"\n[orchestrate] MERGE: {len(to_merge)} candidates to merge")
    for i, cp in enumerate(to_merge, 1):
        print(f"\n  ({i}/{len(to_merge)}) {cp.stem}")
        try:
            report = merge_paper(cp, topic_dir)
            print(f"  Created: {len(report['created'])}, Anchored: {len(report['anchored'])}")
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)


def run_build(topic_dir: Path):
    from build_lattice import build
    from insights import extract_all

    print("\n[orchestrate] BUILD: Compiling lattice...")
    lattice = build(topic_dir)

    print("[orchestrate] BUILD: Extracting insights...")
    insights = extract_all(lattice)
    print(f"  {len(insights)} insights extracted")

    insights_path = topic_dir / "insights.json"
    insights_path.write_text(
        json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[orchestrate] Done. Lattice: {topic_dir / 'lattice.json'}, Insights: {insights_path}")


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ModernKnowledge pipeline orchestrator")
    add_topic_arg(parser)
    parser.add_argument("--query", type=str, help="Search query (required for discover stage)")
    parser.add_argument("--limit", type=int, default=30, help="Max papers to discover")
    parser.add_argument("--seeds", type=str, default=None, help="Comma-separated seed paper IDs")
    parser.add_argument("--stage", type=str, choices=STAGES, help="Run a single stage")
    parser.add_argument("--from-stage", type=str, choices=STAGES, help="Run from this stage onward")
    parser.add_argument("--checkpoint", action="store_true", help="Pause after each stage")
    args = parser.parse_args()

    topic_dir = resolve_topic(args.topic)
    state = _load_state(topic_dir)

    # Determine which stages to run
    if args.stage:
        stages = [args.stage]
    elif args.from_stage:
        idx = STAGES.index(args.from_stage)
        stages = STAGES[idx:]
    else:
        stages = STAGES

    seed_list = args.seeds.split(",") if args.seeds else None

    print(f"[orchestrate] Topic: {args.topic}")
    print(f"[orchestrate] Stages: {' → '.join(stages)}")
    start = time.time()

    for stage in stages:
        print(f"\n{'='*60}")
        print(f"  STAGE: {stage.upper()}")
        print(f"{'='*60}")

        if stage == "discover":
            if not args.query:
                print("ERROR: --query required for discover stage", file=sys.stderr)
                sys.exit(1)
            run_discover(topic_dir, args.query, args.limit, seed_list)
        elif stage == "extract":
            run_extract(topic_dir)
        elif stage == "decompose":
            run_decompose(topic_dir)
        elif stage == "merge":
            run_merge(topic_dir)
        elif stage == "build":
            run_build(topic_dir)

        state["stages_completed"].append({"stage": stage, "at": datetime.now(timezone.utc).isoformat()})
        _save_state(topic_dir, state)

        if args.checkpoint and stage != stages[-1]:
            print(f"\n[orchestrate] Checkpoint after {stage}. Press Enter to continue...")
            input()

    elapsed = time.time() - start
    print(f"\n[orchestrate] Pipeline complete in {elapsed:.1f}s")
