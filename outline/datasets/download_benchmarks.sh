#!/usr/bin/env bash
# Download all 73 auto-research benchmarks
# Usage: ./download_benchmarks.sh [--tier1-only] [--dry-run]

set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=false
TIER1_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) DRY_RUN=true; shift ;;
    --tier1-only) TIER1_ONLY=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() { echo "[$(date +%H:%M:%S)] $*"; }
run() {
  if $DRY_RUN; then
    echo "[DRY] $*"
  else
    log "Running: $*"
    "$@"
  fi
}

clone_repo() {
  local repo="$1"
  local target="$2"
  if [[ -z "$repo" ]]; then
    log "  ⊘ No repo URL"
    return
  fi
  # Clone into target/repo/ so meta.json can coexist
  local repo_dir="$target/repo"
  if [[ -d "$repo_dir/.git" ]]; then
    log "  ✓ Already cloned: $repo_dir"
    return
  fi
  mkdir -p "$target"
  run gh repo clone "$repo" "$repo_dir" -- --depth=1 || log "  ✗ Clone failed for $repo"
}

pull_hf() {
  local dataset="$1"
  local target="$2"
  if [[ -z "$dataset" ]]; then
    log "  ⊘ No HuggingFace dataset"
    return
  fi
  if [[ -d "$target" ]] && [[ -n "$(ls -A "$target" 2>/dev/null)" ]]; then
    log "  ✓ Already downloaded: $target"
    return
  fi
  if command -v huggingface-cli &>/dev/null; then
    run huggingface-cli download "$dataset" --repo-type dataset --local-dir "$target"
  else
    log "  ⚠ huggingface-cli not found, skipping HF dataset"
  fi
}

# Tier 1: 17 benchmarks that can be evaluated immediately (status: ✓)
TIER1=(
  "1.2-literature-review/LitSearch|https://github.com/princeton-nlp/LitSearch|"
  "1.2-literature-review/CiteME||"
  "1.3-coding-experiments/SWE-bench|https://github.com/princeton-nlp/SWE-bench|princeton-nlp/SWE-bench"
  "1.3-coding-experiments/SciCode|https://github.com/scicode-bench/SciCode|"
  "1.3-coding-experiments/MLAgentBench|https://github.com/snap-stanford/MLAgentBench|"
  "1.3-coding-experiments/ScienceAgentBench||"
  "1.3-coding-experiments/KernelBench|https://github.com/ScalingIntelligence/KernelBench|"
  "1.3-coding-experiments/TritonBench|https://github.com/thunlp/TritonBench|"
  "1.3-coding-experiments/InfiAgent-DABench||"
  "1.3-coding-experiments/SUPER||"
  "1.4-tables-figures/TeXpert||"
  "1.4-tables-figures/ChartQA||"
  "2-paper-writing/SciIG||"
  "2-paper-writing/AutoSurvey|https://github.com/AutoSurveys/AutoSurvey|"
  "3.1-peer-review/PeerRead||"
  "3.1-peer-review/ClaimCheck||"
  "e2e-general/GAIA||gaia-benchmark/GAIA"
  "e2e-general/SimpleQA||"
)

# Tier 2: 34 benchmarks needing light adapter (status: ~)
TIER2=(
  "1.1-idea-generation/IdeaBench||"
  "1.1-idea-generation/LiveIdeaBench||"
  "1.1-idea-generation/AI-Idea-Bench-2025|https://github.com/yansheng-qiu/AI_Idea_Bench_2025|"
  "1.1-idea-generation/HindSight||"
  "1.2-literature-review/DeepScholar-Bench|https://github.com/guestrin-lab/deepscholar-bench|"
  "1.2-literature-review/ReportBench|https://github.com/ByteDance-BandAI/ReportBench|"
  "1.2-literature-review/ScholarGym||"
  "1.3-coding-experiments/SWE-bench-Pro||"
  "1.3-coding-experiments/ResearchCodeBench||"
  "1.3-coding-experiments/SciReplicate-Bench|https://github.com/xyzCS/SciReplicate-Bench|"
  "1.3-coding-experiments/MLE-Bench||"
  "1.3-coding-experiments/EXP-Bench|https://github.com/Just-Curieous/Curie|"
  "1.3-coding-experiments/PostTrainBench|https://github.com/aisa-group/PostTrainBench|"
  "1.3-coding-experiments/DiscoveryBench|https://github.com/allenai/discoverybench|"
  "1.3-coding-experiments/LAB-Bench|https://github.com/Future-House/LAB-Bench|"
  "1.3-coding-experiments/RE-Bench||"
  "1.3-coding-experiments/CORE-Bench||"
  "1.4-tables-figures/ArxivDIGESTables||"
  "1.4-tables-figures/Chain-of-Table||"
  "1.4-tables-figures/AbGen||"
  "1.4-tables-figures/FigureBench|https://github.com/ResearAI/AutoFigure|"
  "2-paper-writing/PaperWritingBench||"
  "3.1-peer-review/ReviewMT||"
  "3.1-peer-review/AgentReview||"
  "3.1-peer-review/ReviewAgents||"
  "3.1-peer-review/AI-Detection||"
  "3.1-peer-review/Breaking-the-Reviewer||"
  "3.1-peer-review/Prompt-Injection||"
  "3.2-rebuttal/Re2||"
  "3.2-rebuttal/RebuttalAgent|https://github.com/Zhitao-He/RebuttalAgent|"
  "3.2-rebuttal/DRPG|https://github.com/ulab-uiuc/DRPG-RebuttalAgent|"
  "3.2-rebuttal/Commitment-Checklist||"
  "e2e-general/BrowseComp||"
  "e2e-general/HLE|https://github.com/centerforaisafety/hle|"
  "e2e-general/AAAR-1.0||"
)

# Tier 3: 16 benchmarks needing medium refactor (status: !)
TIER3=(
  "1.1-idea-generation/HeurekaBench|https://github.com/mlbio-epfl/HeurekaBench|"
  "1.1-idea-generation/ResearchBench||"
  "1.2-literature-review/IDRBench||"
  "1.2-literature-review/SciNetBench||"
  "1.3-coding-experiments/SWE-EVO||"
  "1.3-coding-experiments/PaperBench|https://github.com/openai/preparedness|"
  "1.3-coding-experiments/MLGym||"
  "1.3-coding-experiments/MLR-Bench||"
  "1.3-coding-experiments/DiscoveryWorld|https://github.com/allenai/discoveryworld|"
  "1.3-coding-experiments/AstaBench|https://github.com/allenai/asta-bench|"
  "1.3-coding-experiments/ResearchClawBench|https://github.com/InternScience/ResearchClawBench|"
  "1.3-coding-experiments/FrontierScience||"
  "1.4-tables-figures/SciFlow-Bench||"
  "3.1-peer-review/ICLR-2025-Study||"
  "3.1-peer-review/RATE||"
)

# Tier 4: 6 benchmarks NOT COVERED (status: ✗)
TIER4=(
  "4-dissemination/P2P||"
  "4-dissemination/Paper2Poster|https://github.com/Paper2Poster/Paper2Poster|"
  "4-dissemination/PPTAgent-PPTEval|https://github.com/icip-cas/PPTAgent|"
  "4-dissemination/Paper2Video|https://github.com/showlab/Paper2Video|"
  "4-dissemination/Paper2Web|https://github.com/YuhangChen1/Paper2All|"
  "4-dissemination/PresentEval|https://github.com/AIGeeksGroup/PresentAgent|"
)

download_tier() {
  local tier_name="$1"
  shift
  local items=("$@")

  log "━━━ $tier_name (${#items[@]} benchmarks) ━━━"

  for entry in "${items[@]}"; do
    IFS='|' read -r path repo hf <<< "$entry"
    name="$(basename "$path")"
    target="$BASE/$path"

    log "[$name]"

    if [[ -n "$repo" ]]; then
      clone_repo "$repo" "$target"
    fi

    if [[ -n "$hf" ]]; then
      pull_hf "$hf" "$target/hf_data"
    fi

    if [[ -z "$repo" && -z "$hf" ]]; then
      log "  ⊘ No download source (paper-only or proprietary)"
    fi
  done
}

cd "$BASE"

if $TIER1_ONLY; then
  download_tier "TIER 1 (✓ directly evaluable)" "${TIER1[@]}"
else
  download_tier "TIER 1 (✓ directly evaluable)" "${TIER1[@]}"
  download_tier "TIER 2 (~ light adapter)" "${TIER2[@]}"
  download_tier "TIER 3 (! medium refactor)" "${TIER3[@]}"
  download_tier "TIER 4 (✗ NOT COVERED)" "${TIER4[@]}"
fi

log "━━━ DONE ━━━"
log "Next steps:"
log "  1. Check meta.json in each benchmark dir for evaluation flow"
log "  2. Run MinionsOS evaluation: cd <MinionsOS repo> && python -m minions.eval --benchmark <name>"
log "  3. Results will be written to outline/index.html automatically"
