---
name: sync-branch
description: "Standard git sync + branch-level CLAUDE.md update flow shared by every agent under examples/"
---

# /sync-branch — Sync Work To Branch

Shared checkout/update/commit/push flow used by every agent type. Agents are stateless; this skill is how work becomes durable.

## Goal

Ensure all durable work lives on the assigned GitHub branch, and that the branch's `CLAUDE.md` always reflects the current state so the next agent of the same type can take over with only `git pull`.

## When to use

- **on pickup**: first thing after receiving an EACN task with `{repo_url, branch}`
- **before handoff**: any time you return a result to EACN, finish a stage, or go idle
- **when citing an artifact**: whenever you want to point another agent at your work

## Pickup flow

1. `git clone` the shared repo if not already cloned, otherwise `git fetch origin`
2. `git checkout <branch>` and `git pull --ff-only`
3. read the branch's `CLAUDE.md` end-to-end before doing anything else
4. follow its "Current state" and "Handoff notes" to resume work

## Handoff flow

1. stage new/changed artifacts; keep any single file over 500MB out of the branch
2. update the branch's `CLAUDE.md` fields:
   - **What's been done**: prepend a new human-readable entry
   - **Current state**: rewrite to reflect the truth right now
   - **Artifacts produced**: add new paths with one-line descriptions
   - **Handoff notes**: leave a message for the next same-type agent
3. `git add -A && git commit -m "<short semantic message>"`
4. `git push` (use `--force-with-lease` only if EACN lease makes you the exclusive writer)
5. capture the new commit hash and include `{repo_url, branch, commit}` in the EACN message you send back

## Do

- always update `CLAUDE.md` in the same commit as the artifact it describes
- reference other agents' work by `{branch, commit}`, not by copying files across branches
- keep commits semantic, not dumps

## Do not do

- do not write to a branch you do not own
- do not push large binaries; use LFS or an external store and commit a pointer
- do not skip the `CLAUDE.md` update, even for small commits

## Output

Return `{repo_url, branch, commit, claude_md_path}` so the caller can embed it in the EACN reply.
