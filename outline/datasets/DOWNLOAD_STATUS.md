# Auto-Research Benchmarks Download Status

**Date:** 2026-05-22
**Source:** AI for Auto-Research: Roadmap & User Guide (Kong et al., 2026, arXiv:2605.18661)

## Summary

- **Total benchmarks catalogued:** 73 (74 dirs incl. summary)
- **Repos successfully cloned:** 29 (1 partial: PaperBench needs git-lfs)
- **Total size on disk:** 6.2 GB
- **meta.json files:** 74 (one per benchmark with paper / repo / scoring / MinionsOS adapter status)

## Successfully cloned (29 repos, 6.2 GB)

### Tier 1 — directly evaluable (✓), 7 repos
- LitSearch (208K), SWE-bench (6.0M), SciCode (344K)
- MLAgentBench (5.9M), KernelBench (5.9M), TritonBench (156M)
- AutoSurvey (1.8M)

### Tier 2 — light adapter (~), 11 repos
- AI-Idea-Bench-2025 (325M)
- DeepScholar-Bench (46M), ReportBench (11M)
- SciReplicate-Bench (3.3M), EXP-Bench (47M), PostTrainBench (18M)
- DiscoveryBench (69M), LAB-Bench (512M)
- FigureBench (159M)
- RebuttalAgent (3.6M), DRPG (3.8M)

### Tier 3 — medium refactor (!), 6 repos
- HeurekaBench (358M)
- **PaperBench** (39M, partial — needs `git lfs pull`)
- DiscoveryWorld (58M), AstaBench (4.2M), ResearchClawBench (2.5G)
- HLE (364K)

### Tier 4 — not covered (✗), 5 repos cloned anyway
- Paper2Poster (1.1G), PPTAgent-PPTEval (157M), Paper2Video (64M), Paper2Web (528M), PresentEval (152M)
- These are dissemination benchmarks MinionsOS doesn't cover yet, but repos cloned for future reference.

## Not downloaded (44 benchmarks)

Reasons:
- **Paper-only / proprietary** (no public repo): CiteME, PeerRead, ClaimCheck, SimpleQA, SciIG, TeXpert, ChartQA, ScienceAgentBench, InfiAgent-DABench, SUPER, MLE-Bench, RE-Bench, CORE-Bench, etc.
- **HuggingFace dataset, no CLI installed**: GAIA, SWE-bench HF dataset, etc.
- **Future-dated / placeholder arXiv IDs** (need manual verification): IDRBench, ScholarGym, SciNetBench, FrontierScience, RATE, ICLR-2025-Study, etc.

## Directory layout

```
outline/datasets/
├── README.md                         # User-facing intro
├── DOWNLOAD_STATUS.md                # This file
├── download_benchmarks.sh            # Re-runnable downloader
├── 1.1-idea-generation/              # 6 benchmarks
│   ├── IdeaBench/meta.json
│   ├── AI-Idea-Bench-2025/
│   │   ├── meta.json
│   │   └── repo/                     # ← cloned source
│   └── ...
├── 1.2-literature-review/            # 7 benchmarks
├── 1.3-coding-experiments/           # 25 benchmarks (most repos here)
├── 1.4-tables-figures/               # 7
├── 2-paper-writing/                  # 3
├── 3.1-peer-review/                  # 10
├── 3.2-rebuttal/                     # 4
├── 4-dissemination/                  # 6 (NOT COVERED)
└── e2e-general/                      # 5
```

Every benchmark dir has a `meta.json` with:
- `name`, `stage`, `year`, `venue`
- `what_it_tests`, `scoring`
- `paper_arxiv`, `paper_doi`, `github`, `huggingface`
- `minionsos.status` (✓/~/!✗) + `minionsos.evaluation_flow` (specific Roles + tools to use)

## Next steps

1. **Fix PaperBench (GOLD STANDARD)**:
   ```bash
   brew install git-lfs  # or apt-get install git-lfs
   cd 1.3-coding-experiments/PaperBench/repo
   git lfs pull
   ```

2. **Install HuggingFace CLI** to pull HF-hosted datasets:
   ```bash
   pip install huggingface_hub[cli]
   ./download_benchmarks.sh    # re-run; will skip already-cloned repos
   ```

3. **Manually fetch paper-only benchmarks** as appendices/supplementary materials are released. Track in each benchmark's `meta.json`.

4. **Run Tier 1 evaluations** (17 directly evaluable):
   - Each `meta.json.minionsos.evaluation_flow` describes the exact MinionsOS Role + tool sequence.

5. **Write Tier 2 adapters** (34 benchmarks, ~100-300 LoC each):
   - Drop into `<benchmark>/adapter.py` next to `meta.json`.

6. **Extend modules for Tier 3** (16 benchmarks):
   - Most need either project_bridge expansion (cross-project test) or a new tool.

## Recommended priority order

| # | Benchmark | Tier | Why |
|---|-----------|------|-----|
| 1 | **PaperBench** | ! | GOLD — 8316 rubric leaves, end-to-end test |
| 2 | **SWE-bench** | ✓ | Industry standard; baseline number |
| 3 | **MLE-Bench** | ~ | 75 Kaggle competitions, medal rate metric |
| 4 | **ClaimCheck** | ✓ | Direct test of Ethics + mos_review_run |
| 5 | **RE-Bench** | ~ | 4h vs human researcher — best long-horizon test |
| 6 | **MLR-Bench** | ! | Open-ended; tests Role evolution split/merge |
| 7 | **AutoSurvey** | ✓ | De-facto long-form metric |
| 8 | **HeurekaBench** | ! | Full idea→experiment closed loop |

## Coverage matrix (final)

| Stage | Tier 1 ✓ | Tier 2 ~ | Tier 3 ! | Tier 4 ✗ | Total |
|-------|---------|---------|---------|---------|-------|
| 1.1 Idea Generation | 0 | 4 | 2 | 0 | 6 |
| 1.2 Literature Review | 2 | 3 | 2 | 0 | 7 |
| 1.3 Coding & Experiments | 7 | 9 | 9 | 0 | 25 |
| 1.4 Tables & Figures | 2 | 4 | 1 | 0 | 7 |
| 2 Paper Writing | 2 | 1 | 0 | 0 | 3 |
| 3.1 Peer Review | 2 | 6 | 2 | 0 | 10 |
| 3.2 Rebuttal | 0 | 4 | 0 | 0 | 4 |
| 4 Dissemination | 0 | 0 | 0 | 6 | 6 |
| E2E General | 2 | 3 | 0 | 0 | 5 |
| **Total** | **17** | **34** | **16** | **6** | **73** |

**MinionsOS-evaluable: 67 / 73 (92%)** — only Stage 4 (Paper2X dissemination) fully uncovered.
