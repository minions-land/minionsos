---
name: stage-summary
description: "Generate a human-facing stage summary from the current workflow state"
---

# /stage-summary — Human-Facing Stage Summary

Generate a structured stage summary for the human.

## Goal

Provide a concise, readable overview of the current workflow state without introducing new scientific decisions.

## Include

- objective
- current stage
- active tasks
- key recent events
- decisions already made by experts
- blockers or unresolved dependencies
- next expected actions

## Style

- concise
- operator-facing
- status-first
- no unnecessary theory

## Do not do

- do not tell the human what scientific strategy should be chosen unless Experts have already decided
- do not request human intervention unless breakpoint mode has been explicitly enabled

## Output

Produce a stage summary suitable for saving under `Noter/stages/` and for directly showing to the human.