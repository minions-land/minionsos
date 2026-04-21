# ModernKnowledge Schema Reference

A 6-layer knowledge lattice. Papers are **provenance**, not lattice nodes — each paper is decomposed into units across layers.

## Layers

| ID | Layer | Purpose | Example |
|----|-------|---------|---------|
| L0 | Paradigm | Broad research paradigms | "Deep Learning" |
| L1 | Direction | Research directions within a paradigm | "Spatial GNN" |
| L2 | Method | Specific models/systems | "Novae", "scGPT" |
| L3 | Component | Reusable building blocks | "Delaunay Spatial Graph" |
| L4 | Claim | Specific assertions | "spatial context improves annotation" |
| L5 | Evidence | Experimental results backing claims | benchmark numbers |

## Required Fields Per Node Type

- **paradigm**: `id, type, label, description, status, era`
- **direction**: `id, type, label, description, belongs_to, status, active_period, key_question`
- **method**: `id, type, label, description, belongs_to, introduced_by, year, venue, architecture_type, constraints, origin_field`
- **component**: `id, type, label, description, introduced_by, component_type, used_by`
- **claim**: `id, type, label, claim_type, asserted_by, confidence, year`
- **paper**: `id, type, title, authors, year, venue`

## ID Prefixes

`paradigm:`, `direction:`, `method:`, `component:`, `claim:`, `evidence:`, `paper:`

## Edge Types

**Within-layer**: `extends`, `combines`, `supersedes`, `generalizes`, `specializes`, `is_variant_of`, `transfers_from`, `branches_from`, `converges_with`, `supports`, `contradicts`, `refines`

**Cross-layer**: `belongs_to` (Direction→Paradigm, Method→Direction), `composed_of` (Method→Component), `inspired_by`

**Provenance**: `introduced_by` (→ paper)

**Auto-inferred**: `asserts` (Method→Claim, via shared `introduced_by`/`asserted_by` paper)

## Edge-Direction Swap

`build_lattice.py` swaps source/target for these types so arrows point old → new (knowledge flow):
`extends`, `inspired_by`, `branches_from`, `transfers_from`, `combines`

In YAML, write `extends` with `target` = the ancestor/prior method.

## Confidence Model

- `EXTRACTED` 0.9–1.0: explicitly stated in source
- `INFERRED` 0.5–0.9: reasonable deduction
- `AMBIGUOUS` 0.0–0.5: uncertain, flag for review

## Core Constraints

1. Every method must have `composed_of` edges.
2. Every method must have `constraints` block.
3. Every method must have `origin_field`.
4. Claims should have `supports`/`contradicts`/`refines` edges.
5. Every edge should carry `provenance`.
6. Directions need `belongs_to` a paradigm.
7. Use the user's language for labels/descriptions.
