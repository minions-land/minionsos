#!/usr/bin/env python3
"""PreCompact hook: inject science-aware compaction instructions.

Reads the hook input from stdin (JSON with 'trigger' and 'custom_instructions'),
prints science-aware compact instructions to stdout so the compact model preserves
exploration DAG state, evidence references, and dead ends.
"""

from __future__ import annotations

import json
import sys

SCIENCE_COMPACT_INSTRUCTIONS = """\
You are compacting a science-discovery agent context. Preserve with exact fidelity:

1. NODE IDs: Every node reference (H-xxx, E-xxx, R-xxx, D-xxx) and its current status \
(tentative, verified, refuted, abandoned). These are the agent's exploration graph.

2. EVIDENCE REFERENCES: File paths, commit SHAs, EACN receipt/event IDs, artifact paths. \
These are the only links between claims and proof.

3. DEAD ENDS: Any abandoned hypothesis or failed experiment with its abandonment reason. \
Losing these causes redundant re-exploration.

4. GRAPH POSITION: The current node the agent is working on and its next planned action.

5. BLOCKED DEPENDENCIES: Anything the agent is waiting on (other roles, experiments, data).

Structure your output as:

## New Nodes (this session)
- {node_id}: {type} — {one-line description} ({status})

## Current State
- Working on: {node_id}
- Next action: {concrete step}
- Blocked on: {dependency or nothing}

## Evidence Collected
- {node_id} ← {evidence reference}

## Dead Ends
- {node_id}: {why abandoned}

## Next Steps
- {ordered list of planned actions}

DISCARD: verbose tool outputs, intermediate chain-of-thought, repeated file contents, \
long code listings (keep only the relevant snippet or path reference).
"""


def main() -> None:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            existing = data.get("custom_instructions", "")
        else:
            existing = ""
    except (json.JSONDecodeError, KeyError):
        existing = ""

    # Combine existing instructions with science-aware ones
    parts = []
    if existing:
        parts.append(existing)
    parts.append(SCIENCE_COMPACT_INSTRUCTIONS)

    print("\n\n".join(parts))


if __name__ == "__main__":
    main()
