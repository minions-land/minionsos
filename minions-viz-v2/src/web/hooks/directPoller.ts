/**
 * Browser-side EACN API poller — used when deployed to GitHub Pages (no server).
 * Mirrors the server-side poller.ts logic but runs in the browser.
 */
import type { Task, AgentCard, AgentInfo, ClusterStatus, LogEntry } from "@shared/types";

async function fetchJson<T>(endpoint: string, path: string): Promise<T | null> {
  try {
    const res = await fetch(`${endpoint}${path}`, {
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function checkHealth(endpoint: string): Promise<boolean> {
  const r = await fetchJson<{ status: string }>(endpoint, "/health");
  return r?.status === "ok";
}

export async function fetchTasks(endpoint: string): Promise<Task[]> {
  return (await fetchJson<Task[]>(endpoint, "/api/tasks?limit=200")) ?? [];
}

export async function fetchCluster(endpoint: string): Promise<ClusterStatus | null> {
  return fetchJson<ClusterStatus>(endpoint, "/api/cluster/status");
}

export async function fetchLogs(endpoint: string, limit = 100): Promise<LogEntry[]> {
  return (await fetchJson<LogEntry[]>(endpoint, `/api/admin/logs?limit=${limit}`)) ?? [];
}

export async function fetchAgents(endpoint: string, knownDomains: Set<string>): Promise<AgentCard[]> {
  const seen = new Map<string, AgentCard>();
  const domainList = knownDomains.size > 0 ? [...knownDomains] : ["coding"];
  // Fetch in parallel (max 6 concurrent)
  const batches: string[][] = [];
  for (let i = 0; i < domainList.length; i += 6) {
    batches.push(domainList.slice(i, i + 6));
  }
  for (const batch of batches) {
    const results = await Promise.all(
      batch.map((domain) =>
        fetchJson<AgentCard[]>(endpoint, `/api/discovery/agents?domain=${encodeURIComponent(domain)}&limit=200`)
      )
    );
    for (const agents of results) {
      if (agents) {
        for (const a of agents) seen.set(a.agent_id, a);
      }
    }
  }
  return [...seen.values()];
}

export async function enrichAgents(endpoint: string, cards: AgentCard[]): Promise<AgentInfo[]> {
  // Enrich in parallel batches of 10
  const results: AgentInfo[] = [];
  for (let i = 0; i < cards.length; i += 10) {
    const batch = cards.slice(i, i + 10);
    const enriched = await Promise.all(
      batch.map(async (card) => {
        const [repRes, balRes] = await Promise.all([
          fetchJson<{ score: number }>(endpoint, `/api/reputation/${encodeURIComponent(card.agent_id)}`),
          fetchJson<{ available: number; frozen: number }>(endpoint, `/api/economy/balance?agent_id=${encodeURIComponent(card.agent_id)}`),
        ]);
        return {
          ...card,
          reputation: repRes?.score ?? 0.5,
          balance: balRes ?? { available: 0, frozen: 0 },
        };
      })
    );
    results.push(...enriched);
  }
  return results;
}

export function collectDomains(tasks: Task[], cluster: ClusterStatus | null): Set<string> {
  const domains = new Set<string>();
  for (const t of tasks) {
    for (const d of t.domains) domains.add(d);
  }
  if (cluster) {
    for (const d of cluster.local.domains) domains.add(d);
    for (const m of cluster.members) {
      for (const d of m.domains) domains.add(d);
    }
  }
  return domains;
}
