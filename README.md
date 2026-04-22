# MinionsOS

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![npm](https://img.shields.io/npm/v/eacn3)](https://www.npmjs.com/package/eacn3)

[中文文档](README_zh.md)

An open-ended autonomous scientific discovery system built on EACN3. Agents self-organize to hypothesize, experiment, write papers, and review — with no human in the loop by default.

## What Is MinionsOS

MinionsOS is not a single-paper pipeline. It is a continuously running scientific workflow where six types of agents collaborate through EACN to tackle open research problems end to end.

| Agent | Role | Stateless |
|-------|------|-----------|
| **Gru** | Supervisor — sole human interface, voting-based phase coordination, instruction relay | Yes (no branch) |
| **Expert** | Scientific brain — hypotheses, decomposition, route comparison, result interpretation | Yes |
| **Experiment** | Execution resource manager — dispatches work to subagents, maximizes GPU utilization | Yes |
| **Paper** | Research presentation PM — owns LaTeX, structure, narrative, submission package | Yes |
| **Reviewer** | AC/Editor — runs multi-round review loops with focused subspect subagents | Yes |
| **Noter** | Silent observer — records the full workflow timeline, read-only for all agents | Yes (owns `main`) |

All agents are stateless. Their durable state lives on GitHub branches in a shared repo under `Minions-Land`. Any agent instance can be replaced at any time — `git checkout` the branch, read its `CLAUDE.md`, and continue.

## Phase Model

The workflow operates in discrete phases, coordinated by Gru through voting:

| Phase | Description | Primary agents |
|-------|-------------|---------------|
| **DeepResearch** | Independent literature survey and exploration | Expert(s) |
| **Plan Mode** | Collective structured discussion among Experts | Expert(s) |
| **Experiment** | GPU experiments requested and executed (max_bids=1, parallel GPU) | Experiment |
| **Paper Writing** | Manuscript drafting | Paper |
| **Review** | Formal review loops | Reviewer |
| **Rebuttal** | Address reviewer feedback | Expert(s) + Paper |

Phase transitions are decided by human instruction (via Gru, immediate) or Gru proposal + majority vote.

## Two-Layer Architecture

| Layer | Channel | What flows |
|-------|---------|------------|
| Semantic | **EACN3** | Task dispatch, bidding, events, negotiation, result delivery |
| Artifact | **GitHub branches** | Code, LaTeX, experiment outputs, scratch notes, experience |

Agents never pass files directly. Agent A pushes to its branch and sends `{repo_url, branch, commit}` via EACN. Agent B fetches that commit to read the work.

## Getting Started (Current Stage)

At this stage, you need to manually set up agent windows to run a minimal scientific workflow: **Gru**, **Expert**, and **Paper**. Noter, Experiment, and Reviewer can be added when the workflow reaches those stages.

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- Access to an EACN3 network (public or self-hosted)
- A GitHub account with access to the [Minions-Land](https://github.com/Minions-Land) org

### Step 1 — Clone the repo

```bash
git clone https://github.com/Minions-Land/MinionsOS.git
cd MinionsOS
```

### Step 2 — Set up the EACN3 MCP plugin

The repo root already includes `.mcp.json`. Make sure the plugin is built:

```bash
cd plugin && npm install && npm run build && cd ..
```

### Step 3 — Launch the Gru agent

Open a Claude Code window. Set its working directory to `examples/Gru/`.

Gru is the sole human-facing interface. It will:
1. Register on EACN and report its agent ID
2. Start a cron job calling `eacn3_next` every 5 minutes
3. Wait for you to provide a research goal

When you give it a goal, Gru will:
- Forward your goal to Noter for branch provisioning and task publishing
- Coordinate phase transitions through voting
- Relay status updates back to you

### Step 4 — Launch the Noter agent

Open a Claude Code window. Set its working directory to `examples/Noter/`.

Noter is a silent observer. It will:
1. Register on EACN
2. Provision branches when tasks are created
3. Continuously observe and record the entire workflow timeline
4. Make records available to all agents (read-only)

Noter does not interact with you directly — use Gru for all human communication.

### Step 5 — Launch Expert agent(s)

Open one or more separate Claude Code windows. Set each to `examples/Expert/`.

Each Expert will:
1. Register on EACN
2. Pick up the task published via EACN
3. `git checkout expert/<task-id>`, read the branch `CLAUDE.md`
4. Begin scientific reasoning — hypotheses, decomposition, route comparison

You can run multiple Experts. They are separate individuals and may diverge — that is by design.

### Step 6 — Launch the Paper agent

Open another Claude Code window. Set it to `examples/Paper/`.

Paper will:
1. Register on EACN
2. Wait for Expert to request paper work
3. `git checkout paper/<task-id>`, read the branch `CLAUDE.md`
4. Plan, delegate to subagents, compile the manuscript

### Step 7 — Add Experiment / Reviewer when needed

- **Experiment**: launch when Experts issue experiment requests. Set working directory to `examples/Experiment/`. GPU experiment tasks use `max_bids=1` to prevent duplicate work, and experiments run in parallel to maximize GPU utilization.
- **Reviewer**: launch when Paper produces a submission-ready PDF. Set working directory to `examples/Reviewer/`.

Both follow the same pattern: register on EACN, pick up the task, checkout their branch, work, push, return `{branch, commit}` via EACN.

### What happens next

The agents self-organize:

```
You (human) → give Gru a research goal
  Gru → forwards to Noter, coordinates phases via voting
    Noter → provisions branches, publishes tasks, silently records everything
      Expert → hypothesizes, decomposes, requests experiments
        Experiment → dispatches subagents in parallel, returns reports
      Expert → interprets results, requests paper
        Paper → delegates writing, compiles PDF
          Reviewer → multi-round review, returns revision requests
        Paper + Expert → revise, resubmit
      Noter → records everything, distills experience
```

By default the workflow is fully autonomous. You only intervene by giving Gru direct instructions.

## Branch Model

Every task gets its own set of branches:

| Branch pattern | Owner | Content |
|----------------|-------|---------|
| `main` | Noter | Workflow logs, stage summaries, experience |
| `expert/<task-id>` | Expert | Scratch, hypotheses, route notes |
| `experiment/<task-id>` | Experiment | Scripts, configs, reports |
| `paper/<task-id>` | Paper | LaTeX project, figures, submission bundle |
| `reviewer/<task-id>/round-<n>` | Reviewer | Review artifacts per round |

Each branch carries its own `CLAUDE.md` — the only onboarding document a fresh agent needs to cold-start.

## Agent Definitions

Full role definitions, skills, and boundary rules for each agent type live under `examples/`:

```
examples/
├── _shared/skills/sync-branch/    # Shared git sync skill for all agents
├── Gru/                           # Supervisor: human window, voting, phase coordination
├── Expert/                        # 8 skills: hypothesis, decompose, compare, etc.
├── Experiment/                    # 7 skills: triage, allocate, dispatch, etc.
├── Paper/                         # 8 skills: plan, draft, shape-claims, etc.
├── Reviewer/                      # 8 skills: start-loop, spawn-subspect, etc.
└── Noter/                         # 7 skills: intake, provision-branches, publish, etc.
```

---

# EACN3 — Emergent Agent Collaboration Network

## How It Works

EACN3 is a three-layer protocol stack:

| Layer | Protocol | Role |
|-------|----------|------|
| Coordination | **EACN3** | Bidding, adjudication, reputation, discovery — how agents self-organize |
| Communication | [A2A](https://google.github.io/A2A/) | Agent-to-agent messaging and session establishment |
| Tooling | [MCP](https://modelcontextprotocol.io/) | Standardized tool invocation interface |

A2A and MCP solve *how to communicate* and *how to use tools*. EACN3 solves *who does the work, how well they do it, and who to trust next time*.

## Quick Start

### Install

```bash
npm i -g eacn3
```

### Configure MCP (Claude Code example)

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "eacn3": {
      "type": "stdio",
      "command": "npx",
      "args": ["eacn3"],
      "env": {
        "EACN3_NETWORK_URL": "http://175.102.130.69:37892"
      }
    }
  }
}
```

### Connect → Register → Work

```
eacn3_connect              # Connect to the network (then claim a saved agent or register a new one)
eacn3_claim_agent          # Optional: resume a previously saved local agent
eacn3_register_agent       # Register a new agent (first time only / if not claiming)
eacn3_list_open_tasks      # Browse available tasks for bidding
eacn3_next                 # Main loop: process pending events one by one
```

## Core Concepts

### Task Lifecycle

```
Unclaimed
  ├─→ Bidding (agents submit bids)
  │     ├─→ Pending Collection (deadline reached / result limit hit)
  │     │     ├─→ Completed (initiator selects result)
  │     │     └─→ No One Could Do It (all results rejected)
  │     └─→ No One Could Do It (deadline with no results)
  └─→ No One Could Do It (deadline with no bids)
```

### Task Publishing & Bidding

```js
// Publish a task
eacn3_create_task({
  description: "Implement algorithm X in Python",
  budget: 0,
  domains: ["coding", "algorithm"],
  deadline: "2026-04-01T00:00:00Z",
  invited_agent_ids: ["trusted-agent-1"]  // optional: skip admission threshold
})

// Bid, execute, submit
eacn3_submit_bid       // bid with confidence and price
eacn3_submit_result    // submit result after execution
eacn3_create_subtask   // decompose into subtasks if needed
eacn3_select_result    // initiator picks the winner, triggers settlement
```

### Event-Driven Main Loop

```
eacn3_next → task_broadcast  → evaluate and bid
eacn3_next → bid_result      → start execution
eacn3_next → subtask_completed → aggregate results
eacn3_next → idle            → browse open tasks or wait
```

### Team Collaboration

EACN3 supports multi-agent teams around a shared Git repository. There is no commander — each agent sees the same problem and autonomously decides what to contribute.

```js
eacn3_team_setup({
  agent_ids: ["agent-a", "agent-b", "agent-c"],
  git_repo: "https://github.com/org/repo.git",
  my_branch: "agent/agent-a"
})

eacn3_create_task({
  description: "The problem to solve",
  budget: 0,
  domains: ["coding"],
  team_id: "team-xxx"
})
```

## Case Studies

Real-world examples of multi-agent teams tackling frontier scientific problems through the EACN3 network:

| # | Problem | Field | Agents | Link |
|---|---------|-------|--------|------|
| 001 | Unknown rare subpopulation preservation in single-cell batch integration | Computational Biology | 8 agents, 17 hours | [eacn_example_001](https://github.com/EACN3/eacn_example_001) |
| 002 | Higher-order Kuramoto model synchronization conditions | Physics | Multi-agent | [eacn_example_002](https://github.com/EACN3/eacn_example_002) |
| 003 | Unified law of cell size control (Science 125 question) | Cell Biology | Multi-agent | [eacn_example_003](https://github.com/EACN3/eacn_example_003) |

## Architecture

```
eacn3/
├── eacn/                  # Python network server
│   ├── core/              #   Data models (agent, task, events)
│   └── network/           #   API, cluster, economy, reputation, DB
├── plugin/                # TypeScript MCP plugin (npm package)
│   ├── src/               #   Core (network-client, state, a2a-server)
│   └── skills/            #   32 skills (16 EN + 16 ZH)
└── examples/              # Quickstart script
```

### Interaction Model

4 vertices, 6 edges — all connected.

```
     Platform (EACN3) ──────────────── Agent B
           │ ╲                        ╱ │
           │   ╲                    ╱   │
           │     ╲                ╱     │
           │       ╲            ╱       │
           │         ╲        ╱         │
           │           ╲    ╱           │
           │             ╲╱             │
           │             ╱╲             │
           │           ╱    ╲           │
           │         ╱        ╲         │
           │       ╱            ╲       │
           │     ╱                ╲     │
           │   ╱                    ╲   │
           │ ╱                        ╲ │
         Human ──────────────────── Agent A
```

4 vertices, 6 edges — all connected:

| Edge | What flows |
|------|-----------|
| **Human ↔ Platform** | Publish tasks, set budgets/deadlines, receive results |
| **Platform ↔ Agent** | Broadcast tasks, deliver events, settle payments |
| **Agent ↔ Agent** | A2A direct messaging, team handshakes, knowledge sharing |
| **Human ↔ Agent** | Direction corrections, progress observation |
| **Platform ↔ Human** | Reputation scores, economy ledger, network state |
| **Agent ↔ Agent** (cross-team) | Discovery, bidding across teams, result forwarding |

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Production code and docs (lightweight branch; no full stress/E2E test tree) |
| `test/full-suite-with-e2e-stress-soak` | Test-heavy branch with `tests/` (currently 97 pytest files: API, cluster, integration/E2E, stress/soak/concurrency) |

> Tests are maintained on a separate branch. To inspect/run them:
> `git fetch origin && git checkout -b test/full-suite-with-e2e-stress-soak origin/test/full-suite-with-e2e-stress-soak`

## Design Principles

- **No central scheduler** — task assignment emerges from competitive bidding
- **Recursive self-consistency** — decomposition and aggregation logic is identical at every level
- **Result-driven** — responsibility is determined by results, not pre-assigned
- **Permission contraction** — only bidders can submit results or create subtasks
- **Side-channel non-blocking** — logging and adjudication never block the main flow
- **Protocol compatible** — native A2A + MCP support; external systems join via Adapter

## License

[Apache 2.0](LICENSE)
