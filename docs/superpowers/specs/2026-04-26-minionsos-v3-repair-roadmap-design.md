# MinionsOS_V3 Repair Roadmap Design

Date: 2026-04-26

## Purpose

MinionsOS_V3 should not be built by mechanically clearing every item in the issue checklist. It should first establish a stable, verifiable, and extensible operating skeleton, then layer research workflow, review, camera-ready, visualization, hooks, MCP, and higher-level skills on top.

The recommended priority is:

1. Phase 0: stable startup baseline.
2. Phase 1: Local EACN3 network and state contracts.
3. Phase 2: wakeup and context control.
4. Phase 3: human-side agents and role boundaries.
5. Phase 4: emergent research, submission, review, and camera-ready workflow.
6. Phase 5: visualization, hooks, MCP, Graphify/Ralph, and higher-level enhancements.

The main strategy is dual-track: fix local blockers while freezing the global contracts that prevent future rework.

## Phase 0: Stable Startup Baseline

Goal: prove that MinionsOS_V3 has a minimal stable system.

The baseline acceptance path is:

```bash
./install.sh
uv sync
./mos doctor
./gru
```

Phase 0 should only fix issues that block or obscure this path.

### Installation

- Use `uv` as the standard Python environment and dependency path.
- Keep EACN3 as the submodule/editable dependency described by the project configuration.
- Measure where EACN3 installation is slow before optimizing it.
- Prefer caching or avoiding repeated setup work over redesigning installation during this phase.

### Ports and processes

- Detect port occupancy before starting a project backend.
- If a project EACN backend port is occupied, select the next available valid port.
- Synchronize the final selected port to project metadata, Gru state, and role-visible context.
- Make port failures explicit in `./mos doctor` or startup output.

### Model registry and Claude startup

- Check that the model registry is internally consistent and that configured model names are callable.
- Decide whether `./gru` should launch Claude with:

```bash
claude --permission-mode bypassPermissions --effort max
```

- If enabled, document the safety boundary: local, trusted development and experiment environments only; not unknown repositories or shared machines by default.

### Debugging, logs, and doctor checks

- Do not enable Claude `--debug` by default.
- Enable debug only through an explicit diagnostic mode or environment variable.
- `./mos doctor` should check at least: `uv` environment, EACN3 importability, port availability, model registry consistency, Claude CLI availability, and writable runtime directories.

### Workspace hygiene

- Define the boundaries among runtime projects, workspaces, artifacts, logs, and state.
- Phase 0 does not need a large cleanup migration.
- It should prevent new runs from adding more unstructured files to the workspace.

Phase 0 is complete when a new user can run the four baseline commands and either start Gru successfully or receive a specific, actionable failure.

## Phase 1: Local EACN3 Network and State Contracts

Goal: make MinionsOS_V3 a local EACN3-based multi-agent operating system, not a loose collection of Claude processes.

### Network contract

- Each project has its own Local EACN3 backend.
- EACN-visible roles receive tasks, publish status, and hand off work through EACN3.
- Critical role coordination must not bypass EACN3 through implicit context or ad hoc file passing.
- Gru communicates with all role agents through the local EACN3 network.

### State contract

Gru state, project metadata, and EACN agent state must map to one another. The minimal shared schema should include:

- project id or port;
- agent id;
- role;
- status;
- `last_seen`;
- current task;
- blocked reason;
- wake policy;
- artifact pointers.

Persistent project identity and lifecycle state should be anchored in Gru/project metadata. Event flow and task handoff should be anchored in EACN3.

### Monitoring contract

Gru should not infer health from conversational context. The system should expose a health snapshot containing:

- backend alive/dead;
- queue depth;
- agent `last_seen`;
- pending events;
- recent failures.

Monitoring should be handled by Python-side scheduler/watcher logic or other low-cost system components. It should not depend on a long-running Claude subagent.

Phase 1 is complete when `./mos status --json` can represent project, backend, agent, queue, and recent failure state consistently with the EACN3 backend.

## Phase 2: Wakeup and Context Control

Goal: let a project continuously receive messages without frequently waking expensive model agents.

### Receiving messages is not waking a model

- EACN3 backend and Python wakeup/scheduler logic can remain low-cost and persistent.
- Claude role agents remain short-lived.
- A role is launched only when its wake policy says the event batch deserves model attention.

### Wakeup classes

The system should distinguish three wakeup classes:

1. Event-triggered: new task, direct mention, dependency unblocked, reviewer verdict, experiment completion.
2. Time-triggered: Noter summary, health check, stale pending task check.
3. Human-triggered: explicit user or Gru instruction.

### Throttling and batching

- Each role should have cadence, cooldown, batching, and deduplication rules.
- Multiple small events should be combined into a batch.
- No role should wake if there is no new information and no meaningful timeout.
- Wakeups should be explainable in logs.

### Context entry

A cold-started role should load only:

- current event batch;
- role scratchpad;
- necessary artifact pointers;
- relevant project metadata and instructions.

The system should not reload complete project history into every role context. Noter is responsible for compressing long-term state into summaries, scratchpads, and artifacts.

Phase 2 is complete when a project can remain always receptive to EACN messages while role wakeups are sparse, explainable, and controlled.

## Phase 3: Human-Side Agents and Role Boundaries

Goal: freeze the conceptual and operational boundaries of MinionsOS_V3 roles.

### Gru

Gru is a human-side agent. It primarily accepts human input for MinionsOS and drives the project workflow.

Gru responsibilities:

- receive and interpret human instructions;
- recommend workflow options;
- drive project progress;
- dispatch tasks through EACN3;
- wait, check, retry, and arbitrate;
- inspect health/status and project state.

Gru does not directly implement code, run experiments, write final paper text, or participate in Review.

### Noter

Noter is also a human-side agent. It primarily provides staged reports so humans can observe the system.

Noter responsibilities:

- periodic project summaries;
- pending task summaries;
- risk summaries;
- evidence-chain summaries;
- token/context usage reports when available;
- artifact indexes;
- concise human-facing status output.

Noter should reduce Gru context pressure rather than add work to Gru's context.

### EACN-visible role agents

Coder, Experimenter, Writer, Reviewer, Expert, Ethics, and other project roles are EACN-visible coordination nodes. They should communicate state and task handoffs through EACN3.

Complex execution can be delegated to subagents or teams, but the main role must summarize, verify, and write back results to EACN3 and relevant artifacts.

### Subagents and teams

Subagents/teams perform local execution: reading code, editing code, running experiments, checking papers, or analyzing artifacts. They are not long-term EACN-visible project state sources.

### Ethics

Ethics is the project's validation-set-like agent. It continuously checks whether agent behavior, communication, theory, code, and claims have real evidence support.

Ethics may inspect internal materials, including:

- experiment artifacts;
- evidence/claim maps;
- appendix and supplementary plans;
- known limitations;
- unresolved risks;
- agent communication;
- theoretical, code, experiment, and writing claims.

Ethics exists to reduce hallucination, unsupported reasoning, and evidence drift throughout the project.

### Reviewer

Reviewer is the project's test-set-like agent. It is invoked only when the project has produced a staged submission resembling a real submission.

Reviewer should simulate real reviewers and should only see what real reviewers see:

- paper PDF;
- submitted/open-source-ready repository code.

Reviewer should not see internal experiment artifacts, evidence/claim maps, Ethics reports, Noter reports, internal discussions, known limitations files, or unresolved risk lists unless those are visible in the submitted PDF or repository.

Each review round should produce at least three independent reviewer opinions. Gru does not participate in Review.

Phase 3 is complete when role prompts, tool whitelists, lifecycle code, and tests all express these same boundaries.

## Phase 4: Emergent Research, Submission, Review, and Camera-Ready

Goal: support research emergence while enforcing common-sense gates around submission, review, and final handoff.

MinionsOS_V3 should not impose a fixed global linear workflow on every project. Research can move forward, backward, or sideways across phases. The system should provide workflow suggestions, not a rigid project phase machine.

The system should still enforce key constraints:

- paper review starts only after the paper is complete enough and relevant experts have cross-checked it;
- Reviewer sees only the PDF and submitted/open-source-ready code;
- `Accept` or `Strong Accept` is required before final Camera-Ready;
- `Borderline`, `Weak Accept`, or `Reject` sends the project back to revision;
- Camera-Ready produces the final human-facing package and ends the project.

### External submission surface

For review and final human handoff, the external surface is only:

1. final or staged paper PDF;
2. corresponding `LaTeX.zip` when handing the final result to the human;
3. repository-level project code that can be directly `git push`ed and open-sourced.

Internal artifacts are not part of the Reviewer-visible submission surface unless they are included in the PDF or repository.

### Reviewer workflow

Reviewer is invoked when there is a staged submission package for realistic review. It should inspect only the paper PDF and submitted/open-source-ready repository code.

Reviewer checks should include:

- scientific contribution;
- presentation;
- claim strength;
- missing baselines;
- citation risk as visible in the paper;
- hallucination risk as visible in the paper/code;
- code reproducibility as visible from the submitted code.

Reviewer verdicts route the project:

- `Accept` or `Strong Accept`: eligible for Camera-Ready.
- `Borderline`, `Weak Accept`, or `Reject`: return to revision.

### Ethics workflow

Ethics runs throughout the project and may inspect internal materials. Ethics is responsible for evidence support, not external review simulation.

Ethics should maintain or emit evidence-focused summaries such as:

- unsupported claims;
- speculative claims;
- claims derived from specific experiments or artifacts;
- mismatches between paper, code, experiments, and agent communications;
- high-risk hallucination areas.

### Writer and claim discipline

Writer should not invent claims. Writer output should be based on available evidence, expert feedback, experiment results, and competitor positioning.

Required writing constraints include:

- Abstract is one paragraph.
- Conclusion is one paragraph.
- Core claims should be calibrated: no overclaim, no underclaim, and no excessive limitation.
- Claims should be supported by evidence, experiment, derivation, citation, or explicit speculation markers.

### Camera-Ready

Camera-Ready starts only after `Accept` or `Strong Accept`.

Camera-Ready work includes:

- use GPT-image-2.0 to generate a main/model-overview figure;
- place the figure into the revised paper;
- control main-body page count;
- move remaining material to appendix;
- check citations, references, labels, PDF question marks, and hallucinated bibliography entries;
- produce final PDF;
- produce corresponding `LaTeX.zip`;
- prepare repository-level project code that can be directly `git push`ed and open-sourced;
- hand the final package to the human;
- end the project.

Phase 4 is complete when the system can suggest and execute these gates without forcing every research project into a single rigid pipeline.

## Phase 5: Visualization, Hooks, MCP, and Higher-Level Enhancements

Goal: improve observability, automation, and research augmentation after the core operating model is stable.

### Visualization

Project-level visualization should show:

- project state;
- agent state;
- EACN queue status;
- pending tasks;
- recent events;
- artifacts;
- Ethics risk summaries;
- Reviewer verdicts.

Viz must remain read-only. It must not drain role queues, modify EACN3, or become a hidden workflow controller.

### Hooks

Hooks can help with:

- state synchronization;
- logging;
- permission checks;
- post-run summaries;
- lightweight notifications.

Hooks should not silently change project workflow. Workflow decisions should remain explicit in Gru/EACN communication.

### MCP and tool failure handling

EACN operations should go through EACN MCP/tools rather than ad hoc HTTP calls.

Tool failures should be:

- classified;
- retried when safe;
- summarized;
- recorded as artifacts or logs;
- reported back to the scheduling/coordination agent through EACN3 when relevant.

### Graphify, Ralph, and higher-level skills

Graphify/Ralph and high-level reasoning skills can enhance:

- issue clustering;
- claim/evidence graphs;
- paper structure graphs;
- research knowledge maps;
- philosophical reasoning templates;
- table and plot template libraries.

They should not be in the Phase 0 startup-critical path.

## Recommended Repair Order

1. Stabilize startup and diagnostics around `./install.sh && uv sync && ./mos doctor && ./gru`.
2. Fix port/process/model/debug/workspace issues that block the startup baseline.
3. Define and implement the EACN3 network contract.
4. Define and implement the shared state contract across Gru, project metadata, and EACN agent state.
5. Add explicit health snapshots to `./mos status --json`.
6. Separate message receipt from model wakeup.
7. Add event/time/human wakeup policies with batching, cooldown, and deduplication.
8. Freeze Gru and Noter as human-side agents with distinct input and observation responsibilities.
9. Freeze role/subagent execution boundaries and enforce them in prompts, whitelists, and tests.
10. Implement Ethics as continuous validation-set-like evidence auditing.
11. Implement Reviewer as staged test-set-like external review over PDF and submitted code only.
12. Add emergent research workflow suggestions and common-sense gates without forcing a rigid global pipeline.
13. Implement Camera-Ready finalization and human handoff.
14. Add visualization, hooks, MCP fallback, Graphify/Ralph, and higher-level research/writing enhancements.

## Out of Scope for the First Implementation Plan

The first implementation plan should not attempt all phases at once. It should start with Phase 0 and the minimum Phase 1 contracts needed to avoid rework.

Specifically defer:

- full Reviewer workflow;
- full Camera-Ready automation;
- GPT-image-2.0 integration;
- full dashboard redesign;
- Graphify/Ralph integration;
- philosophical skill packs;
- table and plotting template libraries.

These become later implementation plans after the startup baseline and core EACN/Gru/role contracts are stable.
