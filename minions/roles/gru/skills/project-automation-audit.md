---
slug: project-automation-audit
summary: Open after a new project's first workflow stabilizes, or when the author asks "what automation should we add?" — read-only scan that recommends ≤2 low-risk automations per category.
layer: logical
tools:
version: 2
status: active
supersedes:
references: feature-intake, role-skill-design
provenance: human
---

# Skill — Project Automation Audit

Low-risk agent-host / MinionsOS automations that fit a project's actual workflow. Advisory by default.

## When to invoke

- A new project has been bootstrapped and its first workflow has stabilized.
- The author asks "what automation should we add?"
- Multiple roles repeatedly hit the same manual coordination or validation step.

## Structure

Read-only scan of `CLAUDE.md`, `meta.json`, recent EACN history, active roles, scripts, tests, dashboard. Up to two recommendations per category (role skills, slash-command-like workflows, hooks, MCP integrations, tests, dashboard views, subagent prompts). Each recommendation classified `install now` / `draft skill` / `backlog` / `reject` and grounded in project evidence. Risks flagged when touching secrets, runtime state, cross-project isolation, generated output, or heavy compute.

## Procedure

1. **Read the project shape.** `CLAUDE.md`, `meta.json`, recent EACN history, active roles, scripts, tests, dashboard needs.
2. **Find repeated friction.** Recurring failures, manual checks, missing role skills, fragile handoffs, stale docs, review bottlenecks.
3. **Recommend at most two per category** — role skills, slash-command-like workflows, hooks, MCP integrations, tests, dashboard views, subagent prompts.
4. **Separate now vs later.** Mark each `install now`, `draft skill`, `backlog`, or `reject`.
5. **Check risk.** Flag anything that could touch secrets, runtime state, cross-project isolation, generated output, or heavy compute.
6. **Route follow-up.** Use `feature-intake` for accepted work; otherwise leave the audit as a note.
7. **Write a short audit** with `recommended now`, `backlog`, and `not recommended` sections, each grounded in project evidence.

## Pitfalls

- Recommending a hook or MCP server because it sounds useful, without an EACN history entry or role log line that shows the friction it would solve.
- Installing plugins, hooks, or MCP servers during the audit.
- Adding automation that makes role behavior less observable on EACN.
- Optimizing for novelty instead of reducing actual friction.
