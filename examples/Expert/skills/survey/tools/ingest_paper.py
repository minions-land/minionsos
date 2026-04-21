"""
ModernKnowledge — ingest_paper.py
The core pipeline: Decompose → Anchor → Diff → Connect → Report

Given a new paper (as structured text or abstract), this tool:
1. Decomposes it into knowledge units at each lattice layer
2. Anchors each unit to the closest existing node
3. Identifies what's genuinely new vs. what maps to existing knowledge
4. Generates a diff report showing the paper's position in the lattice

Usage:
    python tools/ingest_paper.py --input <paper_description.md>

The input file should have YAML frontmatter with at least:
    title, authors, year, venue, abstract
And optionally structured method/experiment descriptions.
"""

import yaml
import json
import sys
from pathlib import Path
from difflib import SequenceMatcher

from common import resolve_topic, add_topic_arg


def load_lattice(topic_dir: Path) -> dict:
    with open(topic_dir / "lattice.json") as f:
        return json.load(f)


def parse_input(path: Path) -> dict:
    """Parse input paper file (YAML frontmatter + body)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.index("---", 3)
        meta = yaml.safe_load(text[3:end])
        meta["_body"] = text[end + 3:].strip()
    else:
        meta = {"_body": text}
    return meta


# ── Step 1: Decompose ──────────────────────────────────────────────

def decompose(paper: dict) -> dict:
    """
    Decompose a paper into candidate knowledge units at each layer.
    This is a rule-based extraction from structured input.
    For unstructured input, an LLM call would replace this.
    """
    units = {
        "paradigm": [],
        "direction": [],
        "method": [],
        "component": [],
        "claim": [],
    }

    paper_id = paper.get("paper_id", paper.get("title", "unknown"))

    # Extract method as a unit
    if paper.get("method_name"):
        units["method"].append({
            "label": paper["method_name"],
            "description": paper.get("method_description", ""),
            "architecture_type": paper.get("architecture_type", ""),
            "year": paper.get("year"),
            "source_paper": paper_id,
        })

    # Extract components
    for comp in paper.get("components", []):
        units["component"].append({
            "label": comp.get("name", ""),
            "description": comp.get("description", ""),
            "component_type": comp.get("type", ""),
            "source_paper": paper_id,
        })

    # Extract claims
    for claim in paper.get("claims", []):
        units["claim"].append({
            "label": claim.get("text", ""),
            "claim_type": claim.get("type", "performance"),
            "source_paper": paper_id,
        })

    # Infer direction from tags/topic
    if paper.get("direction"):
        units["direction"].append({
            "label": paper["direction"],
            "description": paper.get("direction_description", ""),
        })

    return units


# ── Step 2: Anchor ─────────────────────────────────────────────────

def similarity(a: str, b: str) -> float:
    """Simple text similarity using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def keyword_overlap(a: str, b: str) -> float:
    """Keyword-based similarity: Jaccard on word sets."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def combined_similarity(a_label: str, a_desc: str, b_label: str, b_desc: str) -> float:
    """Weighted combination of label similarity and description keyword overlap."""
    label_sim = similarity(a_label, b_label)
    desc_sim = keyword_overlap(a_desc, b_desc) if a_desc and b_desc else 0.0
    return 0.6 * label_sim + 0.4 * desc_sim


# PLACEHOLDER_ANCHOR_DIFF

def anchor(units: dict, lattice: dict, threshold: float = 0.35) -> dict:
    """
    For each candidate unit, find the closest existing node in the lattice.
    Returns anchoring results: {type: [{unit, best_match, score, is_new}]}
    """
    results = {}
    for ntype, candidates in units.items():
        existing = [n for n in lattice["nodes"] if n.get("type") == ntype]
        results[ntype] = []
        for unit in candidates:
            best_match = None
            best_score = 0.0
            for node in existing:
                score = combined_similarity(
                    unit.get("label", ""), unit.get("description", ""),
                    node.get("label", ""), node.get("description", ""),
                )
                if score > best_score:
                    best_score = score
                    best_match = node
            results[ntype].append({
                "unit": unit,
                "best_match": best_match,
                "score": best_score,
                "is_new": best_score < threshold,
            })
    return results


# ── Step 3: Diff ───────────────────────────────────────────────────

def diff(anchored: dict, paper: dict, lattice: dict) -> dict:
    """
    Analyze what's genuinely new vs. what maps to existing knowledge.
    Also infer relationships to existing methods based on related_methods field
    and component overlap.
    """
    report = {
        "novel_nodes": [],
        "anchored_nodes": [],
        "potential_edges": [],
        "contradictions": [],
        "temporal_context": [],
    }

    for ntype, items in anchored.items():
        for item in items:
            if item["is_new"]:
                report["novel_nodes"].append({
                    "type": ntype,
                    "label": item["unit"].get("label", ""),
                    "description": item["unit"].get("description", ""),
                    "source": item["unit"].get("source_paper", ""),
                })
            else:
                match = item["best_match"]
                report["anchored_nodes"].append({
                    "type": ntype,
                    "new_label": item["unit"].get("label", ""),
                    "matched_to": match["id"] if match else "?",
                    "matched_label": match.get("label", "?") if match else "?",
                    "similarity": round(item["score"], 3),
                })
                if ntype == "claim" and match:
                    report["potential_edges"].append({
                        "source": item["unit"].get("label", ""),
                        "target": match["id"],
                        "suggested_type": "refines",
                        "reason": f"Similar claim (sim={item['score']:.2f}), may refine or extend",
                    })

    # Infer method-level relationships from related_methods
    related = paper.get("related_methods", [])
    methods_in_lattice = {n["label"]: n for n in lattice["nodes"] if n.get("type") == "method"}
    paper_year = paper.get("year", 9999)
    method_name = paper.get("method_name", "")

    for rel_name in related:
        if rel_name in methods_in_lattice:
            existing = methods_in_lattice[rel_name]
            existing_year = existing.get("year", 0)
            # Infer relationship type based on temporal order and architecture
            if existing_year < paper_year:
                rel_type = "extends"
                reason = f"{method_name} ({paper_year}) 晚于 {rel_name} ({existing_year})"
            else:
                rel_type = "competes_with"
                reason = f"同期方法"
            report["potential_edges"].append({
                "source": method_name,
                "target": existing["id"],
                "suggested_type": rel_type,
                "reason": reason,
            })

    # Infer component-level relationships: find methods sharing components
    anchored_component_ids = set()
    for item in anchored.get("component", []):
        if not item["is_new"] and item["best_match"]:
            anchored_component_ids.add(item["best_match"]["id"])

    if anchored_component_ids:
        # Find other methods that use the same components
        shared_methods = set()
        for edge in lattice["edges"]:
            if edge["type"] == "composed_of" and edge["target"] in anchored_component_ids:
                shared_methods.add(edge["source"])
        for mid in shared_methods:
            mnode = next((n for n in lattice["nodes"] if n["id"] == mid), None)
            if mnode and mnode.get("label") != method_name:
                shared = anchored_component_ids & {
                    e["target"] for e in lattice["edges"]
                    if e["source"] == mid and e["type"] == "composed_of"
                }
                report["potential_edges"].append({
                    "source": method_name,
                    "target": mid,
                    "suggested_type": "shares_components_with",
                    "reason": f"共享组件: {', '.join(shared)}",
                })

    # Temporal context: find methods in same direction, ordered by year
    paper_direction = paper.get("direction", "")
    for n in lattice["nodes"]:
        if n.get("type") == "method" and n.get("belongs_to"):
            dir_node = next(
                (d for d in lattice["nodes"]
                 if d["id"] == n["belongs_to"] and paper_direction.lower() in d.get("label", "").lower()),
                None,
            )
            if dir_node:
                report["temporal_context"].append({
                    "method": n["label"],
                    "year": n.get("year", "?"),
                    "direction": dir_node["label"],
                })
    report["temporal_context"].sort(key=lambda x: x.get("year", 9999))

    return report


# ── Step 4: Generate Report ────────────────────────────────────────

def generate_report(paper: dict, diff_result: dict, anchored: dict) -> str:
    """Generate a human-readable diff report."""
    lines = []
    title = paper.get("title", "Unknown Paper")
    lines.append(f"# Ingest Report: {title}")
    lines.append(f"**Year:** {paper.get('year', '?')} | **Venue:** {paper.get('venue', '?')}")
    lines.append("")

    # Summary
    n_novel = len(diff_result["novel_nodes"])
    n_anchored = len(diff_result["anchored_nodes"])
    n_edges = len(diff_result["potential_edges"])
    lines.append(f"## Summary")
    lines.append(f"- **Novel knowledge units:** {n_novel}")
    lines.append(f"- **Anchored to existing:** {n_anchored}")
    lines.append(f"- **Potential new edges:** {n_edges}")
    lines.append("")

    # Novel nodes
    if diff_result["novel_nodes"]:
        lines.append("## Genuinely New Knowledge")
        for node in diff_result["novel_nodes"]:
            lines.append(f"- **[{node['type'].upper()}]** {node['label']}")
            if node["description"]:
                lines.append(f"  {node['description'][:200]}")
        lines.append("")

    # Anchored nodes
    if diff_result["anchored_nodes"]:
        lines.append("## Anchored to Existing Knowledge")
        for node in diff_result["anchored_nodes"]:
            lines.append(
                f"- **[{node['type'].upper()}]** \"{node['new_label']}\" "
                f"→ `{node['matched_to']}` ({node['matched_label']}) "
                f"[sim={node['similarity']}]"
            )
        lines.append("")

    # Potential edges
    if diff_result["potential_edges"]:
        lines.append("## Suggested New Relationships")
        for edge in diff_result["potential_edges"]:
            lines.append(
                f"- {edge['source']} --[{edge['suggested_type']}]--> "
                f"`{edge['target']}` ({edge['reason']})"
            )
        lines.append("")

    # Position assessment
    lines.append("## Position in Knowledge Lattice")
    # Find which directions this paper touches
    directions_touched = set()
    for ntype, items in anchored.items():
        for item in items:
            if not item["is_new"] and item["best_match"]:
                match = item["best_match"]
                if match.get("type") == "direction":
                    directions_touched.add(match.get("label", "?"))
                elif match.get("belongs_to"):
                    directions_touched.add(match["belongs_to"])
    if directions_touched:
        lines.append(f"**Directions touched:** {', '.join(directions_touched)}")
    lines.append("")

    # Temporal context
    if diff_result.get("temporal_context"):
        lines.append("## Temporal Context (同方向方法时间线)")
        paper_year = paper.get("year", "?")
        for entry in diff_result["temporal_context"]:
            marker = " ← YOU ARE HERE" if entry["method"] == paper.get("method_name") else ""
            lines.append(f"- {entry['year']} — {entry['method']}{marker}")
        lines.append(f"- {paper_year} — **{paper.get('method_name', '?')}** ← NEW")
        lines.append("")

    return "\n".join(lines)


# ── Main Pipeline ──────────────────────────────────────────────────

def ingest(input_path: Path, topic_dir: Path) -> str:
    """Run the full ingest pipeline."""
    paper = parse_input(input_path)
    lattice = load_lattice(topic_dir)

    # Step 1: Decompose
    units = decompose(paper)

    # Step 2: Anchor
    anchored = anchor(units, lattice)

    # Step 3: Diff
    diff_result = diff(anchored, paper, lattice)

    # Step 4: Report
    report_text = generate_report(paper, diff_result, anchored)

    # Save report
    reports_dir = topic_dir / "reports"
    reports_dir.mkdir(exist_ok=True)
    paper_id = paper.get("paper_id", "unknown")
    report_path = reports_dir / f"ingest_{paper_id}.md"
    report_path.write_text(report_text, encoding="utf-8")

    # Append to changelog
    changelog = topic_dir / "changelog.jsonl"
    changelog_entry = {
        "paper": paper_id,
        "title": paper.get("title", ""),
        "novel_nodes": len(diff_result["novel_nodes"]),
        "anchored_nodes": len(diff_result["anchored_nodes"]),
        "potential_edges": len(diff_result["potential_edges"]),
    }
    with open(changelog, "a", encoding="utf-8") as f:
        f.write(json.dumps(changelog_entry, ensure_ascii=False) + "\n")

    print(f"Report saved: {report_path}")
    print(f"Novel: {len(diff_result['novel_nodes'])}, "
          f"Anchored: {len(diff_result['anchored_nodes'])}, "
          f"New edges: {len(diff_result['potential_edges'])}")
    return report_text


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest a new paper into the knowledge lattice")
    add_topic_arg(parser)
    parser.add_argument("--input", required=True, help="Path to paper description file")
    args = parser.parse_args()
    ingest(Path(args.input), resolve_topic(args.topic))
