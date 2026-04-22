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

## Python environment management

All agents must use **`uv`** to manage Python environments and dependencies.

- Use `uv venv` to create virtual environments and `uv pip` to install packages.
- If a project or branch uses conda (`environment.yml`, `conda` commands), convert it to `uv` before proceeding:
  1. Extract dependencies from `environment.yml` or `conda list --export` into a `requirements.txt` or `pyproject.toml`.
  2. Remove conda-specific files (`environment.yml`, `.condarc`) from the branch.
  3. Create the environment with `uv venv` and install with `uv pip install -r requirements.txt`.
- Do not use `conda`, `mamba`, `virtualenv`, or bare `pip` (without `uv`) in any workflow step.
- Managed execution units (subagents) must also follow this rule.

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

## Stateless agents + branch-as-state model

All agents except Noter are treated as **stateless**. Their durable state lives only on GitHub branches in the shared `Minions-Land` repo, so that a different instance of the same agent type can pick up the work at any time by cloning the branch. Local caches are not authoritative.

### Branch ownership

- `main` — owned by **Noter**. Workflow records, stage summaries, experience assets.
- `expert/<task-id>` — owned by **Expert** of that task (scratch, hypotheses, route notes).
- `experiment/<task-id>` — owned by **Experiment** (scripts, configs, reports, execution assets).
- `paper/<task-id>` — owned by **Paper** (LaTeX project, figures, submission bundle).
- `reviewer/<task-id>/round-<n>` — owned by **Reviewer** for that round.

Additional branches may be provisioned on demand, but the rule "one agent type writes one branch" must hold.

### Noter as branch provisioner

When a new team task is set, Noter runs `provision-branches` **before** `publish-task`:

1. Ensure the shared repo exists under `https://github.com/Minions-Land/` (create if missing).
2. Create the needed branches from a clean `main` commit.
3. Seed each branch with an initial `CLAUDE.md` describing the branch.
4. Put `{repo_url, branch, claude_md_path}` into every EACN task message, so the invitee can locate its branch without external context.

### Branch-level CLAUDE.md contract

Every working branch (not `main`) must carry its own `CLAUDE.md` at the branch root, structured as:

- **Role on this branch** — which agent type owns it
- **Task context** — summary inherited from Noter's intake
- **Upstream dependencies** — other branches + commit hashes this branch relies on
- **What's been done** — reverse-chronological human-readable log (not `git log`)
- **Current state** — what is in progress, what is blocked, what is next
- **Artifacts produced** — paths with one-line descriptions
- **Handoff notes** — message to the next agent of the same type

This file is the **only** onboarding document a fresh agent needs. It must be kept truthful; update it in the same commit as the work it describes.

### Pickup / handoff protocol

Every agent, on receiving an EACN task carrying `{repo_url, branch}`, must follow the shared `sync-branch` skill (under `examples/_shared/skills/sync-branch/`):

1. **Pickup**: `git fetch` → `git checkout <branch>` → `git pull --ff-only` → read branch `CLAUDE.md` end-to-end before acting.
2. **Work**: do the role-specific work; produce artifacts on this branch only.
3. **Handoff**: update branch `CLAUDE.md` → commit → push → return `{repo_url, branch, commit}` in the EACN reply so peers can cite the exact snapshot.

Other agents reference your work by `{branch, commit}`, not by copying files across branches.

### Concurrency and safety

- One agent of a given type writes a given branch at a time; EACN bid/claim enforces exclusivity.
- Use `git push --force-with-lease` rather than `--force` if an overwrite is ever needed.
- Oversize artifacts (>500MB, checkpoints, datasets) go to LFS or an external store; commit only a pointer + metadata.
- Completed task branches are archived by tag, not deleted.

### Implication

Experiment and Reviewer agents are fully interchangeable across sessions — if the original instance is gone, any new same-type agent can resume by reading the branch `CLAUDE.md`. Expert branches follow the same mechanics, though a new Expert may bring its own scientific bias by design.

