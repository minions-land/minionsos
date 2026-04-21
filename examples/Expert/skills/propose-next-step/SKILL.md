---
name: propose-next-step
description: "Propose the next scientific step after considering current evidence and workflow state"
---

# /propose-next-step — Propose Next Scientific Step

Propose the next scientific step for the workflow.

## Goal

Use current evidence, decomposition state, and route comparison to decide what should happen next from the scientific side.

## Include

- current scientific state
- why this next step matters
- what agent type needs to act next
- what uncertainty it reduces
- whether the workflow should explore further or begin converging

## Do

- be explicit about rationale
- keep the next step scientifically grounded
- connect the next move to prior evidence

## Do not do

- do not jump straight into execution ownership
- do not skip over unresolved contradictions

## Output

Return a next-step proposal:
- current state
- proposed next step
- target agent type
- rationale
- expected decision value