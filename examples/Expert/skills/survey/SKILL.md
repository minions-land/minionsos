---
name: "survey"
description: "Run a structured literature survey by orchestrating subagents through a 5-stage pipeline: Discover → Extract → Decompose → Merge → Insights, producing a ModernKnowledge 6-layer knowledge lattice."
paths:
  - "**/*"
---

# /survey

Use this skill when the user gives a research topic and wants a structured survey. The main agent acts as coordinator only — it launches subagents for each pipeline stage, enforces schema, and assembles the final report. All substantive research happens in subagents.

## Purpose

Given a research topic, produce a structured knowledge lattice by running a 5-stage pipeline:

1. **Discover** — find relevant papers (Semantic Scholar API, arXiv MCP, web search)
2. **Extract** — per-paper three-dimensional extraction (methods, experiments, theory)
3. **Decompose** — map extractions into 6-layer lattice candidates
4. **Merge** — anchor candidates against existing lattice, deduplicate, write node files
5. **Insights** — run 9 topology-derived analyses on the compiled lattice

The main agent must not perform substantive domain research. Its job is: scope definition, subagent dispatch, schema enforcement, progress tracking, and final assembly.

## Inputs

- topic or research question (required)
- optional scope constraints (time range, venue, subfield)
- optional seed papers (arXiv IDs or titles)
- optional language preference (default: follow user's language)
- optional paper limit (default: 30)

If the user provides no time range, recent = last 2–3 years from today's system date.
If the topic is ambiguous, narrow it first (e.g. `视觉长尾` → long-tailed recognition vs detection vs segmentation).

## The 6-layer knowledge lattice

```
L0 Paradigm     broad paradigms (e.g. "Deep Learning")
L1 Direction    research directions (e.g. "Spatial GNN")
L2 Method       specific systems (e.g. "Novae", "scGPT")
L3 Component    reusable building blocks
L4 Claim        assertions with claim_type + confidence
L5 Evidence     experimental results backing claims
```

Papers are provenance, not lattice nodes. Decompose each paper into knowledge units at multiple layers — never summarize a paper as one node.

## Schema reference

Node types and required fields:

- **Paradigm (L0)**: `id`, `label`, `description`; optional `status`, `era`
- **Direction (L1)**: `id`, `label`, `description`, `belongs_to` (→ paradigm); optional `status` (active/emerging/mature/declining), `active_period`, `key_question`
- **Method (L2)**: `id`, `label`, `description`, `belongs_to` (→ direction), `introduced_by` (→ paper); must carry `constraints` and `origin_field`; optional `year`, `venue`, `architecture_type`, `pretraining_scale`
- **Component (L3)**: `id`, `label`, `description`, `introduced_by` (→ paper); optional `component_type` (architecture | encoding | training-task | strategy | framework | algorithm | design-principle | capability), `used_by`
- **Claim (L4)**: `id`, `label`, `claim_type` (performance | scalability | efficiency | generalization | novelty | limitation), `asserted_by` (→ paper); optional `confidence` ∈ [0,1], `conditions`, `year`
- **Evidence (L5)**: `id`, `label`, `supports_claim` (→ claim), `source_paper` (→ paper); optional `task`, `dataset`, `metric`, `result`, `baselines`, `setting`
- **Paper**: `id`, `title`, `authors`, `year`; optional `venue`, `url`, `tags`

Edge types:
- Within L1: `branches_from`, `converges_with`
- Within L2: `extends`, `combines`, `supersedes`
- Within L3: `generalizes`, `specializes`, `is_variant_of`, `transfers_from`
- Within L4: `supports`, `contradicts`, `refines`
- Cross-layer: `belongs_to`, `composed_of`, `inspired_by`, `asserts`, `evidenced_by`, `introduced_by`

Every edge carries `confidence` ∈ [0,1] and `provenance`.

Confidence model:
- EXTRACTED (0.9–1.0): explicitly stated in source
- INFERRED (0.5–0.9): reasonable deduction
- AMBIGUOUS (0.0–0.5): uncertain, flagged for review

## Required role policy

### Main agent

Must do:
- define topic scope and paper search strategy
- launch subagents for each pipeline stage
- track progress: how many papers discovered, extracted, decomposed, merged
- enforce schema completeness after merge (every method has `constraints`, `origin_field`, `composed_of`)
- compile lattice and run insights
- assemble the final report from lattice data

Must not do:
- read papers and extract knowledge itself
- introduce domain claims
- fill evidence gaps with intuition

### Subagents

Each subagent must:
- stay within its assigned pipeline stage
- return structured output (JSON or structured Markdown) that the next stage can consume
- support every claim with a source
- never invent URLs

## Pipeline stages and subagent assignments

### Stage 1: Discover

Launch 1–3 subagents in parallel depending on topic breadth.

Mission per subagent:
- search for papers using available tools: Semantic Scholar API (`WebFetch`), arXiv MCP (`mcp__arxiv-mcp-server__search_papers`), web search (`WebSearch`)
- for each paper collect: title, authors, year, venue, abstract, citation count, arXiv ID or DOI, paper URL
- identify foundational/classic papers (high citation count, referenced by many recent works)
- mark each paper as `seed`, `foundational`, or `recent`

Parallelization strategy:
- Subagent A: keyword search via Semantic Scholar + WebSearch for recent papers (last 2–3 years)
- Subagent B: arXiv MCP search for preprints and recent work
- Subagent C (optional): seed paper expansion — given user-provided seeds, fetch their references to find foundational works

Main agent after this stage:
- merge paper lists from all subagents, deduplicate by title/arXiv ID
- sort by citation count, cap at paper limit
- produce a unified `paper_list` for the next stage

Required output per paper:
```json
{
  "title": "...",
  "authors": ["..."],
  "year": 2024,
  "venue": "...",
  "abstract": "...",
  "citationCount": 150,
  "arXivId": "2401.12345",
  "url": "...",
  "status": "pending",
  "source": "semantic_scholar | arxiv | web | seed",
  "is_foundational": false
}
```

### Stage 2: Extract

Launch N subagents in parallel (one per paper, or batched 3–5 papers per subagent).

Mission per subagent — three-dimensional extraction for each paper:

**Dimension 1: Method components** — extract at three granularity levels:
- Level 0 (architecture): the overall system/framework
- Level 1 (module): major functional blocks
- Level 2 (atomic): individual operations/techniques

For each component: name, level, description, sub-components, novelty, inspirational links to prior work (with confidence and evidence text).

**Dimension 2: Experiments** — extract as structured tuples:
- task, dataset, metric, method variant, result, baselines (with their results and source papers), experimental setting
- claims made based on each experiment (text + claim_type)
- ablation studies (variant, result, insight)
- experiment gaps: what's missing (COMBINATION_MISSING, SCALE_MISSING, ABLATION_MISSING, BASELINE_MISSING, SETTING_MISSING, REPRODUCIBILITY_MISSING)

**Dimension 3: Theory** — extract theoretical contributions:
- type (convergence | generalization | expressiveness | computational_complexity | information_theoretic)
- statement, assumptions, mathematical tools used
- dependencies on prior theorems
- empirical-theory gaps: observations lacking theoretical explanation

Required output per paper:
```json
{
  "paper_id": "slug",
  "title": "...",
  "year": 2024,
  "venue": "...",
  "method_components": [...],
  "experiments": [...],
  "experiment_gaps": [...],
  "theoretical_contributions": [...],
  "empirical_theory_gaps": [...]
}
```

Subagent prompt template:

"Analyze the paper titled '<TITLE>' (year: <YEAR>, venue: <VENUE>). Abstract: <ABSTRACT>. Extract all knowledge in three dimensions. Dimension 1 — Method Components: extract at architecture (level 0), module (level 1), and atomic (level 2) granularity. For each component give name, level, description, sub-components, novelty, and inspirational links to prior work with confidence scores. Dimension 2 — Experiments: extract every experiment as a structured tuple (task, dataset, metric, result, baselines with results, setting, claims, ablations). Identify experiment gaps. Dimension 3 — Theory: extract theoretical contributions (type, statement, assumptions, tools, dependencies) and empirical-theory gaps. Return structured JSON only."

### Stage 3: Decompose

Launch N subagents in parallel (one per extraction, or batched).

Mission per subagent:
- take one paper's raw extraction + the current lattice context (existing paradigms, directions, methods, components, claims)
- map the extraction into lattice-layer-aligned candidate nodes:
  - L0 Paradigm: only propose new if no existing paradigm fits (almost always reuse existing)
  - L1 Direction: propose new only if genuinely novel, otherwise reference existing by ID
  - L2 Method: one node per paper's main contribution, with `architecture_type`, `origin_field`, `constraints`, and `extends`/`combines` edges to existing methods
  - L3 Components: 5–10 reusable building blocks, each precisely named, typed, and marked novel or standard
  - L4 Claims: 3–8 specific falsifiable claims with `claim_type`, `conditions`, and `supports`/`contradicts`/`refines` edges to existing claims
  - L5 Evidence: experimental results backing each claim

The lattice context must be passed to each decompose subagent so it can anchor to existing nodes rather than creating duplicates.

Required output per paper:
```json
{
  "paradigm": null | {"label": "...", "description": "..."},
  "direction": {"existing_id": "direction:xxx"} | {"label": "...", "description": "...", "belongs_to": "paradigm:xxx", "key_question": "..."},
  "method": {
    "label": "...", "description": "...", "architecture_type": "...",
    "origin_field": "...", "constraints": {...},
    "relations": [{"target_id": "method:xxx", "type": "extends", "confidence": 0.85, "provenance": "..."}]
  },
  "components": [{"label": "...", "description": "...", "component_type": "...", "is_novel": true, "relations": [...]}],
  "claims": [{"label": "...", "claim_type": "...", "confidence": 0.9, "conditions": "...", "relations": [...]}],
  "evidence": [{"label": "...", "task": "...", "dataset": "...", "metric": "...", "result": "...", "baselines": [...], "supports_claim_label": "..."}]
}
```

Subagent prompt template:

"You are decomposing a paper's extracted knowledge into a six-layer knowledge lattice. Existing lattice context: <LATTICE_CONTEXT>. Paper: '<TITLE>' (<YEAR>, <VENUE>). Raw extraction: <EXTRACTION_JSON>. Map the extraction into lattice candidates. Rules: (1) Reuse existing paradigms/directions when possible. (2) Method must have architecture_type, origin_field, constraints, and extends/combines edges. (3) Components must be reusable, precisely named, and typed. (4) Claims must be falsifiable with claim_type and conditions. (5) Evidence must back specific claims. Return structured JSON only."

### Stage 4: Merge

Launch 1 subagent (sequential, because merge requires global deduplication state).

Mission:
- take all decompose outputs + the current lattice
- for each candidate node, anchor against existing nodes using label + description similarity
  - similarity > 0.55 → anchor to existing (same concept)
  - similarity < 0.30 → create new node
  - between 0.30–0.55 → flag as ambiguous for review
- write `.md` node files with YAML frontmatter under `nodes/` and `papers/`
- ensure unique IDs (append `-2`, `-3` if collision)
- add `composed_of` edges from methods to their components
- resolve claim `supports`/`contradicts`/`refines` edges by matching target labels to existing claim IDs

Required output:
- list of created nodes (with IDs)
- list of anchored nodes (with similarity scores)
- list of ambiguous nodes flagged for review
- schema gaps: methods missing `constraints`, `origin_field`, or `composed_of`

After merge, the main agent runs `build_lattice.py` to compile all node files into `lattice.json`, then `insights.py` to extract topology-derived insights into `insights.json`.

### Stage 5: Insights

Run `insights.py` on the compiled `lattice.json` — this is pure Python topology analysis, no LLM calls:

1. **Evolution Spine** — find longest `extends` chains within each direction, ordered by year
2. **Convergence Funnel** — find components used by methods from different directions
3. **Claim Conflict** — find `contradicts` edges and trace back to divergent components
4. **Orphan Innovation** — find components used by only one method with no transfer edges, older than 1 year
5. **Component Hub** — find components with disproportionately high usage across methods
6. **Branching Burst** — find methods that spawned multiple children within 2 years
7. **Open Problem** — synthesize from unresolved claim conflicts and missing cross-method comparisons
8. **Applicability Boundary** — surface methods with incompatible constraints solving the same task
9. **Cross-Field Transfer** — map which external fields feed innovation into this domain via `origin_field`

Run via: `python .claude/skills/survey/tools/insights.py --topic <topic>`

## Execution rules

1. Stage 1 (Discover): launch search subagents in parallel.
2. Stage 2 (Extract): launch per-paper subagents in parallel (batch 3–5 papers per subagent to manage context).
3. Stage 3 (Decompose): launch per-paper subagents in parallel, but pass current lattice context to each.
4. Stage 4 (Merge): run sequentially — global dedup state required.
5. Stage 5 (Insights): run after lattice compilation.
6. Between stages, the main agent consolidates outputs and prepares inputs for the next stage.
7. Never present a finding as final unless it survived the full pipeline.
8. Prefer strong venues, impactful arXiv preprints, widely used benchmarks/code.
9. Never invent URLs — only use URLs found via search tools or provided by the user.
10. Every method must have `constraints`, `origin_field`, and `composed_of` edges.
11. Every claim must have a source and at least one `supports`/`contradicts`/`refines` edge when possible.
12. Every edge carries `confidence` and `provenance`.
13. Use the user's language for labels/descriptions.
14. Edge-direction convention: the declaring node is the descendant; `target` = ancestor. `extends`, `inspired_by`, `branches_from`, `transfers_from`, `combines` arrows render old → new.

## Subagent dispatch summary

| Stage | Subagent count | Parallelism | Input | Output |
|-------|---------------|-------------|-------|--------|
| Discover | 1–3 | parallel | topic + scope | paper_list (JSON) |
| Extract | N (batched) | parallel | paper abstracts | per-paper extraction (JSON) |
| Decompose | N (batched) | parallel | extraction + lattice context | per-paper candidates (JSON) |
| Merge | 1 | sequential | all candidates + lattice | node files (.md) + merge report |
| Insights | 1 | after build | lattice.json | 9 insight analyses |

All subagents use `Agent` with `subagent_type: "general-purpose"`.

## Final report format

1. Topic and scope used
2. Discovery summary — papers found, sources used, foundational vs recent split
3. Paradigms (L0) — 2–3 with status/era
4. Directions (L1) — 4–8 with status + `branches_from` / `converges_with`
5. Methods (L2) — each with `constraints`, `origin_field`, component list, pedigree (`extends`/`inspired_by`)
6. Components (L3) — hubs and their `used_by`
7. Claims (L4) — supports/contradicts clusters with confidence
8. Evidence (L5) — key experimental results backing major claims
9. Nine insights — one paragraph each:
   1. Evolution Spine
   2. Convergence Funnel
   3. Claim Conflict
   4. Orphan Innovation
   5. Component Hub
   6. Branching Burst
   7. Open Problem
   8. Applicability Boundary
   9. Cross-Field Transfer
10. Merge statistics — created/anchored/ambiguous counts, schema gaps
11. Recommended reading list (top 10–15 papers by importance)
12. Source appendix — title, year, venue, paper URL, which layer/node it contributed to

## Quality bar

A good result must:
- discover papers from multiple sources, not just one API
- extract each paper into multi-layer knowledge units, not single-node summaries
- anchor new knowledge against existing lattice to avoid duplicates
- carry every method's `constraints`, `origin_field`, and `composed_of` edges
- make direction dynamics (branching / converging / fragmenting) explicit
- connect claims with `supports`/`contradicts`/`refines` where applicable
- back key claims with evidence nodes (dataset, metric, result)
- expose uncertainty and ambiguous anchoring instead of hiding it
- populate at least one entry per insight type when evidence allows
- keep the main agent out of substantive domain reasoning — all research happens in subagents

## Integrated tools

All tools are bundled under `.claude/skills/survey/tools/`. Topics are created under `surveys/topics/` in the working directory (configurable via `MK_TOPICS_DIR` env var).

### Full automated pipeline

```bash
python .claude/skills/survey/tools/orchestrate.py --topic <topic> --query "<query>" --limit 30
```

### Individual tools

| Tool | Usage |
|------|-------|
| `discover_papers.py --topic T --query Q --limit N` | Semantic Scholar search + foundational detection |
| `extract_paper.py --topic T --all` | LLM extraction for all pending papers |
| `decompose_to_lattice.py --topic T --all` | Map extractions to lattice candidates |
| `anchor_merge.py --topic T --all` | Anchor + merge candidates into node files |
| `anchor_merge.py --topic T --all --dry-run` | Preview merge without writing |
| `build_lattice.py --topic T` | Compile node files → `lattice.json` |
| `insights.py --topic T` | 9 topology-derived insights → `insights.json` |
| `query.py --topic T --stats` | Lattice statistics |
| `query.py --topic T --timeline` | Temporal evolution |
| `query.py --topic T --gaps` | Research gaps |
| `validate.py` | Schema validation |
| `ingest_paper.py --topic T --input F` | Incremental paper ingest |

### Dependencies

- Python 3.10+
- `pyyaml` (`pip install pyyaml`)
- `claude` CLI in PATH (for LLM extraction/decomposition stages)
