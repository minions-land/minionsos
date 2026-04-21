# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This repository contains two coupled pieces:

- `eacn/`: the Python EACN3 network backend. It exposes a FastAPI API, persists state in SQLite, and owns task lifecycle, discovery, reputation, settlement, and cluster forwarding.
- `plugin/`: the TypeScript MCP plugin published as `eacn3`. It is the client-side integration used by Claude Code and other MCP hosts to connect agents to the network.

Most feature work crosses both halves: backend API/state changes in `eacn/` and corresponding MCP/tool or state-handling changes in `plugin/`.

## Common commands

### Python backend

- Create venv and install editable package:
  - `python -m venv .venv`
  - `source .venv/bin/activate`
  - `pip install -e .`
- Run the network API locally:
  - `EACN3_DB_PATH=data/eacn3.db uvicorn eacn.network.api.app:create_app --host 0.0.0.0 --port 8000`
- Health check:
  - `curl http://127.0.0.1:8000/health`

### TypeScript MCP plugin

- Install dependencies:
  - `cd plugin && npm install`
- Build once:
  - `cd plugin && npm run build`
- Watch mode during development:
  - `cd plugin && npm run dev`
- Run built plugin directly:
  - `cd plugin && node dist/server.js`

### Local integration

The repo root already includes `.mcp.json` for wiring Claude Code to the plugin. After editing plugin code, rebuild with `cd plugin && npm run build`; if the MCP server is already running in an existing Claude Code session, restart the session so the updated build is loaded.

### Tests

The default `main` branch is intentionally light and does not include the full test tree. The README documents a dedicated branch for tests:

- Fetch and switch to the test branch:
  - `git fetch origin`
  - `git checkout -b test/full-suite-with-e2e-stress-soak origin/test/full-suite-with-e2e-stress-soak`
- Run all tests from that branch:
  - `pytest`
- Run a single test file from that branch:
  - `pytest tests/path/to/test_file.py`
- Run a single test case from that branch:
  - `pytest tests/path/to/test_file.py::test_name`

## Architecture

### Backend flow

The backend entrypoint is `eacn/network/api/app.py`. `create_app()` builds the FastAPI app and the lifespan hook initializes the SQLite `Database`, then creates a `Network` instance from `eacn/network/app.py`.

`Network` is the orchestration layer. It wires together:

- `DiscoveryService` for discovery/bootstrap/DHT/gossip
- `TaskManager` for in-memory task state plus DB reload
- `PushService` for event delivery
- `GlobalMatcher` for bid admission
- `GlobalReputation` for scores and propagation
- `EscrowService` and `SettlementService` for budget freezing, subtask allocation, refunds, and payouts
- `ClusterService` for cross-node forwarding and status propagation

The HTTP routes in `eacn/network/api/routes.py` are intentionally thin wrappers around `Network`. If behavior changes in task lifecycle, escrow, timeout handling, subtask rules, or cross-node forwarding, the real logic is usually in `eacn/network/app.py` and `eacn/network/task_manager.py`, not in the route layer.

A key design point: push delivery is queue-based, not websocket-based, on the backend. During app startup, every outgoing event is written into the per-agent offline queue (`OfflineStore`), and agents later fetch from `/api/events/{agent_id}`. Cluster forwarding re-enqueues remotely for local delivery.

### Task lifecycle model

The core product concept is a marketplace-style task lifecycle:

1. initiator creates a task and escrow freezes budget
2. discovery finds candidate agents by domain
3. the task is broadcast to matching agents
4. agents submit bids, possibly entering pending confirmation if price exceeds budget
5. accepted bidders execute directly or create subtasks
6. results are submitted and may trigger adjudication subtasks
7. initiator collects/selects a result, which triggers settlement and reputation propagation

Important implementation detail: many guardrails in `eacn/network/app.py` are about parent/child task termination and escrow rollback. When changing task completion, selection, or subtask behavior, check the child-task cascade and settlement ordering carefully.

### Cluster model

The backend can run as a standalone node or as a clustered node. Routes first check whether a task is local; if not, they forward bids/results/rejections through the cluster router. That means API behavior may be split between local execution and cross-node forwarding, especially in `routes.py` and `cluster/`.

### Plugin flow

The plugin is a stateful MCP server compiled from `plugin/src/`.

Important modules:

- `network-client.ts`: typed wrapper over the backend HTTP API; this is where retries, timeouts, health probes, and server-id header injection live
- `state.ts`: persistent local state under `~/.eacn3/`, split into shared server state, per-agent state files, and per-agent event files
- `event-transport.ts`: on-demand event fetcher. There is no background polling; events are fetched only when tools like `eacn3_next`, `eacn3_get_events`, or `eacn3_await_events` ask for them
- `reverse-control.ts`: optional proactive behavior layer that can use MCP sampling/notifications to react to network events
- `a2a-server.ts`: small HTTP server for direct agent-to-agent messages

The plugin is not just a thin API proxy. It owns local persistence, agent claiming, event buffering, message sessions, team metadata, and some decision automation. If a bug involves duplicated events, missing state after restart, multiple agents, or Claude-side behavior, inspect plugin state/event handling before assuming the backend is wrong.

### MCP usage rule

`plugin/AGENT_GUIDE.md` is explicit: EACN3 operations should go through `eacn3_*` MCP tools rather than handcrafted direct HTTP calls. Keep that contract intact when adding or changing capabilities.

## Repo structure cues

- `eacn/core/models/`: shared domain models such as tasks, agents, log entries, and push events
- `eacn/network/api/`: FastAPI app and schemas
- `eacn/network/cluster/`: peer membership, routing, forwarding, gossip/bootstrap internals
- `eacn/network/economy/`: escrow and settlement logic
- `plugin/src/`: MCP server implementation and persistent client/runtime behavior
- `examples/quickstart.py`: a minimal conceptual example, but it is not the main development path

## Development notes

- Python requires 3.11+.
- Node requires 16+ according to `plugin/package.json`.
- The repo root `.mcp.json` points Claude Code at the plugin; backend URL is provided through `EACN3_NETWORK_URL`.
- `LOCAL_DEV_SETUP.md` is the authoritative local dev setup doc for running backend + plugin together.
- There are no lint commands configured in the checked-in `main` branch, so do not invent one in automation or docs without adding the tool first.
