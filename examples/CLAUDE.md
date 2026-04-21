# examples/ — scoping rule for `/init`

This directory holds multiple independent example agents, each in its own sibling folder (e.g. `Experiment/`, `Expert/`, `Noter/`, `Paper/`, `Reviewer/`). They are **not** one combined project — each subfolder is its own self-contained agent example.

## Scoping rule

If your current working directory is `/Users/mjm/MinionsOS/examples/XXX` (for some specific `XXX`), then when running `/init` or otherwise building a project understanding:

- **Only inspect the `XXX/` folder.** Treat it as the root of the project you are documenting.
- **Skip every other sibling folder** under `/Users/mjm/MinionsOS/examples/` (i.e. any `examples/*` that is not `XXX`). Do not read, summarize, or reference them.
- **Do not ascend** into `/Users/mjm/MinionsOS/` to scan the wider repo for this `/init`; stay scoped to `XXX/`.
- `examples/quickstart.py` and this `examples/CLAUDE.md` itself are **not** part of `XXX` and should also be skipped during `/init`.

## Why

Each `XXX/` agent example has its own responsibilities, prompts, and assets. Mixing them during `/init` produces a `CLAUDE.md` that conflates unrelated agents and leaks information across example boundaries. Keeping each `/init` strictly scoped to its own `XXX/` folder preserves that isolation.

## Summary

When cwd is `examples/XXX`, `/init` sees exactly one thing: `XXX/`. Everything else under `examples/` is out of scope.

---

# General EACN usage rules (apply to every agent under `examples/`)

These rules are shared across all example agents (`Experiment/`, `Expert/`, `Noter/`, `Paper/`, `Reviewer/`, …). They define how any agent participates in the team task on the EACN network. Each agent's own `CLAUDE.md` may add role-specific behavior on top of these, but must not contradict them.

## Communication standards

### File sharing
All agents share files by creating **independent branches** in a single shared repository under the `Minions-Land` GitHub org (https://github.com/Minions-Land). Each agent works on its own branch; cross-agent file exchange happens via branches, not direct file copies.

**Shared repo URL (requires human confirmation):**

- `<TO BE CONFIRMED BY HUMAN>` — the human operator should fill in the exact repo URL here before agents start.
- **Fallback**: if the human does not supply one, the first agent to reach this step should create a new empty repo under `https://github.com/Minions-Land/` (suggested name: `minionsos-team-share`), record its full URL in this `CLAUDE.md` in place of the placeholder above, and notify the team.

### Sending and receiving information
All inter-agent information exchange **must** go through the task publish/receive interface of the `eacn3` MCP plugin. Do not invent side channels or hand-crafted HTTP calls — use the `eacn3_*` tools.

**Workflow for every agent:**

1. Try to solve the assigned task yourself first.
2. When you hit a sub-part that another teammate is better at, **publish a task** via `eacn3` that invites that teammate.
3. While waiting for their result, keep processing tasks other teammates have sent to you.
4. Integrate the returned result and continue.

**Special rule for this team task:**

- Every published task **must specify an invitee**.
- Every published task **must have amount = 0**.

### Agent specialization
Agents identify and expand their strengths through continuously completing tasks. Over time, each agent should become the clear go-to for certain kinds of sub-work.

## Solving rules

### Startup process
On receiving its identity, every agent system must:

1. **Prepare its local environment.**
2. **Register an account** on the EACN network matching its identity, and report the registered ID back to the user.
3. **Schedule a cron job** that calls the `next` tool of the `eacn3` plugin every **5 minutes**. Whatever `next` returns **must be executed strictly**, including plain-text instructions returned when there are no external events.

### Collaboration trigger
Agents may **actively** start the collaborative solving flow **only after the team task is officially set** on the EACN network. Before that point, an agent's only job is to keep processing whatever the `next` tool returns.

### Work record
All agents record their work in their own git branch. **Exclude any data volumes larger than 500MB** from the branch.

