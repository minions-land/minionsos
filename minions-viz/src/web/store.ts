import { useEffect, useRef, useSyncExternalStore } from "react";
import type {
  NetworkSnapshot,
  WsMessage,
  GruInfo,
  MosProject,
} from "@shared/types";

interface Selection {
  gruId: string | null;
  port: number | null;
}

const STORAGE_KEY = "mos.viz.selection";

function loadSelection(): Selection {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (!v) return { gruId: null, port: null };
    const parsed = JSON.parse(v) as Selection;
    return {
      gruId: typeof parsed.gruId === "string" ? parsed.gruId : null,
      port: typeof parsed.port === "number" ? parsed.port : null,
    };
  } catch {
    return { gruId: null, port: null };
  }
}

function saveSelection(sel: Selection) {
  try {
    if (sel.gruId == null && sel.port == null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sel));
    }
  } catch {}
}

const empty: NetworkSnapshot = {
  tasks: [],
  agents: [],
  cluster: null,
  logs: [],
  messages: [],
  connected: false,
  eacnEndpoint: "",
  lastUpdate: 0,
  selectedPort: null,
  selectedGruId: null,
  grus: [],
};

let snapshot: NetworkSnapshot = { ...empty };
const listeners = new Set<() => void>();
let ws: WebSocket | null = null;
let notifyScheduled = false;

/** Role-log stream: append-only per (role) string, shared for the current (gruId,port). */
const roleLogBuffers = new Map<string, string>();
const roleLogListeners = new Map<string, Set<() => void>>();
const roleLogRefCounts = new Map<string, number>();
const pendingRoleLogRoles = new Set<string>();
let roleLogNotifyScheduled = false;

function flushNotify() {
  notifyScheduled = false;
  for (const l of listeners) l();
}

function notify() {
  if (notifyScheduled) return;
  notifyScheduled = true;
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(flushNotify);
  } else {
    setTimeout(flushNotify, 16);
  }
}

function flushRoleLogNotify() {
  roleLogNotifyScheduled = false;
  const roles = Array.from(pendingRoleLogRoles);
  pendingRoleLogRoles.clear();
  for (const role of roles) {
    const set = roleLogListeners.get(role);
    if (set) for (const l of set) l();
  }
}

function notifyRoleLog(role: string) {
  pendingRoleLogRoles.add(role);
  if (roleLogNotifyScheduled) return;
  roleLogNotifyScheduled = true;
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(flushRoleLogNotify);
  } else {
    setTimeout(flushRoleLogNotify, 16);
  }
}

function notifyAllRoleLogs() {
  for (const role of roleLogListeners.keys()) pendingRoleLogRoles.add(role);
  if (roleLogNotifyScheduled) return;
  roleLogNotifyScheduled = true;
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(flushRoleLogNotify);
  } else {
    setTimeout(flushRoleLogNotify, 16);
  }
}

function applyMessage(msg: WsMessage) {
  let snapshotChanged = true;
  switch (msg.type) {
    case "snapshot":
      snapshot = { ...msg.data };
      break;
    case "tasks:update":
      snapshot = { ...snapshot, tasks: msg.data, lastUpdate: Date.now() };
      break;
    case "agents:update":
      snapshot = { ...snapshot, agents: msg.data, lastUpdate: Date.now() };
      break;
    case "cluster:update":
      snapshot = { ...snapshot, cluster: msg.data, lastUpdate: Date.now() };
      break;
    case "logs:update":
      snapshot = { ...snapshot, logs: msg.data, lastUpdate: Date.now() };
      break;
    case "messages:update":
      snapshot = { ...snapshot, messages: msg.data, lastUpdate: Date.now() };
      break;
    case "connection:status":
      snapshot = { ...snapshot, connected: msg.data.connected };
      break;
    case "grus:update":
      snapshot = { ...snapshot, grus: msg.data };
      break;
    case "selected":
      snapshot = {
        ...snapshot,
        selectedGruId: msg.data.gruId,
        selectedPort: msg.data.port,
        eacnEndpoint:
          msg.data.port != null ? `http://127.0.0.1:${msg.data.port}` : "",
      };
      // New selection ⇒ clear role-log buffers.
      roleLogBuffers.clear();
      notifyAllRoleLogs();
      break;
    case "role-log:append": {
      const prev = roleLogBuffers.get(msg.data.role) ?? "";
      const next = (prev + msg.data.chunk).slice(-64_000); // cap per role
      roleLogBuffers.set(msg.data.role, next);
      notifyRoleLog(msg.data.role);
      snapshotChanged = false;
      break;
    }
  }
  if (snapshotChanged) notify();
}

function sendJSON(obj: unknown) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

export function selectGruProject(gruId: string | null, port: number | null) {
  saveSelection({ gruId, port });
  sendJSON({ type: "select", gruId, port });
  snapshot = {
    ...snapshot,
    selectedGruId: gruId,
    selectedPort: port,
    eacnEndpoint: port != null ? `http://127.0.0.1:${port}` : "",
    tasks: [],
    agents: [],
    cluster: null,
    logs: [],
    messages: [],
    connected: false,
  };
  roleLogBuffers.clear();
  notifyAllRoleLogs();
  notify();
}

export function subscribeRoleLog(role: string) {
  const refs = roleLogRefCounts.get(role) ?? 0;
  roleLogRefCounts.set(role, refs + 1);
  if (refs > 0) return;

  sendJSON({ type: "subscribe-role-log", role });
  // Kick off a one-shot fetch for the tail (pre-stream history).
  const sel = snapshot;
  if (sel.selectedGruId && sel.selectedPort != null) {
    fetch(
      `/api/mos/project/${sel.selectedPort}/role-log/${encodeURIComponent(role)}?gru=${sel.selectedGruId}&tail=500`,
    )
      .then((r) => (r.ok ? r.text() : ""))
      .then((text) => {
        if (!text) return;
        const prev = roleLogBuffers.get(role) ?? "";
        roleLogBuffers.set(role, (text + prev).slice(-64_000));
        notifyRoleLog(role);
      })
      .catch(() => {});
  }
}

export function unsubscribeRoleLog(role: string) {
  const refs = roleLogRefCounts.get(role) ?? 0;
  if (refs > 1) {
    roleLogRefCounts.set(role, refs - 1);
    return;
  }
  roleLogRefCounts.delete(role);
  sendJSON({ type: "unsubscribe-role-log", role });
}

export function useRoleLog(role: string | null): string {
  return useSyncExternalStore(
    (cb) => {
      if (!role) return () => {};
      let set = roleLogListeners.get(role);
      if (!set) {
        set = new Set();
        roleLogListeners.set(role, set);
      }
      set.add(cb);
      return () => {
        set?.delete(cb);
      };
    },
    () => (role ? (roleLogBuffers.get(role) ?? "") : ""),
  );
}

function startSocket(): () => void {
  let cancelled = false;
  let reconnect: ReturnType<typeof setTimeout> | null = null;
  function connect() {
    if (cancelled) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onopen = () => {
      const saved = loadSelection();
      if (saved.gruId || saved.port != null) {
        sendJSON({ type: "select", gruId: saved.gruId, port: saved.port });
      }
    };
    ws.onmessage = (e) => {
      try {
        applyMessage(JSON.parse(e.data));
      } catch {}
    };
    ws.onclose = () => {
      if (!cancelled) reconnect = setTimeout(connect, 1500);
    };
    ws.onerror = () => ws?.close();
  }
  connect();
  return () => {
    cancelled = true;
    if (reconnect) clearTimeout(reconnect);
    ws?.close();
  };
}

export function useStore(): NetworkSnapshot {
  const cleanupRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    cleanupRef.current = startSocket();
    return () => cleanupRef.current?.();
  }, []);
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => snapshot,
  );
}

export function gruById(grus: GruInfo[], id: string | null): GruInfo | null {
  if (!id) return null;
  return grus.find((g) => g.id === id) ?? null;
}

export function projectByPort(
  projects: MosProject[],
  port: number | null,
): MosProject | null {
  if (port == null) return null;
  return projects.find((p) => p.port === port) ?? null;
}

/** Flag an agent as "the Gru" (star), vs planetary role. */
export function isGruAgent(agentId: string, name?: string): boolean {
  const s = (agentId + " " + (name ?? "")).toLowerCase();
  return /\bgru\b/.test(s) || s.startsWith("gru") || s.endsWith("-gru");
}
