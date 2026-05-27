"""Empirical replay: simulate context-pressure detection on real project_37596 sessions.

Replays each turn of the long expert-triton-kernel session through the
probe() logic, treating each turn as if it were the "current" turn the
role just received. Reports:

  - At which turn the high-pressure threshold first fires
  - How many turns the role would have stayed in compact-cooldown
  - Cumulative cache_read tokens that COULD have been saved if compact
    had fired at every high-pressure point (with realistic cooldown
    suppression)

Pricing assumptions (Opus 1M-context tier per issue #38):
  cache_read   = $1.5/M
  cache_write  = $18.75/M
  output       = $75/M

Each compact event:
  + writes a 5-10K summary (small cache_write)
  + costs ~5K output tokens for the compact model run
  - resets the prefix tail back to ~floor (50K) for several turns

Running:
  cd /Users/mjm/MinionsOS-context-pressure
  PYTHONPATH=. uv run python tests/empirical/replay_issue_38.py /tmp/issue38_sim/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Replay parameters — match context_pressure.DEFAULT_*
THRESHOLD_HIGH = 100_000
WINDOW_TURNS = 10
COOLDOWN_TURNS = 30  # ~ 5 min of role activity at the observed cadence
FLOOR_AFTER_COMPACT = 50_000

# Pricing
P_CR = 1.5 / 1e6
P_CC = 18.75 / 1e6
P_OUT = 75.0 / 1e6
COMPACT_OUTPUT_TOKENS = 5_000  # compact model's summary output
COMPACT_PREFIX_REBUILD = 5_000  # extra cache_write next turn for new summary


def load_turns(jsonl: Path) -> list[dict]:
    turns = []
    with jsonl.open() as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "assistant":
                continue
            usage = (rec.get("message") or {}).get("usage") or {}
            turns.append(
                {
                    "ts": rec.get("timestamp"),
                    "cr": int(usage.get("cache_read_input_tokens") or 0),
                    "cc": int(usage.get("cache_creation_input_tokens") or 0),
                    "in": int(usage.get("input_tokens") or 0),
                    "out": int(usage.get("output_tokens") or 0),
                }
            )
    return turns


def simulate_compact_strategy(turns: list[dict]) -> dict:
    """Replay turns under the proposed strategy.

    Logic per turn:
      1. compute avg_cr over last WINDOW_TURNS effective-turns
      2. if >= THRESHOLD_HIGH and not in cooldown:
           - record a compact event
           - the role's "next-real-cr" trajectory is reset:
             after compact, conversation history is effectively replaced
             with a 5-10K summary; cr/turn drops back to floor and
             grows again from there.
      3. otherwise the cr value follows the original trajectory
    """
    # We simulate by RESCALING cr from the point of compact:
    #   For turn i after compact at turn k:
    #     simulated_cr[i] = FLOOR + (original_cr[i] - original_cr[k]) * decay
    # Simpler approximation: after compact, the next 30 turns track FLOOR
    # plus the *delta* the role would have accumulated in those turns
    # from cold start, capped by the original trajectory.

    n = len(turns)
    sim_cr = [t["cr"] for t in turns]  # start from original
    compact_events = []
    cooldown_until = -1
    last_compact_at = -1

    # Estimate per-turn growth rate from original trajectory: avg delta
    # between consecutive turns = a proxy for "how fast history grows."
    deltas = [
        max(0, turns[i]["cr"] - turns[i - 1]["cr"])
        for i in range(1, min(40, n))
        if turns[i]["cr"] > 0 and turns[i - 1]["cr"] > 0
    ]
    growth_per_turn = sum(deltas) / max(1, len(deltas)) if deltas else 2_000

    for i in range(n):
        # Probe avg over the last WINDOW_TURNS of SIMULATED trajectory
        window_start = max(0, i - WINDOW_TURNS + 1)
        window = sim_cr[window_start : i + 1]
        avg = sum(window) // len(window)

        on_cooldown = i < cooldown_until
        if avg >= THRESHOLD_HIGH and not on_cooldown:
            # Trigger compact at turn i. From turn i+1 onward, the
            # simulated cr resets to FLOOR and grows at growth_per_turn.
            compact_events.append({"turn_idx": i, "avg_cr_at_trigger": avg})
            last_compact_at = i
            cooldown_until = i + COOLDOWN_TURNS

            for j in range(i + 1, n):
                offset = j - i
                projected = FLOOR_AFTER_COMPACT + int(growth_per_turn * offset)
                # Don't exceed what the original trajectory had at this absolute turn —
                # if the work being done genuinely needed less context, respect that.
                sim_cr[j] = min(projected, turns[j]["cr"])

    # Tally costs
    orig_cr = sum(t["cr"] for t in turns)
    sim_cr_total = sum(sim_cr)
    compact_overhead_cc = len(compact_events) * COMPACT_PREFIX_REBUILD
    compact_overhead_out = len(compact_events) * COMPACT_OUTPUT_TOKENS

    cost_orig = orig_cr * P_CR + sum(t["cc"] for t in turns) * P_CC + sum(t["out"] for t in turns) * P_OUT
    cost_sim = (
        sim_cr_total * P_CR
        + (sum(t["cc"] for t in turns) + compact_overhead_cc) * P_CC
        + (sum(t["out"] for t in turns) + compact_overhead_out) * P_OUT
    )

    return {
        "n_turns": n,
        "n_compact": len(compact_events),
        "compact_events": compact_events,
        "orig_cr_total": orig_cr,
        "sim_cr_total": sim_cr_total,
        "cr_saved": orig_cr - sim_cr_total,
        "cost_orig_dollars": cost_orig,
        "cost_sim_dollars": cost_sim,
        "savings_dollars": cost_orig - cost_sim,
        "savings_pct": (cost_orig - cost_sim) / cost_orig * 100 if cost_orig else 0,
        "growth_per_turn_est": int(growth_per_turn),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: replay_issue_38.py <jsonl_dir>")
        return 2
    jsonl_dir = Path(argv[1])
    files = sorted(jsonl_dir.glob("*.jsonl"))
    print(f"Found {len(files)} session files")
    print(f"  threshold_high = {THRESHOLD_HIGH:,}")
    print(f"  window_turns = {WINDOW_TURNS}")
    print(f"  cooldown_turns = {COOLDOWN_TURNS}")
    print(f"  floor_after_compact = {FLOOR_AFTER_COMPACT:,}")
    print()

    grand_orig = grand_sim = 0.0
    grand_compacts = 0
    for f in files:
        turns = load_turns(f)
        if not turns:
            continue
        result = simulate_compact_strategy(turns)
        print(f"== {f.name}  ({result['n_turns']} turns)")
        print(f"   compacts triggered: {result['n_compact']}")
        if result["compact_events"]:
            firsts = result["compact_events"][:3]
            for ev in firsts:
                print(
                    f"     → at turn {ev['turn_idx']}, avg_cr was {ev['avg_cr_at_trigger']:,}"
                )
        print(f"   original cr total : {result['orig_cr_total']:>12,} tok")
        print(f"   simulated cr total: {result['sim_cr_total']:>12,} tok")
        print(f"   cr saved          : {result['cr_saved']:>12,} tok")
        print(f"   original cost     : ${result['cost_orig_dollars']:.2f}")
        print(f"   simulated cost    : ${result['cost_sim_dollars']:.2f}")
        print(
            f"   savings           : ${result['savings_dollars']:.2f}  "
            f"({result['savings_pct']:.1f}%)"
        )
        print(f"   growth/turn est   : {result['growth_per_turn_est']:,} tok")
        print()
        grand_orig += result["cost_orig_dollars"]
        grand_sim += result["cost_sim_dollars"]
        grand_compacts += result["n_compact"]

    print("=" * 60)
    print(f"GRAND TOTAL (this expert, {len(files)} sessions):")
    print(f"  total compacts: {grand_compacts}")
    print(f"  original cost : ${grand_orig:.2f}")
    print(f"  simulated cost: ${grand_sim:.2f}")
    print(f"  savings       : ${grand_orig - grand_sim:.2f}  "
          f"({(grand_orig - grand_sim) / grand_orig * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))