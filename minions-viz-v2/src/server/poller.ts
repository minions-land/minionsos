/**
 * EACN3 per-project poller — fetches read-only data from a project's local
 * EACN3 backend at http://127.0.0.1:{port}. All functions take the endpoint
 * explicitly so the scheduler can switch projects at runtime.
 */
import type { Task, AgentCard, AgentInfo, ClusterStatus, LogEntry, Message } from "../shared/types.js";

async function fetchJson<T>(endpoint: string, p: string): Promise<T | null> {
  try {
    const res = await fetch(`${endpoint}${p}`, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch { return null; }
}

export function endpointForPort(port: number): string {
  return `http://127.0.0.1:${port}`;
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
  for (const domain of domainList) {
    const agents = await fetchJson<AgentCard[]>(
      endpoint, `/api/discovery/agents?domain=${encodeURIComponent(domain)}&limit=200`,
    );
    if (agents) for (const a of agents) seen.set(a.agent_id, a);
  }
  return [...seen.values()];
}

export async function fetchReputation(endpoint: string, agentId: string): Promise<number> {
  const r = await fetchJson<{ score: number }>(endpoint, `/api/reputation/${encodeURIComponent(agentId)}`);
  return r?.score ?? 0.5;
}

export async function fetchBalance(endpoint: string, agentId: string): Promise<{ available: number; frozen: number }> {
  const r = await fetchJson<{ available: number; frozen: number }>(
    endpoint, `/api/economy/balance?agent_id=${encodeURIComponent(agentId)}`,
  );
  return r ?? { available: 0, frozen: 0 };
}

export async function enrichAgents(endpoint: string, cards: AgentCard[]): Promise<AgentInfo[]> {
  const out: AgentInfo[] = [];
  for (const card of cards) {
    const [reputation, balance] = await Promise.all([
      fetchReputation(endpoint, card.agent_id),
      fetchBalance(endpoint, card.agent_id),
    ]);
    out.push({ ...card, reputation, balance });
  }
  return out;
}

export function collectDomains(tasks: Task[], cluster: ClusterStatus | null): Set<string> {
  const domains = new Set<string>();
  for (const t of tasks) for (const d of t.domains) domains.add(d);
  if (cluster) {
    for (const d of cluster.local.domains) domains.add(d);
    for (const m of cluster.members) for (const d of m.domains) domains.add(d);
  }
  return domains;
}

export async function fetchMessages(endpoint: string, limit = 500): Promise<Message[]> {
  const logs = await fetchLogs(endpoint, limit);
  const messages: Message[] = [];
  for (const log of logs) {
    if (log.fn_name === "relay_message" && log.agent_id && log.args.to_agent_id) {
      messages.push({
        id: `${log.timestamp}-${log.agent_id}`,
        from_agent_id: log.agent_id,
        to_agent_id: String(log.args.to_agent_id),
        task_id: log.task_id,
        content: log.args.content,
        timestamp: log.timestamp,
      });
    }
  }
  return messages;
}
