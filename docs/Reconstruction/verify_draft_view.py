"""实践出真理: verify mos_draft_view subsumes the 4 retired read tools.

Not a unit test — a measured proof on a realistic multi-role Draft that the
single unified read answers every question the old query/relevant/summary/
topic_index answered, and that cold-start (no hot.md) still orients a role.

Run: MINIONS_FAKE_CLAUDE=1 uv run python docs/Reconstruction/verify_draft_view.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

PORT = 9911
_tmp = Path(tempfile.mkdtemp())
os.environ["MINIONS_PROJECT_PORT"] = str(PORT)

from minions.tools import draft  # noqa: E402


def _sub(p, subdir):
    t = _tmp / f"project_{p}" / "branches" / "shared" / subdir
    t.mkdir(parents=True, exist_ok=True)
    return t


draft.project_shared_subdir = _sub
draft.project_shared_draft_json = lambda p: _sub(p, "draft") / "draft.json"


def seed():
    """A realistic multi-role research Draft: 3 roles, mixed types/statuses."""
    nodes = [
        {"id": "H-001", "type": "hypothesis", "text": "Residual connections enable very deep nets",
         "support_status": "verified", "author_role": "expert-ml", "confidence": 0.9,
         "created_at": "2026-06-01T10:00:00"},
        {"id": "E-001", "type": "experiment", "text": "Train ResNet-50 vs plain-34 on ImageNet",
         "support_status": "verified", "author_role": "expert-ml", "confidence": 0.85,
         "created_at": "2026-06-01T11:00:00"},
        {"id": "R-001", "type": "result", "text": "ResNet-50 hit 76.1% top-1, plain-34 diverged",
         "support_status": "verified", "author_role": "expert-ml", "confidence": 0.95,
         "created_at": "2026-06-01T12:00:00"},
        {"id": "DEAD-001", "type": "dead_end", "text": "Plain-34 without residuals diverged at depth",
         "support_status": "verified", "author_role": "ethics", "confidence": 1.0,
         "created_at": "2026-06-01T12:30:00"},
        {"id": "D-001", "type": "decision", "text": "Use ResNet-50 backbone for all downstream work",
         "support_status": "verified", "author_role": "gru", "confidence": 0.9,
         "created_at": "2026-06-01T13:00:00"},
        {"id": "H-002", "type": "hypothesis", "text": "Batch size barely affects final accuracy",
         "support_status": "unverified", "author_role": "expert-ml", "confidence": 0.4,
         "created_at": "2026-06-01T14:00:00"},
        {"id": "Q-001", "type": "question", "text": "Should we sweep learning rate next?",
         "support_status": "unverified", "author_role": "expert-ml", "confidence": 0.5,
         "created_at": "2026-06-01T15:00:00", "metadata": {"pending_plan": True}},
    ]
    edges = [
        {"from_id": "E-001", "to_id": "H-001", "relation": "tests"},
        {"from_id": "R-001", "to_id": "E-001", "relation": "derived_from"},
        {"from_id": "DEAD-001", "to_id": "H-001", "relation": "supports"},
        {"from_id": "D-001", "to_id": "R-001", "relation": "derived_from"},
    ]
    draft.mos_draft_append(nodes=nodes, edges=edges)


# CHECKS_PLACEHOLDER


def main() -> int:
    seed()
    checks: list[tuple[str, bool, str]] = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # Q1 (was mos_draft_summary): cold-start orient — header with totals + pending.
    v = draft.mos_draft_view()
    check("orient: totals.nodes==7", v["totals"]["nodes"] == 7, str(v["totals"]))
    check("orient: pending_plans surfaced", v["pending_plans_total"] == 1
          and v["pending_plans"][0]["id"] == "Q-001", str(v["pending_plans"]))
    check("orient: newest-first (Q-001 heads slice)", v["nodes"][0]["id"] == "Q-001",
          v["nodes"][0]["id"])
    check("orient: nodes_by_type present", v["nodes_by_type"].get("hypothesis") == 2,
          str(v["nodes_by_type"]))

    # Q2 (was mos_draft_query filters): by_role / by_status / by_type.
    vr = draft.mos_draft_view(by_role="expert-ml")
    check("by_role=expert-ml → only that role", vr["nodes"]
          and all(n["author_role"] == "expert-ml" for n in vr["nodes"]),
          {n["id"]: n["author_role"] for n in vr["nodes"]})
    vs = draft.mos_draft_view(by_status="verified")
    check("by_status=verified → only verified", vs["nodes"]
          and all(n["support_status"] == "verified" for n in vs["nodes"]),
          {n["id"]: n["support_status"] for n in vs["nodes"]})
    vt = draft.mos_draft_view(by_type="dead_end")
    check("by_type=dead_end → only DEAD-001",
          [n["id"] for n in vt["nodes"]] == ["DEAD-001"],
          [n["id"] for n in vt["nodes"]])

    # Q3 (was mos_draft_query related_to): 1-hop neighbourhood.
    vn = draft.mos_draft_view(related_to="H-001")
    nbr = {n["id"] for n in vn["nodes"]}
    check("related_to=H-001 → 1-hop neighbours", {"H-001", "E-001", "DEAD-001"} <= nbr, sorted(nbr))

    # Q4 (was mos_draft_relevant): free-text relevance push + ranking.
    vq = draft.mos_draft_view(query="residual connections deep network ResNet", sort="relevance")
    top_ids = [n["id"] for n in vq["nodes"]]
    check("query surfaces residual/ResNet nodes", "H-001" in top_ids and "R-001" in top_ids, top_ids)
    check("query ranks unrelated batch-size node lower",
          "H-002" not in top_ids[:2], top_ids)

    # Q5 (was mos_draft_topic_index, by-time discovery): sort=time newest-first.
    vtime = draft.mos_draft_view(sort="time", limit=3)
    ids = [n["id"] for n in vtime["nodes"]]
    check("sort=time newest-first top-3", ids == ["Q-001", "H-002", "D-001"], ids)

    # Cold-start без hot.md: a single no-arg call reconstructs orientation.
    cold = draft.mos_draft_view()
    check("cold-start single call gives header+slice (no hot.md needed)",
          cold["pending_plans_total"] == 1 and cold["totals"]["nodes"] == 7
          and len(cold["nodes"]) > 0, "")

    # Report.
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{'=' * 60}\nmos_draft_view verification — {passed}/{len(checks)} checks\n{'=' * 60}")
    for name, ok, detail in checks:
        mark = "✓" if ok else "✗"
        line = f"  {mark} {name}"
        if not ok:
            line += f"   [got: {detail}]"
        print(line)
    print(f"{'=' * 60}")
    print(json.dumps({"passed": passed, "total": len(checks),
                      "all_green": passed == len(checks)}))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

