# CLAUDE.md

Guidance for a Claude Code session working in the **MinionsOS codebase**.
Runtime Role agents do not read this file — their contract is
`minions/roles/SYSTEM.md`, injected via `--append-system-prompt`.

## What this is

MinionsOS is a local multi-agent OS for autonomous research projects. A
persistent Gru process supervises isolated paper-sized projects; each has its
own EACN3 backend, git worktrees, and long-lived Role processes (Gru / Ethics /
Expert) hosted by Claude Code.

## Install

```bash
./install.sh        # idempotent: uv, Python 3.11, EACN3, node plugin, .mcp.json
./mos doctor        # verify the environment
```

## The handbook

`MANUAL/` is the progressive-disclosure handbook for both contributors and
agents — the single source of truth for tools, domains, and known pitfalls.
Open it instead of grepping blindly:

```bash
python3 MANUAL/scripts/lookup.py <query>           # search
python3 MANUAL/scripts/lookup.py --domain memory   # list a domain's pages
python3 MANUAL/scripts/lookup.py --kind pitfall <q> # known-failure pages
python3 MANUAL/scripts/lookup.py --id <tool_name>  # one tool page
```

Common entry points: `--domain eacn3`, `--domain memory`, `--domain publish`,
`--domain skills`, `--domain runtime`.

## The one load-bearing dev rule

**Tool-use input must stay small (Opus empty-input bug).** Never inline a large
payload in a single `tool_use` — not `Write.content`, `Edit.new_string`, nor a
`Bash` heredoc. Hard cap ~50 lines / ~3 KB per call. For anything larger, seed
with one short `Write`, then append with successive `Edit` calls. Full recipe:
`minions/roles/common/skills/reliable-file-io.md`. This is mandatory for long
Markdown / LaTeX / CJK content — the exact shapes that trigger the bug.

## Where to look when something breaks

| Symptom | Look |
|---|---|
| Gru process | `minions/state/logs/gru.log` |
| Project backend | `projects/project_{port}/logs/backend.log` |
| Role crash / behavior | `projects/project_{port}/logs/role-{name}.log` |
| Anything else | `python3 MANUAL/scripts/lookup.py <query>` |
