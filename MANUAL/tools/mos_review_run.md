---
id: mos_review_run
kind: tool
domain: deliverables
auth: [gru]
source: minions/tools/mcp/experiment_tools.py:16
since: stable
keywords: [review, submission, checklist, area-chair, deliverable, paper]
related: [mos_submit, mos_evaluate, mos_promote_to_book]
status: stable
---

# mos_review_run

**One line:** Gru-only Area-Chair review round for a submitted manuscript package.

## Signature
```py
mos_review_run(args={
  "port": int,
  "submission_path": str,
  "prior_summary_path": str | None,
}) -> dict
```

## Args
- `port`: project port that owns the submission.
- `submission_path`: absolute path, or path relative to the project main
  workspace, for a submission directory.
- `prior_summary_path`: optional previous-round summary path for revision rounds.

The submission directory must contain `submission-checklist.md` and a compiled
manuscript PDF, normally `build/paper.pdf`.

## Behaviour
- Rejects immediately when the required checklist is missing or unchecked.
- Rejects when the package has no real compiled PDF manuscript.
- Runs one bounded Area-Chair process that drives the three-pass review.
- Validates artifacts on disk before returning; it does not trust process exit
  code alone.
- Writes review outputs under `branches/main/reviews/` and commits them when
  the shared worktree is available.

## Returns
```py
{"status": "rejected", "reason": str, "missing_required": [str]}
{"status": "error", "reason": str, "round": int, ...}
{
  "status": "completed",
  "round": int,
  "decision": str,
  "consolidated_path": str,
  "summary_path": str,
  "shared_commit_sha": str | None,
}
```

## Don't
- Don't route this through the drafting Expert. The Expert publishes the
  submission; Gru invokes the review gate.
- Don't write directly into `branches/main/reviews/`; this tool owns that tree.
