# Skill — Project Automation Audit

Recommend low-risk agent-host/MinionsOS automations that fit a project's actual
workflow.

## Core move

Scan a project read-only and propose the smallest automation set that would
remove recurring friction. This is advisory unless the author explicitly asks
Gru to install or edit something.

## Procedure

1. **Read the project shape.** Inspect `CLAUDE.md`, `meta.json`, recent EACN
   history, active roles, scripts, tests, and dashboard needs.
2. **Find repeated friction.** Look for recurring failures, manual checks,
   missing role skills, fragile handoffs, stale docs, or review bottlenecks.
3. **Recommend at most two per category.** Categories include role skills,
   slash-command-like workflows, hooks, MCP integrations, tests, dashboard views,
   and subagent prompts.
4. **Separate now vs later.** Mark each suggestion as `install now`, `draft
   skill`, `backlog`, or `reject`.
5. **Check risk.** Flag anything that could touch secrets, runtime state,
   cross-project isolation, generated output, or heavy compute.
6. **Route follow-up.** Use `feature-intake` for accepted work; otherwise leave
   the audit as a note.

## When to invoke

- A new project has been bootstrapped and its first workflow has stabilized.
- The author asks "what automation should we add?"
- Multiple roles repeatedly hit the same manual coordination or validation step.

## Pitfalls

- Recommending generic tooling without evidence from this project.
- Installing plugins, hooks, or MCP servers during the audit.
- Adding automation that makes role behavior less observable on EACN.
- Optimizing for novelty instead of reducing actual friction.

## Output habit

Write a short audit with `recommended now`, `backlog`, and `not recommended`
sections, each grounded in project evidence.
