"""
ModernKnowledge — build_lattice.py
Compiles individual node markdown files into lattice.json.
Reads YAML frontmatter from each .md file under nodes/ and papers/.

Usage:
    python tools/build_lattice.py --topic spatial-transcriptomics
"""

import yaml
import json
import argparse
from pathlib import Path
from common import resolve_topic, add_topic_arg


def parse_frontmatter(path: Path) -> dict | None:
    """Extract YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.index("---", 3)
    return yaml.safe_load(text[3:end])


def collect_nodes(topic_dir: Path) -> list[dict]:
    """Walk nodes/ and papers/ directories, parse all .md files."""
    nodes = []
    nodes_dir = topic_dir / "nodes"
    papers_dir = topic_dir / "papers"
    for subdir in sorted(nodes_dir.iterdir()):
        if not subdir.is_dir():
            continue
        for md in sorted(subdir.glob("*.md")):
            data = parse_frontmatter(md)
            if data:
                data["_source_file"] = str(md.relative_to(topic_dir))
                nodes.append(data)
    for md in sorted(papers_dir.glob("*.md")):
        data = parse_frontmatter(md)
        if data:
            data["_source_file"] = str(md.relative_to(topic_dir))
            nodes.append(data)
    return nodes


def extract_edges(nodes: list[dict]) -> list[dict]:
    """Extract edges from 'relations' fields and infer cross-layer edges.

    Edge direction convention: arrows point in the direction of knowledge flow.
    For 'extends', 'inspired_by', 'branches_from', 'transfers_from' the node
    declaring the relation is the *descendant* — the arrow should originate from
    the ancestor (the target in the YAML) and point to the descendant (the node
    that wrote the relation).  We swap source/target for these types so the
    rendered arrow goes old → new.
    """
    # Edge types where the declaring node is the descendant (new work),
    # and rel["target"] is the ancestor (prior work).
    # Arrow should go ancestor → descendant, so we swap.
    SWAP_TYPES = {"extends", "inspired_by", "branches_from", "transfers_from", "combines"}

    edges = []
    seen = set()
    for node in nodes:
        for rel in node.get("relations", []):
            etype = rel["type"]
            if etype in SWAP_TYPES:
                src, tgt = rel["target"], node["id"]
            else:
                src, tgt = node["id"], rel["target"]
            edge = {
                "source": src,
                "target": tgt,
                "type": etype,
                "confidence": rel.get("confidence", 1.0),
                "provenance": rel.get("provenance", ""),
            }
            key = (edge["source"], edge["target"], edge["type"])
            if key not in seen:
                edges.append(edge)
                seen.add(key)

    # Infer method → claim 'asserts' edges:
    methods = {n["id"]: n for n in nodes if n.get("type") == "method"}
    claims = [n for n in nodes if n.get("type") == "claim"]
    for claim in claims:
        asserted_by = claim.get("asserted_by", "")
        if not asserted_by:
            continue
        for mid, method in methods.items():
            if method.get("introduced_by") == asserted_by:
                key = (mid, claim["id"], "asserts")
                if key not in seen:
                    edges.append({
                        "source": mid, "target": claim["id"],
                        "type": "asserts", "confidence": 0.9,
                        "provenance": f"inferred: both linked to {asserted_by}",
                    })
                    seen.add(key)

    return edges


def build(topic_dir: Path) -> dict:
    """Main build: collect nodes, extract edges, write lattice.json."""
    nodes = collect_nodes(topic_dir)
    edges = extract_edges(nodes)

    clean_nodes = []
    for n in nodes:
        out = {k: v for k, v in n.items() if k != "relations" and not k.startswith("_")}
        clean_nodes.append(out)

    lattice = {
        "meta": {
            "version": "0.1.0",
            "node_count": len(clean_nodes),
            "edge_count": len(edges),
        },
        "nodes": clean_nodes,
        "edges": edges,
    }

    output = topic_dir / "lattice.json"
    output.write_text(json.dumps(lattice, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built lattice: {len(clean_nodes)} nodes, {len(edges)} edges → {output}")
    return lattice


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build lattice.json from node files")
    add_topic_arg(parser)
    args = parser.parse_args()
    build(resolve_topic(args.topic))
