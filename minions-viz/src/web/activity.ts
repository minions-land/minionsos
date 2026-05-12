import { useMemo } from "react";
import type { AgentInfo, MosProject, Task, Message } from "@shared/types";
import { roleBucket } from "./roleIdentity";

export interface AgentActivity {
  state: "active" | "idle";
  pending: number;
  executing: number;
  busyOn: string | null; // task id, if awaiting_retrieval and this agent is executing
}

/**
 * Shared computation for per-agent activity, independent of which view
 * renders it. Rules:
 *
 *   - Default state = idle (agents are event-driven; no forced "sleeping").
 *   - Active iff any of:
 *       • has an accepted/executing bid on an in-progress task;
 *       • has a submitted result on an in-progress task;
 *       • has sent/received a message within the last 30s;
 *       • has a pending bid on a bidding task.
 *   - Pending count = tasks waiting on this agent's attention:
 *       • unclaimed tasks initiated by the agent (waiting for handoff);
 *       • bidding tasks this agent is invited/bidding on;
 *       • awaiting_retrieval tasks this agent is executing.
 *
 * If project.active_roles explicitly marks a role "dismissed", all instances
 * of that bucket are forced idle.
 */
export function computeActivity(
  agents: AgentInfo[],
  tasks: Task[],
  messages: Message[],
  project: MosProject | null,
  nowMs: number = Date.now(),
): Map<string, AgentActivity> {
  const m = new Map<string, AgentActivity>();
  for (const a of agents) {
    m.set(a.agent_id, { state: "idle", pending: 0, executing: 0, busyOn: null });
  }

  for (const t of tasks) {
    if (t.status === "completed" || t.status === "no_one_able") continue;

    if (t.status === "unclaimed") {
      const init = m.get(t.initiator_id);
      if (init) init.pending += 1;
    }

    if (t.status === "bidding") {
      for (const b of t.bids ?? []) {
        const x = m.get(b.agent_id);
        if (x) {
          x.state = "active";
          x.pending += 1;
        }
      }
      for (const id of t.invited_agent_ids ?? []) {
        const x = m.get(id);
        if (x && !x.pending) x.pending += 1;
      }
    }

    if (t.status === "awaiting_retrieval") {
      const executors = new Set<string>();
      for (const b of t.bids ?? [])
        if (b.status === "executing" || b.status === "accepted")
          executors.add(b.agent_id);
      for (const r of t.results ?? []) executors.add(r.agent_id);
      for (const id of executors) {
        const x = m.get(id);
        if (x) {
          x.state = "active";
          x.executing += 1;
          x.pending += 1;
          if (!x.busyOn) x.busyOn = t.id;
        }
      }
    }
  }

  for (const msg of messages) {
    let ts = 0;
    try {
      ts = Date.parse(msg.timestamp);
    } catch {}
    if (!Number.isFinite(ts) || nowMs - ts > 30_000) continue;
    const from = m.get(msg.from_agent_id);
    if (from) from.state = "active";
    const to = m.get(msg.to_agent_id);
    if (to) {
      to.state = "active";
      to.pending += 1;
    }
  }

  const dismissedBuckets = new Set<string>();
  for (const r of project?.active_roles ?? []) {
    if (r.state === "dismissed") dismissedBuckets.add(r.name);
  }
  if (dismissedBuckets.size > 0) {
    for (const a of agents) {
      if (dismissedBuckets.has(roleBucket(a.agent_id).key)) {
        const cur = m.get(a.agent_id);
        if (cur) {
          cur.state = "idle";
        }
      }
    }
  }

  return m;
}

export function useAgentActivity(
  agents: AgentInfo[],
  tasks: Task[],
  messages: Message[],
  project: MosProject | null,
): Map<string, AgentActivity> {
  return useMemo(
    () => computeActivity(agents, tasks, messages, project),
    [agents, tasks, messages, project],
  );
}
