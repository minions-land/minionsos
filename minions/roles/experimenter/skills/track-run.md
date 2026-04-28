# Skill — Track Run

Maintain operational visibility over detached experiments without blocking on them.

## Core move

On each wake-up, use `exp_queue_status` / `exp_queue_reconcile` to inspect durable queue state, surface anomalies, and collect completed results. Experimenter is ephemeral (root §6); the Python queue and detached experiments are not.

## Procedure

1. **Recover state on cold start.** Call `exp_queue_status(batch_id?)`. The scheduler DB is authoritative for queued/running/completed units.
2. **Poll cheaply.** Prefer `exp_queue_reconcile` and `exp_queue_status`; tail logs with `exp_tail` only when a run looks stuck or anomalous.
3. **Wait narrowly.** Call `exp_wait(target_id, run_id, timeout=<short>)` only when one specific downstream action truly blocks on one specific run — never as a default loop primitive.
4. **Detect anomalies.** NaN loss, GPU util collapse for > 2× expected step time, log silence past a threshold — each warrants an EACN heads-up to the requester. Do not unilaterally kill a slow-but-healthy job.
5. **Handle failures.** On OOM or crash, follow `SYSTEM.md`: re-queue once; circuit-break after 3 consecutive same-script failures and broadcast to Gru + requester.
6. **Route blame correctly.** Code tracebacks → Coder via EACN (include log path). Design/metric failures → the requesting Expert. Operational issues stay with you.

## When to invoke

- Every ephemeral wake-up where any run is in flight.
- When `exp_status` or `exp_tail` suggests anomaly and you must decide kill vs wait vs escalate.

## Pitfalls

- Polling with long `exp_wait` loops — violates fire-and-poll and starves other runs.
- Killing a run because it "feels slow" without tailing the log first.
- Forgetting that in-memory state did not survive — always re-list before acting.

## Output habit

A short tracking note per wake-up (EACN or scratchpad): `batch_id → {summary, anomalies?}`, plus any escalation emitted. Mark status facts `[derived: exp_queue_status @ <ts>]` / `[derived: exp_tail lines N..M]` per root §9.
