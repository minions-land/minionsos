# Node YAML Templates

All nodes are `.md` files with YAML frontmatter under `topics/<topic>/nodes/<layer>/` or `topics/<topic>/papers/`.

## Paradigm

```yaml
---
id: "paradigm:deep-learning"
type: paradigm
label: "Deep Learning"
description: "基于深度神经网络的表示学习范式"
status: active
era: "2012-present"
---
One paragraph of context.
```

## Direction

```yaml
---
id: "direction:spatial-gnn"
type: direction
label: "Spatial Graph Neural Networks"
description: "利用图神经网络建模细胞空间邻域关系"
belongs_to: "paradigm:deep-learning"
status: active           # active | emerging | mature | declining
active_period: "2021-present"
key_question: "如何有效编码细胞间的空间关系?"
relations:
  - target: "direction:other-direction"
    type: branches_from  # or converges_with
    confidence: 0.85
    provenance: "why this relationship exists"
---
```

## Method

```yaml
---
id: "method:novae"
type: method
label: "Novae"
description: "首个专门为空间转录组设计的图基础模型"
belongs_to: "direction:spatial-fm"
introduced_by: "paper:novae-2025"
year: 2025
venue: "Nature Methods"
architecture_type: "graph-attention-network"
pretraining_scale: "30M cells"
constraints:
  spatial_input: true
  gene_panel: "any"            # "full_transcriptome" | "any" | "targeted"
  requires_segmentation: true
  requires_reference: false
  compute_scale: "high"        # "low" | "medium" | "high"
  platforms: ["MERFISH", "Xenium"]
origin_field: "graph-theory"
relations:
  - target: "component:delaunay-spatial-graph"
    type: composed_of
    confidence: 1.0
  - target: "method:spagcn"
    type: extends              # target = the ancestor (will be swapped)
    confidence: 0.85
    provenance: "paper:novae-2025 — extends SpaGCN to FM scale"
---
One paragraph summary.
```

## Component

```yaml
---
id: "component:delaunay-spatial-graph"
type: component
label: "Delaunay Triangulation Spatial Graph"
description: "通过 Delaunay 三角化将细胞空间坐标转化为图结构"
introduced_by: "paper:novae-2025"
component_type: "spatial-encoding"
used_by: ["method:novae"]
relations:
  - target: "component:spatial-neighborhood-graph"
    type: specializes          # or generalizes, is_variant_of, transfers_from
    confidence: 0.9
    provenance: "Delaunay is a specific way to build spatial graphs"
---
```

### `component_type` vocabulary
`architecture | encoding | training-task | strategy | framework | algorithm | design-principle | capability`

## Claim

```yaml
---
id: "claim:spatial-context-improves"
type: claim
label: "空间上下文信息显著改善细胞类型注释"
claim_type: performance        # performance | scalability | efficiency | generalization | novelty | limitation
asserted_by: "paper:stellar-2022"
confidence: 0.9
conditions: "尤其在基因面板有限时"
year: 2022
relations:
  - target: "claim:other-claim"
    type: contradicts          # or supports, refines
    confidence: 0.8
    provenance: "why they conflict"
---
```

## Paper

```yaml
---
id: "paper:novae-2025"
type: paper
title: "Novae: a graph-based foundation model for spatial transcriptomics"
authors: ["Quentin Blampey et al."]
year: 2025
venue: "Nature Methods"
tags: ["spatial-transcriptomics", "foundation-model"]
---
```

## Edge-Direction Reminder

For `extends`, `inspired_by`, `branches_from`, `transfers_from`, `combines`:
the node declaring the relation is the **descendant**; `target` is the **ancestor**.
`build_lattice.py` will swap so arrows render old → new.
