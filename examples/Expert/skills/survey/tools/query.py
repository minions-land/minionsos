"""
ModernKnowledge — query.py
Query the knowledge lattice from the command line.

Usage:
    python tools/query.py --topic spatial-transcriptomics --stats
    python tools/query.py --topic spatial-transcriptomics --method novae
    python tools/query.py --topic spatial-transcriptomics --timeline
"""

import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from common import resolve_topic, add_topic_arg


def load(topic_dir: Path):
    with open(topic_dir / "lattice.json") as f:
        return json.load(f)


def cmd_stats(L):
    types = Counter(n.get("type", "?") for n in L["nodes"])
    etypes = Counter(e["type"] for e in L["edges"])
    print(f"=== Knowledge Lattice: {L['meta']['node_count']} nodes, {L['meta']['edge_count']} edges ===\n")
    print("Nodes by type:")
    for t in ["paradigm", "direction", "method", "component", "claim", "paper"]:
        print(f"  L{['paradigm','direction','method','component','claim','paper'].index(t)}: {t:20s} {types.get(t, 0)}")
    print(f"\nEdges by type:")
    for t, c in sorted(etypes.items(), key=lambda x: -x[1]):
        print(f"  {t:30s} {c}")


def cmd_node(L, node_id):
    node = next((n for n in L["nodes"] if n["id"] == node_id), None)
    if not node:
        # fuzzy match
        matches = [n for n in L["nodes"] if node_id.lower() in n.get("id", "").lower() or node_id.lower() in n.get("label", "").lower()]
        if not matches:
            print(f"Node '{node_id}' not found.")
            return
        if len(matches) > 1:
            print(f"Multiple matches:")
            for m in matches:
                print(f"  {m['id']} — {m.get('label', '')}")
            return
        node = matches[0]

    print(f"=== {node['id']} ===")
    print(f"Type: {node.get('type', '?')}")
    print(f"Label: {node.get('label', '?')}")
    if node.get("description"):
        print(f"Description: {node['description']}")
    if node.get("belongs_to"):
        print(f"Belongs to: {node['belongs_to']}")
    if node.get("year"):
        print(f"Year: {node['year']}")

    # Find edges
    outgoing = [e for e in L["edges"] if e["source"] == node["id"]]
    incoming = [e for e in L["edges"] if e["target"] == node["id"]]

    if outgoing:
        print(f"\nOutgoing edges ({len(outgoing)}):")
        for e in outgoing:
            tgt = next((n for n in L["nodes"] if n["id"] == e["target"]), {})
            print(f"  --[{e['type']}]--> {e['target']} ({tgt.get('label', '?')})")

    if incoming:
        print(f"\nIncoming edges ({len(incoming)}):")
        for e in incoming:
            src = next((n for n in L["nodes"] if n["id"] == e["source"]), {})
            print(f"  <--[{e['type']}]-- {e['source']} ({src.get('label', '?')})")


def cmd_method(L, name):
    methods = [n for n in L["nodes"] if n.get("type") == "method" and name.lower() in n.get("label", "").lower()]
    if not methods:
        print(f"No method matching '{name}'")
        return
    for m in methods:
        cmd_node(L, m["id"])
        print()


def cmd_direction(L, name):
    dirs = [n for n in L["nodes"] if n.get("type") == "direction" and name.lower() in n.get("label", "").lower()]
    if not dirs:
        print(f"No direction matching '{name}'")
        return
    for d in dirs:
        print(f"=== {d['label']} ===")
        print(f"Belongs to: {d.get('belongs_to', '?')}")
        print(f"Status: {d.get('status', '?')}")
        if d.get("key_question"):
            print(f"Key question: {d['key_question']}")
        # Find methods in this direction
        methods = [n for n in L["nodes"] if n.get("type") == "method" and n.get("belongs_to") == d["id"]]
        methods.sort(key=lambda x: x.get("year", 9999))
        print(f"\nMethods ({len(methods)}):")
        for m in methods:
            print(f"  {m.get('year', '?')} — {m['label']} ({m.get('architecture_type', '?')})")
        print()


def cmd_timeline(L):
    methods = [n for n in L["nodes"] if n.get("type") == "method"]
    methods.sort(key=lambda x: x.get("year", 9999))
    # Group by direction
    by_dir = defaultdict(list)
    for m in methods:
        by_dir[m.get("belongs_to", "?")].append(m)

    print("=== Temporal Evolution ===\n")
    for dir_id, ms in sorted(by_dir.items()):
        dir_node = next((n for n in L["nodes"] if n["id"] == dir_id), {})
        print(f"[{dir_node.get('label', dir_id)}]")
        for m in ms:
            components = [e["target"] for e in L["edges"] if e["source"] == m["id"] and e["type"] == "composed_of"]
            comp_labels = []
            for cid in components[:3]:
                cn = next((n for n in L["nodes"] if n["id"] == cid), {})
                comp_labels.append(cn.get("label", cid))
            comp_str = ", ".join(comp_labels)
            print(f"  {m.get('year', '?')} — {m['label']:20s} [{comp_str}]")
        print()


def cmd_gaps(L):
    """Identify research gaps from the lattice structure."""
    print("=== Research Gaps (inferred from lattice) ===\n")

    # 1. Methods without cross-direction comparison
    methods = [n for n in L["nodes"] if n.get("type") == "method"]
    by_dir = defaultdict(list)
    for m in methods:
        by_dir[m.get("belongs_to", "?")].append(m)

    # Find directions with competing methods that lack comparison edges
    print("1. Missing cross-method comparisons:")
    for dir_id, ms in by_dir.items():
        if len(ms) < 2:
            continue
        dir_node = next((n for n in L["nodes"] if n["id"] == dir_id), {})
        for i, m1 in enumerate(ms):
            for m2 in ms[i+1:]:
                has_edge = any(
                    (e["source"] == m1["id"] and e["target"] == m2["id"]) or
                    (e["source"] == m2["id"] and e["target"] == m1["id"])
                    for e in L["edges"]
                )
                if not has_edge:
                    print(f"  [{dir_node.get('label', '?')}] {m1['label']} vs {m2['label']} — no direct comparison")

    # 2. Claims without contradictions (potential blind spots)
    claims = [n for n in L["nodes"] if n.get("type") == "claim"]
    claims_with_contradiction = set()
    for e in L["edges"]:
        if e["type"] == "contradicts":
            claims_with_contradiction.add(e["source"])
            claims_with_contradiction.add(e["target"])

    print(f"\n2. Unchallenged claims ({len(claims) - len(claims_with_contradiction)}/{len(claims)}):")
    for c in claims:
        if c["id"] not in claims_with_contradiction:
            print(f"  {c['label'][:80]}")

    # 3. Components used by only one method (potential for transfer)
    comp_usage = Counter()
    for e in L["edges"]:
        if e["type"] == "composed_of":
            comp_usage[e["target"]] += 1
    print(f"\n3. Unique components (used by only 1 method — transfer opportunities):")
    for cid, count in comp_usage.items():
        if count == 1:
            cn = next((n for n in L["nodes"] if n["id"] == cid), {})
            print(f"  {cn.get('label', cid)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the knowledge lattice")
    add_topic_arg(parser)
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--node", type=str)
    parser.add_argument("--method", type=str)
    parser.add_argument("--direction", type=str)
    parser.add_argument("--timeline", action="store_true")
    parser.add_argument("--gaps", action="store_true")
    args = parser.parse_args()

    L = load(resolve_topic(args.topic))
    if args.stats:
        cmd_stats(L)
    elif args.node:
        cmd_node(L, args.node)
    elif args.method:
        cmd_method(L, args.method)
    elif args.direction:
        cmd_direction(L, args.direction)
    elif args.timeline:
        cmd_timeline(L)
    elif args.gaps:
        cmd_gaps(L)
    else:
        cmd_stats(L)
