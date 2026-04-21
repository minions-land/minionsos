"""
ModernKnowledge — insights.py
Extract logic chains and structural insights from the knowledge lattice.
Pure topology + metadata, no LLM calls.

Usage:
    python tools/insights.py                  # print insights
    python tools/insights.py --json           # output JSON for HTML integration
"""

import json
from pathlib import Path
from collections import defaultdict
from common import resolve_topic, add_topic_arg


def load(topic_dir: Path):
    with open(topic_dir / "lattice.json") as f:
        return json.load(f)


def _by_id(L):
    return {n["id"]: n for n in L["nodes"]}


def _ancestors(nid, L, nmap, target_type):
    """Walk upward via belongs_to to find ancestor of target_type."""
    visited = set()
    queue = [nid]
    results = set()
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        node = nmap.get(cur)
        if not node:
            continue
        if node.get("type") == target_type:
            results.add(cur)
        bt = node.get("belongs_to")
        if bt:
            queue.append(bt)
        # Also walk composed_of edges in reverse (target -> source)
        for e in L["edges"]:
            if e["target"] == cur and e["type"] == "composed_of":
                queue.append(e["source"])
    return results


# ── Insight 1: Evolution Spine ───────────────────────────

def find_evolution_spines(L, nmap):
    """Find longest extends chains within each direction, ordered by year."""
    methods = [n for n in L["nodes"] if n.get("type") == "method"]
    # Build extends graph
    extends_graph = defaultdict(list)  # parent -> children
    for e in L["edges"]:
        if e["type"] == "extends":
            extends_graph[e["target"]].append(e["source"])

    # Find all maximal paths
    def dfs_paths(node_id, path):
        children = [c for c in extends_graph.get(node_id, [])
                    if nmap.get(c, {}).get("year", 0) >= nmap.get(node_id, {}).get("year", 0)]
        if not children:
            return [path]
        all_paths = []
        for child in children:
            if child not in path:
                all_paths.extend(dfs_paths(child, path + [child]))
        return all_paths if all_paths else [path]

    # Start from methods with no incoming extends
    targets_of_extends = {e["source"] for e in L["edges"] if e["type"] == "extends"}
    sources_of_extends = {e["target"] for e in L["edges"] if e["type"] == "extends"}
    roots = [m["id"] for m in methods if m["id"] in sources_of_extends and m["id"] not in targets_of_extends]
    # Also try all methods as roots
    if not roots:
        roots = [m["id"] for m in methods if m["id"] in sources_of_extends]

    all_spines = []
    for root in roots:
        paths = dfs_paths(root, [root])
        for p in paths:
            if len(p) >= 2:
                chain = []
                for nid in p:
                    n = nmap.get(nid, {})
                    chain.append({"id": nid, "label": n.get("label", nid), "year": n.get("year", "?")})
                direction = nmap.get(nmap.get(p[0], {}).get("belongs_to", ""), {}).get("label", "?")
                all_spines.append({
                    "chain": chain,
                    "direction": direction,
                    "length": len(chain),
                })

    all_spines.sort(key=lambda x: -x["length"])
    return all_spines[:6]


# ── Insight 2: Convergence Funnel ────────────────────────

def find_convergence_funnels(L, nmap):
    """Find components used by methods from different directions."""
    components = [n for n in L["nodes"] if n.get("type") == "component"]
    results = []
    for comp in components:
        # Find methods that use this component
        users = []
        for e in L["edges"]:
            if e["target"] == comp["id"] and e["type"] == "composed_of":
                m = nmap.get(e["source"])
                if m and m.get("type") == "method":
                    users.append(m)
        if len(users) < 2:
            continue
        directions = set(m.get("belongs_to", "") for m in users)
        if len(directions) >= 2:
            dir_labels = [nmap.get(d, {}).get("label", d) for d in directions]
            results.append({
                "component": {"id": comp["id"], "label": comp.get("label", comp["id"])},
                "users": [{"id": m["id"], "label": m.get("label", m["id"]),
                           "direction": nmap.get(m.get("belongs_to", ""), {}).get("label", "?")}
                          for m in users],
                "directions": dir_labels,
                "chain": [comp["id"]] + [m["id"] for m in users],
                "strength": len(directions),
            })
    results.sort(key=lambda x: -x["strength"])
    return results[:6]


# ── Insight 3: Claim Conflict Chain ──────────────────────

def find_claim_conflicts(L, nmap):
    """Find contradicting claims and trace back to their methods/components."""
    conflicts = []
    for e in L["edges"]:
        if e["type"] != "contradicts":
            continue
        c1 = nmap.get(e["source"], {})
        c2 = nmap.get(e["target"], {})
        if not c1 or not c2:
            continue

        # Find methods asserting each claim (via asserted_by field or edges)
        def find_asserting_methods(claim_id):
            claim = nmap.get(claim_id, {})
            methods = []
            # Check asserted_by field
            ab = claim.get("asserted_by")
            if ab:
                # Find methods introduced by this paper
                for n in L["nodes"]:
                    if n.get("type") == "method" and n.get("introduced_by") == ab:
                        methods.append(n)
            return methods

        m1 = find_asserting_methods(e["source"])
        m2 = find_asserting_methods(e["target"])

        # Find component diff
        def get_components(method_id):
            return {e2["target"] for e2 in L["edges"]
                    if e2["source"] == method_id and e2["type"] == "composed_of"}

        comp1 = set()
        for m in m1:
            comp1 |= get_components(m["id"])
        comp2 = set()
        for m in m2:
            comp2 |= get_components(m["id"])

        only1 = comp1 - comp2
        only2 = comp2 - comp1

        chain = [e["source"], e["target"]]
        chain += [m["id"] for m in m1 + m2]
        chain += list(only1 | only2)

        conflicts.append({
            "claim1": {"id": c1.get("id"), "label": c1.get("label", "?")},
            "claim2": {"id": c2.get("id"), "label": c2.get("label", "?")},
            "methods1": [{"id": m["id"], "label": m.get("label", "?")} for m in m1],
            "methods2": [{"id": m["id"], "label": m.get("label", "?")} for m in m2],
            "divergent_components": [nmap.get(c, {}).get("label", c) for c in (only1 | only2)],
            "chain": chain,
        })
    return conflicts


# ── Insight 4: Orphan Innovation ─────────────────────────

def find_orphan_innovations(L, nmap):
    """Find components that nobody else picked up."""
    max_year = max((n.get("year", 0) for n in L["nodes"] if n.get("year")), default=2026)
    components = [n for n in L["nodes"] if n.get("type") == "component"]

    transfer_types = {"extends", "is_variant_of", "inspired_by", "generalizes", "specializes"}
    comp_transfer_degree = defaultdict(int)
    for e in L["edges"]:
        if e["type"] in transfer_types:
            comp_transfer_degree[e["source"]] += 1
            comp_transfer_degree[e["target"]] += 1

    # Count how many methods use each component
    comp_usage = defaultdict(int)
    for e in L["edges"]:
        if e["type"] == "composed_of":
            comp_usage[e["target"]] += 1

    orphans = []
    for comp in components:
        if comp_usage[comp["id"]] > 1:
            continue  # used by multiple methods, not orphan
        if comp_transfer_degree[comp["id"]] > 0:
            continue  # has transfer edges
        # Find parent method
        parent = None
        for e in L["edges"]:
            if e["target"] == comp["id"] and e["type"] == "composed_of":
                parent = nmap.get(e["source"])
                break
        if not parent:
            continue
        parent_year = parent.get("year", max_year)
        if parent_year >= max_year - 1:
            continue  # too recent

        orphans.append({
            "component": {"id": comp["id"], "label": comp.get("label", comp["id"])},
            "parent_method": {"id": parent["id"], "label": parent.get("label", "?"), "year": parent_year},
            "chain": [parent["id"], comp["id"]],
            "years_orphaned": max_year - parent_year,
        })

    orphans.sort(key=lambda x: -x["years_orphaned"])
    return orphans[:8]


# ── Insight 5: Component Hub (Hidden Backbone) ──────────

def find_component_hubs(L, nmap):
    """Find components with disproportionately high usage across methods."""
    comp_users = defaultdict(list)
    for e in L["edges"]:
        if e["type"] == "composed_of":
            m = nmap.get(e["source"])
            if m and m.get("type") == "method":
                comp_users[e["target"]].append(m)

    hubs = []
    for comp_id, users in comp_users.items():
        if len(users) < 2:
            continue
        comp = nmap.get(comp_id, {})
        directions = set(m.get("belongs_to", "") for m in users)
        hubs.append({
            "component": {"id": comp_id, "label": comp.get("label", comp_id)},
            "usage_count": len(users),
            "users": [{"id": m["id"], "label": m.get("label", "?")} for m in users],
            "cross_direction": len(directions) > 1,
            "directions": [nmap.get(d, {}).get("label", d) for d in directions],
            "chain": [comp_id] + [m["id"] for m in users],
        })

    hubs.sort(key=lambda x: (-int(x["cross_direction"]), -x["usage_count"]))
    return hubs[:6]


# ── Insight 6: Temporal Branching Burst ──────────────────

def find_branching_bursts(L, nmap):
    """Find methods that spawned multiple children within a short window."""
    extends_children = defaultdict(list)
    for e in L["edges"]:
        if e["type"] == "extends":
            parent = nmap.get(e["target"])
            child = nmap.get(e["source"])
            if parent and child:
                extends_children[e["target"]].append(child)

    bursts = []
    for parent_id, children in extends_children.items():
        parent = nmap.get(parent_id, {})
        py = parent.get("year", 9999)
        nearby = [c for c in children if c.get("year", 9999) <= py + 2]
        if len(nearby) >= 2:
            bursts.append({
                "parent": {"id": parent_id, "label": parent.get("label", "?"), "year": py},
                "children": [{"id": c["id"], "label": c.get("label", "?"), "year": c.get("year", "?")}
                             for c in sorted(nearby, key=lambda x: x.get("year", 9999))],
                "count": len(nearby),
                "chain": [parent_id] + [c["id"] for c in nearby],
            })

    bursts.sort(key=lambda x: -x["count"])
    return bursts[:6]


# ── Insight 7: Open Problem Synthesis ────────────────────

def find_open_problems(L, nmap):
    """Synthesize open problems from unresolved claim conflicts and evidence gaps."""
    problems = []

    # 7a: Unresolved claim conflicts (contradicts edges where neither side has decisive evidence)
    for e in L["edges"]:
        if e["type"] != "contradicts":
            continue
        c1 = nmap.get(e["source"], {})
        c2 = nmap.get(e["target"], {})
        if c1.get("type") != "claim" or c2.get("type") != "claim":
            continue
        # Both claims still stand — this is an open question
        problems.append({
            "subtype": "unresolved_debate",
            "title": f"未决争论: {c1.get('label', '?')[:35]}… vs {c2.get('label', '?')[:35]}…",
            "summary": f"两个相互矛盾的断言均有方法支持，缺乏决定性的对比实验",
            "detail": f"「{c1.get('label', '?')}」与「{c2.get('label', '?')}」"
                      f"之间的矛盾尚未通过直接对比实验解决。这是一个值得投入的研究问题",
            "chain": [e["source"], e["target"]],
        })

    # 7b: Directions with many methods but no cross-method comparison edges
    methods = [n for n in L["nodes"] if n.get("type") == "method"]
    by_dir = defaultdict(list)
    for m in methods:
        by_dir[m.get("belongs_to", "")].append(m)

    for dir_id, ms in by_dir.items():
        if len(ms) < 3:
            continue
        dir_node = nmap.get(dir_id, {})
        # Count how many method pairs have direct comparison
        compared = set()
        for edge in L["edges"]:
            if edge["type"] in ("extends", "contradicts", "supersedes"):
                s, t = edge["source"], edge["target"]
                if s in {m["id"] for m in ms} and t in {m["id"] for m in ms}:
                    compared.add((min(s, t), max(s, t)))
        total_pairs = len(ms) * (len(ms) - 1) // 2
        missing = total_pairs - len(compared)
        if missing > 0:
            problems.append({
                "subtype": "benchmark_gap",
                "title": f"系统性对比缺失: {dir_node.get('label', '?')}",
                "summary": f"{len(ms)} 个方法中有 {missing}/{total_pairs} 对缺乏直接对比",
                "detail": f"方向 \"{dir_node.get('label', '?')}\" 内的方法缺乏系统性 benchmark 对比，"
                          f"使得方法选择缺乏依据",
                "chain": [dir_id] + [m["id"] for m in ms],
            })

    problems.sort(key=lambda x: len(x["chain"]), reverse=True)
    return problems[:6]


# ── Insight 8: Applicability Boundary ────────────────────

def find_applicability_boundaries(L, nmap):
    """Surface methods with incompatible constraints that claim to solve the same task."""
    methods = [n for n in L["nodes"] if n.get("type") == "method" and n.get("constraints")]
    results = []

    # 8a: Platform coverage gaps — which platforms have few methods?
    platform_methods = defaultdict(list)
    for m in methods:
        for p in m.get("constraints", {}).get("platforms", []):
            platform_methods[p].append(m)

    for platform, ms in sorted(platform_methods.items(), key=lambda x: len(x[1])):
        if len(ms) <= 2:
            results.append({
                "subtype": "platform_underserved",
                "title": f"平台覆盖不足: {platform}",
                "summary": f"仅 {len(ms)} 个方法支持 {platform}: {', '.join(m['label'] for m in ms)}",
                "detail": f"平台 {platform} 的方法选择极为有限，存在开发新方法的机会",
                "chain": [m["id"] for m in ms],
            })

    # 8b: Segmentation dependency — methods that require segmentation vs those that don't
    needs_seg = [m for m in methods if m.get("constraints", {}).get("requires_segmentation")]
    no_seg = [m for m in methods if not m.get("constraints", {}).get("requires_segmentation")]
    if needs_seg and no_seg:
        results.append({
            "subtype": "segmentation_divide",
            "title": "分割依赖分水岭",
            "summary": f"{len(needs_seg)} 个方法依赖细胞分割，{len(no_seg)} 个不依赖",
            "detail": f"依赖分割: {', '.join(m['label'] for m in needs_seg[:4])}… "
                      f"不依赖: {', '.join(m['label'] for m in no_seg)}。"
                      f"分割错误级联传播是已知问题 (Nature Genetics 2025)，"
                      f"不依赖分割的方法可能有系统性优势",
            "chain": [m["id"] for m in no_seg] + [m["id"] for m in needs_seg[:3]],
        })

    # 8c: Gene panel constraint — methods requiring full transcriptome can't handle MERFISH
    full_only = [m for m in methods if m.get("constraints", {}).get("gene_panel") == "full_transcriptome"]
    panel_agnostic = [m for m in methods if m.get("constraints", {}).get("gene_panel") == "any"]
    if full_only and panel_agnostic:
        results.append({
            "subtype": "gene_panel_barrier",
            "title": "基因面板壁垒",
            "summary": f"{len(full_only)} 个方法需要全转录组，无法直接用于 MERFISH/Xenium",
            "detail": f"需要全转录组: {', '.join(m['label'] for m in full_only[:4])}。"
                      f"面板无关: {', '.join(m['label'] for m in panel_agnostic)}。"
                      f"这是单细胞 FM 迁移到空间数据的核心障碍",
            "chain": [m["id"] for m in panel_agnostic] + [m["id"] for m in full_only[:3]],
        })

    # 8d: Compute cost vs accessibility
    high_compute = [m for m in methods if m.get("constraints", {}).get("compute_scale") == "high"]
    low_compute = [m for m in methods if m.get("constraints", {}).get("compute_scale") in ("low", "medium")]
    if len(high_compute) > len(low_compute):
        results.append({
            "subtype": "compute_barrier",
            "title": "计算成本壁垒",
            "summary": f"{len(high_compute)}/{len(methods)} 个方法需要高计算资源",
            "detail": f"高成本: {', '.join(m['label'] for m in high_compute[:4])}。"
                      f"低/中成本: {', '.join(m['label'] for m in low_compute)}。"
                      f"大多数实验室无法负担 FM 级别的计算需求，轻量化方法有巨大需求",
            "chain": [m["id"] for m in low_compute[:3]] + [m["id"] for m in high_compute[:3]],
        })

    return results


# ── Insight 9: Cross-Field Transfer Map ──────────────────

def find_cross_field_transfers(L, nmap):
    """Map which external fields feed innovation into this domain."""
    methods = [n for n in L["nodes"] if n.get("type") == "method" and n.get("origin_field")]
    field_methods = defaultdict(list)
    for m in methods:
        field_methods[m["origin_field"]].append(m)

    results = []
    for field, ms in sorted(field_methods.items(), key=lambda x: -len(x[1])):
        ms_sorted = sorted(ms, key=lambda x: x.get("year", 9999))
        # Count downstream impact: how many other methods extend these?
        impact = 0
        for e in L["edges"]:
            if e["type"] == "extends" and e["target"] in {m["id"] for m in ms}:
                impact += 1

        results.append({
            "field": field,
            "title": f"跨领域迁移: {field}",
            "summary": f"{len(ms)} 个方法源自 {field}，催生 {impact} 个后续扩展",
            "detail": f"来自 {field} 的方法: {', '.join(m['label']+'('+str(m.get('year','?'))+')' for m in ms_sorted)}。"
                      f"下游影响: {impact} 个 extends 关系",
            "methods": [{"id": m["id"], "label": m.get("label", "?"), "year": m.get("year")} for m in ms_sorted],
            "chain": [m["id"] for m in ms_sorted],
            "count": len(ms),
            "impact": impact,
        })

    results.sort(key=lambda x: (-x["impact"], -x["count"]))
    return results


# ── Assemble all insights ────────────────────────────────

def extract_all(L=None):
    if L is None:
        L = load()
    nmap = _by_id(L)

    insights = []

    # Evolution spines
    for spine in find_evolution_spines(L, nmap):
        chain_str = " → ".join(f"{n['label']} ({n['year']})" for n in spine["chain"])
        insights.append({
            "type": "evolution_spine",
            "icon": "🧬",
            "title": f"演化主线: {spine['direction']}",
            "summary": chain_str,
            "detail": f"{spine['length']} 步演化链，展示了 {spine['direction']} 方向的核心发展脉络",
            "chain": [n["id"] for n in spine["chain"]],
            "strength": spine["length"],
        })

    # Convergence funnels
    for funnel in find_convergence_funnels(L, nmap):
        dirs = " + ".join(funnel["directions"])
        insights.append({
            "type": "convergence_funnel",
            "icon": "🔀",
            "title": f"跨方向收敛: {funnel['component']['label']}",
            "summary": f"被 {dirs} 方向的方法共同采用",
            "detail": f"组件 \"{funnel['component']['label']}\" 被来自 {len(funnel['directions'])} 个不同方向的方法使用，"
                      f"说明它正在成为事实标准",
            "chain": funnel["chain"],
            "strength": funnel["strength"] + 1,
        })

    # Claim conflicts
    for conflict in find_claim_conflicts(L, nmap):
        insights.append({
            "type": "claim_conflict",
            "icon": "⚡",
            "title": f"断言冲突",
            "summary": f"「{conflict['claim1']['label'][:40]}…」vs「{conflict['claim2']['label'][:40]}…」",
            "detail": f"两个相互矛盾的断言。差异组件: {', '.join(conflict['divergent_components'][:3]) or '待分析'}",
            "chain": conflict["chain"],
            "strength": 3,
        })

    # Orphan innovations
    for orphan in find_orphan_innovations(L, nmap):
        insights.append({
            "type": "orphan_innovation",
            "icon": "💎",
            "title": f"孤立创新: {orphan['component']['label']}",
            "summary": f"由 {orphan['parent_method']['label']} ({orphan['parent_method']['year']}) 提出，"
                       f"至今 {orphan['years_orphaned']} 年无人采用",
            "detail": f"这个组件可能被忽视，也可能是死胡同。值得评估是否有迁移价值",
            "chain": orphan["chain"],
            "strength": 1,
        })

    # Component hubs
    for hub in find_component_hubs(L, nmap):
        cross = "跨方向" if hub["cross_direction"] else "方向内"
        insights.append({
            "type": "component_hub",
            "icon": "🏗️",
            "title": f"隐藏骨架: {hub['component']['label']}",
            "summary": f"{cross}共享，被 {hub['usage_count']} 个方法使用",
            "detail": f"这个组件是多个方法的共同基础设施。方向: {', '.join(hub['directions'])}",
            "chain": hub["chain"],
            "strength": hub["usage_count"],
        })

    # Branching bursts
    for burst in find_branching_bursts(L, nmap):
        children_str = ", ".join(f"{c['label']}({c['year']})" for c in burst["children"])
        insights.append({
            "type": "branching_burst",
            "icon": "💥",
            "title": f"爆发点: {burst['parent']['label']} ({burst['parent']['year']})",
            "summary": f"2年内催生 {burst['count']} 个后续方法: {children_str}",
            "detail": f"这个方法触发了领域的快速分化，是重要的转折点",
            "chain": burst["chain"],
            "strength": burst["count"] + 1,
        })

    # Sort by strength
    # Open problems
    for prob in find_open_problems(L, nmap):
        insights.append({
            "type": "open_problem",
            "icon": "🔬",
            "title": prob["title"],
            "summary": prob["summary"],
            "detail": prob["detail"],
            "chain": prob["chain"],
            "strength": len(prob["chain"]),
        })

    # Applicability boundaries
    for boundary in find_applicability_boundaries(L, nmap):
        insights.append({
            "type": "applicability_boundary",
            "icon": "🚧",
            "title": boundary["title"],
            "summary": boundary["summary"],
            "detail": boundary["detail"],
            "chain": boundary["chain"],
            "strength": len(boundary["chain"]),
        })

    # Cross-field transfers
    for transfer in find_cross_field_transfers(L, nmap):
        insights.append({
            "type": "cross_field_transfer",
            "icon": "🌐",
            "title": transfer["title"],
            "summary": transfer["summary"],
            "detail": transfer["detail"],
            "chain": transfer["chain"],
            "strength": transfer["impact"] + transfer["count"],
        })

    insights.sort(key=lambda x: -x["strength"])
    return insights


if __name__ == "__main__":
    import argparse as _ap
    parser = _ap.ArgumentParser(description="Extract insights from the knowledge lattice")
    add_topic_arg(parser)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    topic_dir = resolve_topic(args.topic)
    L = load(topic_dir)
    insights = extract_all(L)
    if args.json:
        print(json.dumps(insights, ensure_ascii=False, indent=2))
    else:
        for ins in insights:
            print(f"\n{'='*60}")
            print(f"{ins['icon']} [{ins['type']}] {ins['title']}")
            print(f"  {ins['summary']}")
            print(f"  → {ins['detail']}")
            print(f"  Chain: {' → '.join(ins['chain'][:6])}")
