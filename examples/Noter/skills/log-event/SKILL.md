---
name: log-event
description: "Write an objective workflow log entry with timestamps, references, and artifacts"
---

# /log-event — Record Objective Event

Write an objective workflow log entry for the active MinionsOS theme.

## Goal

Capture facts, not decisions you invented.

Noter must participate in every task under the active theme, so use this skill whenever there is a meaningful event, transition, artifact, or agent-visible outcome.

## Include when available

- timestamp
- event type
- related theme
- related task
- related agent or agents
- related branch
- artifact paths or artifact identifiers
- factual note

## Good examples

- task published
- experiment requested
- expert consensus recorded
- review round completed
- paper draft updated
- artifact delivered
- stage changed

## Do not do

- do not speculate about intent
- do not rewrite facts as conclusions
- do not use the log as agent-to-agent communication

## Output

Produce a concise log entry suitable for saving under `Noter/logs/`.