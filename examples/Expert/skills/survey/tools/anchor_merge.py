"""
ModernKnowledge — anchor_merge.py
Anchor candidate nodes against existing lattice, deduplicate, write .md files.

Usage:
    python tools/anchor_merge.py --topic T --paper-id <slug>
    python tools/anchor_merge.py --topic T --all
    python tools/anchor_merge.py --topic T --all --dry-run
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from common import resolve_topic, add_topic_arg

THRESHOLD_HIGH = 0.55   # above this: definitely same concept
THRESHOLD_LOW = 0.30    # below this: definitely different


def _slugify(label: str) -> str:
    """Convert a label to a filesystem-safe slug."""
    s = label.lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    return s.strip("-")[:60]


def _similarity(a: str, b: str) -> float:
    """Combined label + description similarity."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _keyword_overlap(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _combined_sim(a_label: str, a_desc: str, b_label: str, b_desc: str) -> float:
    label_sim = _similarity(a_label, b_label)
    desc_sim = _keyword_overlap(a_desc, b_desc) if a_desc and b_desc else 0.0
    return 0.6 * label_sim + 0.4 * desc_sim


# ── Node File Writing ───────────────────────────────────────

def _write_node(topic_dir: Path, subdir: str, slug: str, frontmatter: dict, body: str = ""):
    """Write a .md node file with YAML frontmatter."""
    path = topic_dir / subdir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    path.write_text(f"---\n{fm}---\n{body}\n", encoding="utf-8")
    return path


def _ensure_unique_id(node_id: str, existing_ids: set) -> str:
    """Ensure node ID is unique, appending -2, -3 etc. if needed."""
    if node_id not in existing_ids:
        return node_id
    prefix, name = node_id.split(":", 1)
    for i in range(2, 100):
        candidate = f"{prefix}:{name}-{i}"
        if candidate not in existing_ids:
            return candidate
    return node_id  # fallback


# ── Anchoring Logic ─────────────────────────────────────────

def _find_best_match(label: str, desc: str, existing: list[dict]) -> tuple[dict | None, float]:
    """Find the best matching existing node by similarity."""
    best, best_score = None, 0.0
    for node in existing:
        score = _combined_sim(label, desc, node.get("label", ""), node.get("description", ""))
        if score > best_score:
            best_score = score
            best = node
    return best, best_score


# ── Main Merge Logic ────────────────────────────────────────

def merge_paper(candidate_path: Path, topic_dir: Path, dry_run: bool = False) -> dict:
    """Merge a single paper's candidates into the lattice."""
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    slug = candidate.get("_paper_id", candidate_path.stem)

    # Load existing lattice for anchoring
    lattice_path = topic_dir / "lattice.json"
    if lattice_path.exists():
        lattice = json.loads(lattice_path.read_text(encoding="utf-8"))
    else:
        lattice = {"nodes": [], "edges": []}

    existing_ids = {n["id"] for n in lattice["nodes"]}
    existing_by_type = {}
    for n in lattice["nodes"]:
        existing_by_type.setdefault(n.get("type", ""), []).append(n)

    report = {"created": [], "anchored": [], "paper_id": slug}
    created_files = []

    # ── Paper node ──────────────────────────────────────────
    paper_id = f"paper:{slug}"
    paper_fm = {
        "id": paper_id, "type": "paper",
        "title": candidate.get("_title", ""),
        "authors": candidate.get("_authors", []),
        "year": candidate.get("_year"),
        "venue": candidate.get("_venue", ""),
        "tags": [],
    }
    if not dry_run:
        _write_node(topic_dir, "papers", slug, paper_fm)
    report["created"].append(paper_id)

    # ── Direction ───────────────────────────────────────────
    dir_data = candidate.get("direction", {})
    if dir_data.get("existing_id"):
        direction_id = dir_data["existing_id"]
        report["anchored"].append({"type": "direction", "anchored_to": direction_id})
    elif dir_data.get("label"):
        dir_slug = _slugify(dir_data["label"])
        direction_id = _ensure_unique_id(f"direction:{dir_slug}", existing_ids)
        existing_ids.add(direction_id)
        dir_fm = {
            "id": direction_id, "type": "direction",
            "label": dir_data["label"],
            "description": dir_data.get("description", ""),
            "belongs_to": dir_data.get("belongs_to", ""),
            "status": "active",
            "key_question": dir_data.get("key_question", ""),
        }
        if not dry_run:
            _write_node(topic_dir, "nodes/directions", dir_slug, dir_fm, dir_data.get("description", ""))
        report["created"].append(direction_id)
    else:
        direction_id = None

    # ── Method ──────────────────────────────────────────────
    method_data = candidate.get("method", {})
    if method_data.get("label"):
        m_slug = _slugify(method_data["label"])
        method_id = _ensure_unique_id(f"method:{m_slug}", existing_ids)
        existing_ids.add(method_id)

        # Resolve relation targets (method extends/combines)
        relations = []
        for rel in method_data.get("relations", []):
            target = rel.get("target_id", "")
            if target and target in existing_ids:
                relations.append({
                    "target": target, "type": rel.get("type", "extends"),
                    "confidence": rel.get("confidence", 0.8),
                    "provenance": rel.get("provenance", ""),
                })

        method_fm = {
            "id": method_id, "type": "method",
            "label": method_data["label"],
            "description": method_data.get("description", ""),
            "belongs_to": direction_id or "",
            "introduced_by": paper_id,
            "year": candidate.get("_year"),
            "venue": candidate.get("_venue", ""),
            "architecture_type": method_data.get("architecture_type", ""),
            "origin_field": method_data.get("origin_field", ""),
            "constraints": method_data.get("constraints", {}),
            "relations": relations,  # will be populated with composed_of below
        }
        if not dry_run:
            # Don't write yet — we'll add composed_of relations from components
            pass
        report["created"].append(method_id)
    else:
        method_id = None
        method_fm = None

    # ── Components ──────────────────────────────────────────
    component_id_map = {}  # candidate label -> actual node id
    for comp in candidate.get("components", []):
        label = comp.get("label", "")
        desc = comp.get("description", "")
        if not label:
            continue

        # Anchor against existing components
        match, score = _find_best_match(label, desc, existing_by_type.get("component", []))

        if score >= THRESHOLD_HIGH and match:
            # Anchor to existing
            component_id_map[label] = match["id"]
            report["anchored"].append({
                "type": "component", "label": label,
                "anchored_to": match["id"], "similarity": round(score, 3),
            })
        else:
            # Create new component
            c_slug = _slugify(label)
            comp_id = _ensure_unique_id(f"component:{c_slug}", existing_ids)
            existing_ids.add(comp_id)
            component_id_map[label] = comp_id

            comp_relations = []
            for rel in comp.get("relations", []):
                # Try to resolve target_label to existing component id
                t_label = rel.get("target_label", "")
                t_match, t_score = _find_best_match(t_label, "", existing_by_type.get("component", []))
                if t_match and t_score > THRESHOLD_LOW:
                    comp_relations.append({
                        "target": t_match["id"], "type": rel.get("type", "is_variant_of"),
                        "confidence": rel.get("confidence", 0.7),
                        "provenance": rel.get("provenance", ""),
                    })

            comp_fm = {
                "id": comp_id, "type": "component",
                "label": label, "description": desc,
                "introduced_by": paper_id,
                "component_type": comp.get("component_type", "architecture"),
                "used_by": [method_id] if method_id else [],
                "relations": comp_relations,
            }
            if not dry_run:
                _write_node(topic_dir, "nodes/components", c_slug, comp_fm)
            report["created"].append(comp_id)

    # Add composed_of relations to method
    if method_fm and method_id:
        for label, comp_id in component_id_map.items():
            method_fm["relations"].append({
                "target": comp_id, "type": "composed_of", "confidence": 1.0,
            })
        if not dry_run:
            _write_node(topic_dir, "nodes/methods", _slugify(method_data["label"]),
                        method_fm, method_data.get("description", ""))

    # ── Claims ──────────────────────────────────────────────
    claim_id_map = {}
    for claim in candidate.get("claims", []):
        label = claim.get("label", "")
        if not label:
            continue

        match, score = _find_best_match(label, "", existing_by_type.get("claim", []))

        if score >= THRESHOLD_HIGH and match:
            claim_id_map[label] = match["id"]
            report["anchored"].append({
                "type": "claim", "label": label,
                "anchored_to": match["id"], "similarity": round(score, 3),
            })
        else:
            c_slug = _slugify(label)[:40]
            claim_id = _ensure_unique_id(f"claim:{c_slug}", existing_ids)
            existing_ids.add(claim_id)
            claim_id_map[label] = claim_id

            claim_relations = []
            for rel in claim.get("relations", []):
                t_label = rel.get("target_label", "")
                t_match, t_score = _find_best_match(t_label, "", existing_by_type.get("claim", []))
                if t_match and t_score > THRESHOLD_LOW:
                    claim_relations.append({
                        "target": t_match["id"], "type": rel.get("type", "supports"),
                        "confidence": rel.get("confidence", 0.7),
                        "provenance": rel.get("provenance", ""),
                    })

            claim_fm = {
                "id": claim_id, "type": "claim",
                "label": label,
                "claim_type": claim.get("claim_type", "performance"),
                "asserted_by": paper_id,
                "confidence": claim.get("confidence", 0.8),
                "conditions": claim.get("conditions", ""),
                "year": candidate.get("_year"),
                "relations": claim_relations,
            }
            if not dry_run:
                _write_node(topic_dir, "nodes/claims", c_slug, claim_fm)
            report["created"].append(claim_id)

    # ── Evidence ────────────────────────────────────────────
    for ev in candidate.get("evidence", []):
        label = ev.get("label", "")
        if not label:
            continue
        e_slug = _slugify(label)[:40]
        ev_id = _ensure_unique_id(f"evidence:{e_slug}", existing_ids)
        existing_ids.add(ev_id)

        # Resolve supports_claim
        supports_label = ev.get("supports_claim_label", "")
        supports_id = claim_id_map.get(supports_label, "")

        ev_fm = {
            "id": ev_id, "type": "evidence",
            "label": label,
            "supports_claim": supports_id,
            "source_paper": paper_id,
            "task": ev.get("task", ""),
            "dataset": ev.get("dataset", ""),
            "metric": ev.get("metric", ""),
            "result": ev.get("result", ""),
            "baselines": ev.get("baselines", []),
            "setting": ev.get("setting", ""),
        }
        if not dry_run:
            _write_node(topic_dir, "nodes/evidence", e_slug, ev_fm)
        report["created"].append(ev_id)

    # ── Save report ─────────────────────────────────────────
    report_lines = [
        f"# Merge Report: {candidate.get('_title', slug)}",
        f"**Year:** {candidate.get('_year', '?')} | **Venue:** {candidate.get('_venue', '?')}",
        f"**Mode:** {'DRY RUN' if dry_run else 'COMMITTED'}",
        "",
        f"## Summary",
        f"- Created: {len(report['created'])} nodes",
        f"- Anchored: {len(report['anchored'])} nodes",
        "",
    ]
    if report["created"]:
        report_lines.append("## Created Nodes")
        for nid in report["created"]:
            report_lines.append(f"- `{nid}`")
        report_lines.append("")
    if report["anchored"]:
        report_lines.append("## Anchored Nodes")
        for a in report["anchored"]:
            report_lines.append(f"- [{a['type']}] \"{a.get('label', '?')}\" → `{a['anchored_to']}` (sim={a.get('similarity', '?')})")
        report_lines.append("")

    report_path = topic_dir / "reports" / f"merge_{slug}.md"
    report_path.parent.mkdir(exist_ok=True)
    if not dry_run:
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        print(f"[merge] Report → {report_path}", file=sys.stderr)

    # Append to changelog
    if not dry_run:
        changelog = topic_dir / "changelog.jsonl"
        entry = {
            "paper": slug, "title": candidate.get("_title", ""),
            "created": len(report["created"]), "anchored": len(report["anchored"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(changelog, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return report


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Anchor and merge candidates into lattice")
    add_topic_arg(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper-id", type=str, help="Candidate slug")
    group.add_argument("--all", action="store_true", help="Merge all unmerged candidates")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()

    topic_dir = resolve_topic(args.topic)
    candidates_dir = topic_dir / "candidates"
    reports_dir = topic_dir / "reports"

    if args.all:
        existing_reports = {p.stem.replace("merge_", "") for p in reports_dir.glob("merge_*.md")} if reports_dir.exists() else set()
        to_merge = [p for p in sorted(candidates_dir.glob("*.json"))
                    if p.stem not in existing_reports]
        print(f"[merge] {len(to_merge)} candidates to merge")
        for i, cp in enumerate(to_merge, 1):
            print(f"\n[merge] ({i}/{len(to_merge)}) {cp.stem}")
            try:
                report = merge_paper(cp, topic_dir, dry_run=args.dry_run)
                print(f"  Created: {len(report['created'])}, Anchored: {len(report['anchored'])}")
            except Exception as e:
                print(f"[merge] ERROR: {e}", file=sys.stderr)
    else:
        cp = candidates_dir / f"{args.paper_id}.json"
        if not cp.exists():
            print(f"Candidate not found: {cp}", file=sys.stderr)
            sys.exit(1)
        report = merge_paper(cp, topic_dir, dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False, indent=2))
