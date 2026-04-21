---
name: publish-task
description: "Publish a normalized task to EACN and record the publication event"
---

# /publish-task — Publish to EACN

Publish a prepared task to EACN and record that publication in the Noter workflow log.

## Goal

Noter is responsible for publication and tracking, not scientific decomposition. Use this skill only after the task description is already clear enough to publish.

## Step 1 — Confirm task payload

Ensure the task description includes:
- objective
- enough context for downstream agents
- known constraints
- expected outputs if available

## Step 2 — Publish via EACN

Use the appropriate EACN task creation flow.

## Step 3 — Record publication

After publishing, log:
- timestamp
- task identifier
- publishing agent
- topic/theme
- linked branch if relevant
- short factual note

## Do

- publish clearly scoped tasks
- preserve links between published tasks and the active theme
- make sure Noter remains attached for recording purposes

## Do not do

- do not silently rewrite the scientific goal
- do not invent expert consensus
- do not drop the task from Noter tracking after publication

## Output

Return a short structured publication record:
- published task
- task id
- time
- theme
- status
- follow-up tracking note