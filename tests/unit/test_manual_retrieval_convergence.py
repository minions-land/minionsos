"""Convergence tests for MANUAL retrieval — the concept→tool gap.

Motivated by a live Gru trace: phrased its intent as "attach/activate/wake a
role" and the lifecycle tool it needed (mos_project_revive, mos_dismiss_role,
etc.) never surfaced, so it burned 30+ turns guessing. These tests pin that
retrieval now bridges the user's *intent vocabulary* to the tool's *named*
vocabulary via synonym expansion + body-harvested keywords + an exact-name
boost.

Standard: the right tool must appear in the top-K (K=3 for intent queries,
top-1 for exact-name queries). We deliberately do NOT assert top-1 for
ambiguous intent phrasings — a query that literally says both "revive" and
"dormant" has honest multiple readings, and the contract's fallback (look at
`--domain lifecycle` / Gru §G0) covers the tie. Over-fitting top-1 on every
phrasing would be tuning to the test, not fixing retrieval.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _query(q: str) -> list[str]:
    out = subprocess.run(
        [sys.executable, "MANUAL/scripts/lookup.py", q, "-k", "5"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    ids: list[str] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            ids.append(line.split("]", 1)[1].strip().split()[0])
    return ids


# (query, expected_tool, max_rank) — intent phrasings a role would actually type
INTENT_CASES = [
    ("wake up dormant project roles", "mos_project_revive", 3),
    ("start project agents that already exist", "mos_project_revive", 3),
    ("attach role resume activate", "mos_attach_role", 3),
    ("how do I bring a sleeping project back", "mos_project_revive", 3),
    ("shut down a role for good", "mos_dismiss_role", 4),
]

# (query, expected_top1) — near-exact tool names must win outright
EXACT_CASES = [
    ("dismiss a role", "mos_dismiss_role"),
    ("attach role", "mos_attach_role"),
    ("kill role", "mos_kill_role"),
    ("create new project", "mos_project_create"),
    ("send message to peer", "eacn3_send_message"),
    ("publish artifact to another role", "mos_publish_to_shared"),
    # trace-derived: Gru tried `from minions.lifecycle import create_project`
    # instead of the tool; retrieval must point at the tool for that intent.
    ("create a project", "mos_project_create"),
    ("send a message as gru", "eacn3_send_message"),
]


@pytest.mark.parametrize("query,expected,max_rank", INTENT_CASES)
def test_intent_query_surfaces_right_tool(query: str, expected: str, max_rank: int) -> None:
    ids = _query(query)
    assert expected in ids[:max_rank], f"{expected!r} not in top-{max_rank}: {ids[:max_rank]}"


@pytest.mark.parametrize("query,expected", EXACT_CASES)
def test_exact_name_query_wins_top1(query: str, expected: str) -> None:
    ids = _query(query)
    assert ids and ids[0] == expected, f"top-1 was {ids[:1]}, expected {expected!r}"
