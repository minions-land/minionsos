#!/bin/bash
# A/B: original SYSTEM.md vs slim SYSTEM.md cold-start cost
# Run each variant 3 times; report median input_tokens.

set -e
cd /Users/mjm/MinionsOS

run_n() {
  local label="$1"
  local n="$2"
  echo "=== $label (n=$n) ==="
  for i in $(seq 1 "$n"); do
    python3 tests/manual/measure_context_slim.py 2>&1 \
      | grep -A1 "AFTER total" | tail -1
  done
}

echo "STEP 1 — measuring SLIM (current state)"
run_n "SLIM" 3

echo ""
echo "STEP 2 — switching to ORIGINAL via git"
git stash > /dev/null
echo "STEP 3 — measuring ORIGINAL"
run_n "ORIGINAL" 3

echo ""
echo "STEP 4 — restoring SLIM"
git stash pop > /dev/null
