---
name: track-run
description: "Track the status, resources, anomalies, and artifacts of delegated experiment execution"
---

# /track-run — Track Delegated Execution

Track the progress and operational state of delegated experiment work.

## Goal

Monitor delegated execution without taking over the work.

## Track

- current status
- elapsed time
- resource usage
- anomalies
- failures
- partial outputs
- artifact generation
- reproducibility notes if available

## Do

- maintain operational visibility
- surface blockers early
- keep logs and tracking records current

## Do not do

- do not jump into hands-on execution just because a run is failing
- do not reinterpret scientific meaning

## Output

Return a run tracking note:
- execution unit
- status
- resource usage
- issues
- artifacts
- next operational action