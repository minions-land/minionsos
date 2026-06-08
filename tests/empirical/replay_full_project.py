"""Aggregate replay across all 11 roles of project 37596.

Walks every <role_dir>/*.jsonl under the input directory, runs the
context-pressure compact strategy on each session, and reports the
project-wide totals.

Usage:
  cd /Users/mjm/MinionsOS-context-pressure
  PYTHONPATH=. uv run python tests/empirical/replay_full_project.py /tmp/issue38_full/
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from replay_issue_38 import load_turns, simulate_compact_strategy


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: replay_full_project.py <root_dir>")
        return 2
    root = Path(argv[1])
    roles = sorted(p for p in root.iterdir() if p.is_dir())

    grand_orig = grand_sim = 0.0
    grand_compacts = 0
    grand_turns = 0
    print(
        f"{'role':<28} {'sessions':>8} {'turns':>6} {'compacts':>8} "
        f"{'orig $':>8} {'sim $':>8} {'saved %':>8}"
    )
    print("-" * 80)
    for role_dir in roles:
        files = sorted(role_dir.glob("*.jsonl"))
        if not files:
            continue
        role_orig = role_sim = 0.0
        role_compacts = 0
        role_turns = 0
        for f in files:
            turns = load_turns(f)
            if not turns:
                continue
            r = simulate_compact_strategy(turns)
            role_orig += r["cost_orig_dollars"]
            role_sim += r["cost_sim_dollars"]
            role_compacts += r["n_compact"]
            role_turns += r["n_turns"]
        if role_orig <= 0:
            continue
        pct = (role_orig - role_sim) / role_orig * 100
        print(
            f"{role_dir.name:<28} {len(files):>8} {role_turns:>6} {role_compacts:>8} "
            f"{role_orig:>7.2f} {role_sim:>7.2f} {pct:>7.1f}"
        )
        grand_orig += role_orig
        grand_sim += role_sim
        grand_compacts += role_compacts
        grand_turns += role_turns

    print("-" * 80)
    pct = (grand_orig - grand_sim) / grand_orig * 100
    print(
        f"{'TOTAL':<28} {'':>8} {grand_turns:>6} {grand_compacts:>8} "
        f"{grand_orig:>7.2f} {grand_sim:>7.2f} {pct:>7.1f}"
    )
    print()
    print(f"Project saved: ${grand_orig - grand_sim:.2f}  ({pct:.1f}%)")
    print(f"Compact events fired: {grand_compacts}")
    print(f"Turns processed: {grand_turns}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
