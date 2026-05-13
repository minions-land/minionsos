---
slug: track-run
summary: Maintain operational visibility over detached experiments without blocking on them; poll cheaply via exp_queue_status / exp_queue_reconcile, escalate anomalies through EACN.
layer: logical
tools: exp_queue_status, exp_queue_reconcile, exp_tail, exp_wait, exp_status
version: 2
status: active
supersedes:
references: dispatch-runner, collect-report
provenance: human
---

# Skill — Track Run

Experimenter is ephemeral; the Python queue and detached experiments are not. Every wake-up uses `exp_queue_status` / `exp_queue_reconcile` to recover state, surface anomalies, collect completed results.

## When to invoke

- Every ephemeral wake-up where any run is in flight.
- When `exp_status` or `exp_tail` suggests anomaly and you must decide kill vs. wait vs. escalate.

## Structure

Cold-start recovery first; cheap polling next; narrow waits only when one specific downstream action truly blocks on one specific run. Anomalies trigger EACN escalation rather than unilateral kills. Concrete anomaly thresholds:

- **NaN loss**: any single NaN observation is reportable.
- **GPU util collapse**: util drops > 50 % for longer than 2× the expected per-step time.
- **Log silence**: no log output for > 10 min on a run expected to emit per-step logs (or 30 min for slow batch jobs).

Failure routing: code tracebacks → Coder (with log path); design / metric failures → requesting Expert; operational issues stay with you.

## Procedure

1. **Recover state on cold start.** `exp_queue_status(batch_id?)`. The scheduler DB is authoritative for queued / running / completed units.
2. **Poll cheaply.** Prefer `exp_queue_reconcile` and `exp_queue_status`; tail logs with `exp_tail` only when a run looks stuck or anomalous.
3. **Wait narrowly.** `exp_wait(target_id, run_id, timeout=<short>)` only when one specific downstream action truly blocks on one specific run — never as a default loop primitive.
4. **Detect anomalies** per the Structure thresholds (NaN loss, GPU util collapse > 50 % past 2× expected step time, log silence > 10 min for fast jobs / > 30 min for batch jobs). Each warrants an EACN heads-up to the requester. Do not unilaterally kill a slow-but-healthy job.
5. **Handle failures.** On OOM or crash: re-queue once; circuit-break after 3 consecutive same-script failures and broadcast to Gru + requester.
6. **Route blame correctly.** Code tracebacks → Coder via EACN (include log path). Design / metric failures → the requesting Expert. Operational issues stay with you.
7. **Write a tracking note per wake-up** (EACN or scratchpad): `batch_id → {summary, anomalies?}`, plus any escalation emitted. Mark status facts `[derived: exp_queue_status @ <ts>]` / `[derived: exp_tail lines N..M]`.

## Pitfalls

- Polling with long `exp_wait` loops — violates fire-and-poll and starves other runs.
- Killing a run because it "feels slow" without tailing the log first.
- Forgetting that in-memory state did not survive — always re-list before acting.
