---
name: request-experiment
description: "Translate scientific needs into experiment requests for Experiment agents"
---

# /request-experiment — Request Scientific Experiment Support

Translate scientific needs into experiment requests for Experiment agents.

## Goal

Experts should express what evidence is needed without taking over resource scheduling or implementation.

## Include

- scientific question the experiment should answer
- why the experiment matters
- what comparison, control, or ablation is needed
- what outcomes would change the scientific interpretation
- what artifacts or results should come back

## Do

- be specific about scientific purpose
- make success criteria meaningful
- connect the request to hypotheses or route decisions

## Do not do

- do not prescribe low-level resource scheduling
- do not turn the request into hands-on code instructions unless absolutely necessary as scratch guidance

## Output

Return an experiment request:
- scientific goal
- requested evidence
- expected outputs
- interpretation impact
- priority