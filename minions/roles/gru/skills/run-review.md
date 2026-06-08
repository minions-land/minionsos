---
slug: run-review
summary: Open when a manuscript submission arrives via EACN — gate-check the submission, invoke `mos_review_run`, relay the decision and artifact pointers back through EACN.
layer: logical
tools: mos_review_run, eacn3_send_message
version: 1
status: active
references: feature-intake, eacn3-mcp
provenance: human
---

# Skill — Run Review

Review is a synchronous tool workflow that Gru invokes when a submission is published. This skill names when and how to invoke it.

## When to invoke

- A Role sends Gru an EACN message announcing a paper submission (manuscript + `submission-checklist.md` + any rebuttal/changelog).
- A previously rejected submission is resubmitted with the missing checklist items filled in.
- A revision after a Weak Accept / Borderline / Reject decision arrives.

Do **not** invoke review for:
- Code reviews, experiment-design reviews, or mid-project audits — those are Ethics' job.
- "Quick look" requests without a checklist — ask for a complete submission package instead.

## Structure

One call to `mos_review_run`. The tool gate-checks the checklist; if it rejects, the review is not run. If it completes, the tool returns a decision label, the path to `consolidated.md`, and the rolling summary path. Gru relays both to the submitting Expert and to any Role with actionable follow-ups.

## Procedure

1. **Verify the submission package.** The EACN message must name a submission directory containing at minimum the manuscript PDF and `submission-checklist.md`. If either is missing, reply on EACN asking for a complete package; do not invoke the tool.
2. **Locate the prior rolling summary if any.** If this is round ≥ 2, check `branches/shared/reviews/summaries/round-<n-1>.md`. Pass its path as `prior_summary_path` so Pass B / Pass C can run.
3. **Call `mos_review_run`** with `port`, `submission_path`, and optional `prior_summary_path`. The tool blocks until the round finishes.
4. **Handle the response shape:**
   - `status == "rejected"`: relay `missing_required` to the submitting Role with a brief EACN message; do not paraphrase or soften. The author needs to know exactly which items are missing.
   - `status == "completed"`: post an EACN message to the submitting Role with the decision label, `consolidated_path`, and `summary_path`. Include the consolidated.md content inline when small; otherwise just the pointer.
   - `status == "error"`: surface the failure to the author. Do not retry blindly — diagnose first.
5. **Route actionable dependencies.** If the decision contains required revisions that obviously belong to another Role, publish targeted EACN follow-up tasks. Do not let everything funnel back through the submitting Role.
6. **Stop.** No further review-related action until a new submission arrives.

## Pitfalls

- Invoking review on a partial submission to "see what comes back" — the gate exists precisely to prevent this; trust it.
- Reading `consolidated.md` and editorializing the decision before relaying it. The decision is the Area-Chair's; Gru relays, not interprets.
- Addressing review follow-ups to an EACN agent. Use `mos_review_run` for submission review and route resulting action items to the appropriate project Roles.
- Calling `mos_review_run` for an Ethics-shaped request (mid-project evidence audit, claim-validity check, adjudication). Route those to Ethics on the project's Local EACN instead.
