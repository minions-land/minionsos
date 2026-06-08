#!/usr/bin/env python3
"""A/B compare original vs slim SYSTEM.md on real cold-start tokens.

Runs measure_context_slim.py once per variant (auto:30 only — that's the
production config). Variants:
  ORIGINAL: git stash to bring back HEAD's SYSTEM.md
  SLIM:     working tree (the proposed slim version)

Reports per-variant total input tokens; computes delta.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

REPO = Path("/Users/mjm/MinionsOS")
HARNESS = REPO / "tests/manual/measure_context_slim.py"


def run_harness() -> dict:
    """Return AFTER_auto_30 record."""
    proc = subprocess.run(
        ["python3", str(HARNESS)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout
    # Parse: find the AFTER block
    lines = out.split("\n")
    after_start = None
    for i, line in enumerate(lines):
        if "AFTER_auto_30" in line and line.strip().startswith('"label"'):
            after_start = i
            break
    if after_start is None:
        # try alt: parse the JSON block after the AFTER header
        for i, line in enumerate(lines):
            if "Measuring: AFTER" in line:
                # next "{" line starts JSON
                for j in range(i, min(i + 30, len(lines))):
                    if lines[j].strip() == "{":
                        end = j
                        while end < len(lines) and lines[end].strip() != "}":
                            end += 1
                        blob = "\n".join(lines[j : end + 1])
                        return json.loads(blob)
        print("PARSE FAIL\n", out[:2000])
        return {}
    return {}


def variant_run(label: str) -> dict:
    print(f"\n--- variant: {label} ---")
    rec = run_harness()
    if not rec:
        return {}
    total = (
        rec.get("input_tokens", 0)
        + rec.get("cache_creation_input_tokens", 0)
        + rec.get("cache_read_input_tokens", 0)
    )
    rec["total"] = total
    print(
        f"  input_tokens={rec.get('input_tokens')}, "
        f"cc={rec.get('cache_creation_input_tokens')}, "
        f"cr={rec.get('cache_read_input_tokens')}, TOTAL={total}"
    )
    return rec


def main():
    print("=== A/B: SYSTEM.md original vs slim ===")
    print("Measuring SLIM (working tree, current state)...")
    slim = variant_run("SLIM")

    print("\nGit stash → bring back ORIGINAL...")
    subprocess.run(["git", "stash"], cwd=str(REPO), check=True)
    try:
        time.sleep(1)
        print("Measuring ORIGINAL...")
        orig = variant_run("ORIGINAL")
    finally:
        print("\nGit stash pop → restore SLIM...")
        subprocess.run(["git", "stash", "pop"], cwd=str(REPO), check=True)

    if slim and orig:
        delta = slim["total"] - orig["total"]
        pct = (delta / orig["total"] * 100) if orig["total"] else 0
        print("\n=== SUMMARY ===")
        print(f"ORIGINAL total: {orig['total']:>8}")
        print(f"SLIM     total: {slim['total']:>8}")
        print(f"DELTA: {delta:+d} ({pct:+.1f}%)")
        print("\nSYSTEM.md content alone:")
        slim_md = (REPO / "minions/roles/SYSTEM.md").read_text()
        # original is currently restored
        orig_md_chars = 26750  # measured earlier
        slim_md_chars = len(slim_md)
        print(f"  ORIGINAL: ~{orig_md_chars} chars (~{orig_md_chars // 4} tokens)")
        print(f"  SLIM    : ~{slim_md_chars} chars (~{slim_md_chars // 4} tokens)")
        char_savings = orig_md_chars - slim_md_chars
        print(f"  Direct char savings: {char_savings} chars (~{char_savings // 4} tokens)")


if __name__ == "__main__":
    main()
