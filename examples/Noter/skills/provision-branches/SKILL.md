---
name: provision-branches
description: "Provision the shared GitHub repo and per-agent branches for a new team task, and seed each branch with a handoff CLAUDE.md"
---

# /provision-branches — Provision Task Branches

Set up the per-agent branch layout on the shared `Minions-Land` repo when a new team task is published, so every agent has a stateless place to work.

## Goal

All agents are stateless. Their persistent state lives only on GitHub branches. Noter is responsible for creating those branches up front and announcing them through EACN so the right agent can pick up the branch regardless of which Claude window is alive.

## When to use

- immediately after `intake-task`, before `publish-task`
- whenever a new collaborator type is added mid-task and needs its own branch

## Include

- task id and short slug
- target repo under `https://github.com/Minions-Land/` (create if missing, suggested name `minionsos-team-share` unless human specified another)
- the branch set to create, typically:
  - `expert/<task-id>`
  - `experiment/<task-id>`
  - `paper/<task-id>`
  - `reviewer/<task-id>/round-1`
  - additional review rounds added on demand
- seed `CLAUDE.md` on each branch describing:
  - branch purpose and owning agent type
  - task context from intake
  - upstream branches and dependency commits (if any)
  - current state (empty / in progress / delivered)
  - handoff notes for the next agent of the same type

## Do

- create branches from a clean `main` commit
- commit an initial `CLAUDE.md` on each branch before announcing it
- attach `{repo_url, branch, claude_md_path}` to every EACN task message so agents can locate their branch
- treat the branch list as authoritative; later skills reference it

## Do not do

- do not write scientific content into the seed `CLAUDE.md`
- do not mix multiple agents' working areas on one branch
- do not delete branches from completed tasks; archive by tag instead

## Output

Return a provisioning record:
- repo url
- branch list with purpose and owning agent type
- seed commit hash for each branch
- EACN announcement payload template `{repo_url, branch, claude_md_path}`
