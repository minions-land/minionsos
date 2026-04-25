/**
 * In-memory state: per-(gruId,port) EACN3 snapshots + per-client selection + broadcast.
 */
import type { WebSocket } from "ws";
import type {
  NetworkSnapshot, Task, AgentInfo, ClusterStatus, LogEntry, WsMessage, GruInfo,
} from "../shared/types.js";

interface ProjectSnapshot {
  tasks: Task[];
  agents: AgentInfo[];
  cluster: ClusterStatus | null;
  logs: LogEntry[];
  connected: boolean;
  lastUpdate: number;
}

interface Selection { gruId: string | null; port: number | null }

function key(gruId: string, port: number): string { return `${gruId}::${port}`; }

const clients = new Set<WebSocket>();
const clientSelection = new WeakMap<WebSocket, Selection>();
const perPair = new Map<string, ProjectSnapshot>();
let grus: GruInfo[] = [];

function blank(): ProjectSnapshot {
  return { tasks: [], agents: [], cluster: null, logs: [], connected: false, lastUpdate: 0 };
}

export function ensurePair(gruId: string, port: number): ProjectSnapshot {
  const k = key(gruId, port);
  let s = perPair.get(k);
  if (!s) { s = blank(); perPair.set(k, s); }
  return s;
}

export function snapshotFor(sel: Selection): NetworkSnapshot {
  const s = sel.gruId && sel.port != null ? ensurePair(sel.gruId, sel.port) : blank();
  return {
    ...s,
    eacnEndpoint: sel.port != null ? `http://127.0.0.1:${sel.port}` : "",
    selectedPort: sel.port,
    selectedGruId: sel.gruId,
    grus,
  };
}

export function getSelection(ws: WebSocket): Selection {
  return clientSelection.get(ws) ?? { gruId: null, port: null };
}

export function setSelection(ws: WebSocket, sel: Selection) {
  clientSelection.set(ws, sel);
  send(ws, { type: "selected", data: sel });
  send(ws, { type: "snapshot", data: snapshotFor(sel) });
}

export function addClient(ws: WebSocket) {
  clients.add(ws);
  const sel: Selection = { gruId: null, port: null };
  clientSelection.set(ws, sel);
  send(ws, { type: "snapshot", data: snapshotFor(sel) });
  send(ws, { type: "grus:update", data: grus });
}

export function removeClient(ws: WebSocket) { clients.delete(ws); }

function send(ws: WebSocket, msg: WsMessage) {
  try { ws.send(JSON.stringify(msg)); } catch {}
}

function broadcastPair(gruId: string, port: number, msg: WsMessage) {
  if (clients.size === 0) return;
  const raw = JSON.stringify(msg);
  for (const ws of clients) {
    const sel = getSelection(ws);
    if (sel.gruId === gruId && sel.port === port) {
      try { ws.send(raw); } catch {}
    }
  }
}

function broadcastAll(msg: WsMessage) {
  if (clients.size === 0) return;
  const raw = JSON.stringify(msg);
  for (const ws of clients) { try { ws.send(raw); } catch {} }
}

export function setGrus(next: GruInfo[]) {
  grus = next;
  broadcastAll({ type: "grus:update", data: next });
}

export function setConnected(gruId: string, port: number, connected: boolean) {
  const s = ensurePair(gruId, port);
  if (s.connected === connected) return;
  s.connected = connected;
  broadcastPair(gruId, port, { type: "connection:status", data: { connected } });
}

export function updateTasks(gruId: string, port: number, tasks: Task[]) {
  const s = ensurePair(gruId, port);
  s.tasks = tasks; s.lastUpdate = Date.now();
  broadcastPair(gruId, port, { type: "tasks:update", data: tasks });
}

export function updateAgents(gruId: string, port: number, agents: AgentInfo[]) {
  const s = ensurePair(gruId, port);
  s.agents = agents; s.lastUpdate = Date.now();
  broadcastPair(gruId, port, { type: "agents:update", data: agents });
}

export function updateCluster(gruId: string, port: number, cluster: ClusterStatus | null) {
  const s = ensurePair(gruId, port);
  s.cluster = cluster; s.lastUpdate = Date.now();
  broadcastPair(gruId, port, { type: "cluster:update", data: cluster });
}

export function updateLogs(gruId: string, port: number, logs: LogEntry[]) {
  const s = ensurePair(gruId, port);
  s.logs = logs; s.lastUpdate = Date.now();
  broadcastPair(gruId, port, { type: "logs:update", data: logs });
}

export function allClients(): Set<WebSocket> { return clients; }

/** Return active (gruId, port) pairs currently being watched by ≥1 client. */
export function activePairs(): Array<{ gruId: string; port: number }> {
  const set = new Map<string, { gruId: string; port: number }>();
  for (const ws of clients) {
    const sel = getSelection(ws);
    if (sel.gruId && sel.port != null) {
      set.set(key(sel.gruId, sel.port), { gruId: sel.gruId, port: sel.port });
    }
  }
  return Array.from(set.values());
}
