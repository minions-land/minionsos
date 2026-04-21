# Workflow Guide — /survey with ModernKnowledge Lattice

The survey skill orchestrates subagents through a 5-stage pipeline, persisting results as a ModernKnowledge knowledge lattice. All tools are bundled under `.claude/skills/survey/tools/`.

## Integrated tools

| Tool | Purpose | Stage |
|------|---------|-------|
| `discover_papers.py` | Semantic Scholar API search + foundational paper detection | Discover |
| `extract_paper.py` | Per-paper three-dimensional LLM extraction (methods, experiments, theory) | Extract |
| `decompose_to_lattice.py` | Map raw extraction into lattice-layer candidates using existing lattice context | Decompose |
| `anchor_merge.py` | Anchor candidates against existing nodes, deduplicate, write `.md` node files | Merge |
| `build_lattice.py` | Compile node `.md` files → `lattice.json` | Build |
| `insights.py` | 9 topology-derived analyses on `lattice.json` (no LLM) | Build |
| `validate.py` | Validate nodes/edges against `schema/schema.yaml` | Any |
| `query.py` | Query lattice: stats, node lookup, timeline, gaps | Post-build |
| `ingest_paper.py` | Incremental paper ingest (rule-based decompose → anchor → diff → report) | Incremental |
| `orchestrate.py` | End-to-end pipeline: Discover → Extract → Decompose → Merge → Build | All |
| `common.py` | Shared utilities (topic resolution, init) | — |

Prompt templates for LLM extraction/decomposition live in `.claude/skills/survey/prompts/`.
Schema definition lives in `.claude/skills/survey/schema/schema.yaml`.

## Running the pipeline

### Full automated run

```bash
cd .claude/skills/survey
python tools/orchestrate.py --topic <topic> --query "<query>" --limit 30
```

This runs all 5 stages sequentially: discover → extract → decompose → merge → build.

### Stage by stage

```bash
# 1. Init topic
python -c "import sys; sys.path.insert(0,'tools'); from common import init_topic; init_topic('<topic>')"

# 2. Discover papers
python tools/discover_papers.py --topic <topic> --query "<query>" --limit 30

# 3. Extract (calls claude CLI per paper)
python tools/extract_paper.py --topic <topic> --all

# 4. Decompose extractions into lattice candidates
python tools/decompose_to_lattice.py --topic <topic> --all

# 5. Anchor + merge candidates into node files
python tools/anchor_merge.py --topic <topic> --all

# 6. Build lattice + insights
python tools/build_lattice.py --topic <topic>
python tools/insights.py --topic <topic>
```

### Query the lattice

```bash
python tools/query.py --topic <topic> --stats
python tools/query.py --topic <topic> --timeline
python tools/query.py --topic <topic> --method <name>
python tools/query.py --topic <topic> --gaps
```

### Incremental paper ingest

```bash
python tools/ingest_paper.py --topic <topic> --input <paper.md>
```

## Topic directory structure

Topics are created under `surveys/topics/` (configurable via `MK_TOPICS_DIR` env var):

```
surveys/topics/<topic>/
├── paper_list.json          # discovered papers
├── extractions/             # per-paper LLM extractions
├── candidates/              # per-paper lattice candidates
├── nodes/
│   ├── paradigms/           # L0 .md files
│   ├── directions/          # L1
│   ├── methods/             # L2
│   ├── components/          # L3
│   ├── claims/              # L4
│   └── evidence/            # L5
├── papers/                  # paper provenance .md files
├── reports/                 # merge reports
├── lattice.json             # compiled lattice
├── insights.json            # topology-derived insights
├── pipeline_state.json      # orchestrator state
└── changelog.jsonl          # merge changelog
```

## Mapping subagents → lattice layers

| Subagent | Produces | Lands in layer |
|----------|----------|----------------|
| Discover | Paper metadata (title, authors, year, venue, abstract, citations) | `paper_list.json` |
| Extract | Method components, experiments, theory per paper | `extractions/` |
| Decompose | Lattice-layer-aligned candidates per paper | `candidates/` |
| Merge | Deduplicated `.md` node files with anchoring | `nodes/`, `papers/` |
| Build | Compiled `lattice.json` + 9 topology insights | `lattice.json`, `insights.json` |

## Final report sections

Generated from lattice data:
1. Topic + scope
2. **Paradigms (L0)** — 2–3 umbrellas
3. **Directions (L1)** — 4–8 with status and `branches_from`
4. **Methods (L2)** — each with `constraints`, `origin_field`, and pedigree
5. **Components (L3)** — reusable hubs
6. **Claims (L4)** — supports/contradicts clusters
7. **Nine insights** — produced by `insights.py` from `lattice.json`
8. **Recommended reading**
9. **Source appendix**

## Seven key principles

1. **Decompose, don't summarize.** A paper contributes units at multiple layers.
2. Every method must have `composed_of` edges.
3. Every method must have `constraints`.
4. Claims need `contradicts`/`supports` edges.
5. Provenance on every edge.
6. `origin_field` on every method.
7. Use the user's language.

## Quality checks

- No dangling edges (every `target` resolves to a node).
- No orphan methods (every method has ≥1 `composed_of`).
- Every major claim has ≥1 source.
- At least one entry per insight type where applicable.
- Run `validate.py` to check schema compliance.
