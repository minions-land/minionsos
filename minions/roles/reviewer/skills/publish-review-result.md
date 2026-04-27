# Skill - Publish Review Result

Publish a completed review round through Local EACN.

## Core Move

Make one self-contained markdown packet easy for the project team to act on:
notification, meta-review, decision, required revisions, revision-delta
highlights, and all individual reviewer reports.

## Procedure

1. Verify `artifacts/reviews/round-<n>/consolidated.md` exists and contains:
   - notification;
   - Area-Chair / Editor meta-review;
   - exact `## Decision`;
   - required revisions or camera-ready instructions;
   - revision-delta highlights when applicable;
   - all generated reviewer reports.
2. Publish through Local EACN. Prefer creating or replying with a task whose body
   includes the full `consolidated.md` content so downstream roles can read one
   markdown object.
3. If the packet is too large for the EACN message body, include a concise
   notification plus the artifact pointer:
   `artifacts/reviews/round-<n>/consolidated.md`.
4. Target the action implied by the decision:
   - `Strong Accept` / `Accept`: camera-ready cleanup.
   - `Weak Accept` / `Borderline`: revision task for Writer plus evidence tasks
     for Expert / Experimenter / Coder as needed.
   - `Weak Reject` / `Reject` / `Strong Reject`: substantial revision or
     project-level reconsideration before another review round.
5. Keep Reviewer main as the only EACN-facing speaker. Local subagents do not
   publish.

## Pitfalls

- Sending only the decision label without the individual reviews.
- Splitting the meta-review and reviewer reports across many messages when one
  self-contained packet is possible.
- Asking Gru to interpret the decision before Reviewer has published the review
  packet.

## Output Habit

End with a clear EACN task/message: review round number, decision, required next
action, and either full consolidated markdown or the consolidated artifact path.
