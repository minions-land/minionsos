---
name: allocate-resources
description: "Build a resource allocation plan for an accepted experiment request"
---

# /allocate-resources — Allocate Experiment Resources

Build a concrete resource plan for an accepted experiment request.

## Goal

Translate an accepted experiment request into a resource allocation plan without doing the actual experiment work.

## Include

- GPU needs
- CPU needs
- memory needs
- storage needs
- expected runtime
- queueing decision
- topic folder placement
- execution dependencies

## Do

- optimize for throughput and coordination
- preserve reproducibility where possible
- make resource constraints explicit

## Do not do

- do not implement the experiment
- do not edit scripts or code
- do not change scientific goals

## Output

Return a resource plan:
- accepted request
- allocated resources
- scheduling slot
- workspace/topic placement
- handoff readiness