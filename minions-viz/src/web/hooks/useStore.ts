import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import type { NetworkSnapshot, WsMessage, GruInfo, MosProject } from "@shared/types";

const STORAGE_KEY = "mos.viz.selection";

interface Saved { gruId: string | null; port: number | null }

export function getSavedSelection(): Saved {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (!v) return { gruId: null, port: null };
    const parsed = JSON.parse(v) as Saved;
    return {
      gruId: typeof parsed.gruId === "string" ? parsed.gruId : null,
      port: typeof parsed.port === "number" ? parsed.port : null,
    };
  } catch { return { gruId: null, port: null }; }
}

export function saveSelection(sel: Saved) {
  try {
    if (sel.gruId == null && sel.port == null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(sel));
  } catch {}
}

// Legacy shims (still referenced by some components).
export function getSavedPort(): number | null { return getSavedSelection().port; }
export function savePort(port: number | null) {
  const cur = getSavedSelection();
  saveSelection({ gruId: cur.gruId, port });
}
export function needsSetup(): boolean { return false; }
export function getSavedEndpoint(): string { return ""; }
export function reconnectWithEndpoint(_ep: string): void { /* no-op */ }

const empty: NetworkSnapshot = {
  tasks: [], agents: [], cluster: null, logs: [], messages: [],
  connected: false, eacnEndpoint: "", lastUpdate: 0,
  selectedPort: null, selectedGruId: null, grus: [],
};

let snapshot: NetworkSnapshot = { ...empty };
const listeners = new Set<() => void>();
let wsRef: WebSocket | null = null;

function notify() { listeners.forEach((l) => l()); }

function applyMessage(msg: WsMessage) {
  switch (msg.type) {
    case "snapshot": snapshot = { ...msg.data }; break;
    case "tasks:update": snapshot = { ...snapshot, tasks: msg.data, lastUpdate: Date.now() }; break;
    case "agents:update": snapshot = { ...snapshot, agents: msg.data, lastUpdate: Date.now() }; break;
    case "cluster:update": snapshot = { ...snapshot, cluster: msg.data, lastUpdate: Date.now() }; break;
    case "logs:update": snapshot = { ...snapshot, logs: msg.data, lastUpdate: Date.now() }; break;
    case "messages:update": snapshot = { ...snapshot, messages: msg.data, lastUpdate: Date.now() }; break;
    case "connection:status": snapshot = { ...snapshot, connected: msg.data.connected }; break;
    case "grus:update": snapshot = { ...snapshot, grus: msg.data }; break;
    case "selected":
      snapshot = {
        ...snapshot,
        selectedGruId: msg.data.gruId,
        selectedPort: msg.data.port,
        eacnEndpoint: msg.data.port != null ? `http://127.0.0.1:${msg.data.port}` : "",
      };
      break;
    // legacy
    case "projects:update": {
      // Merge into first Gru if present
      const grus = snapshot.grus.length > 0
        ? [{ ...snapshot.grus[0], projects: msg.data }, ...snapshot.grus.slice(1)]
        : [];
      snapshot = { ...snapshot, grus };
      break;
    }
    case "selected_project":
      snapshot = {
        ...snapshot,
        selectedPort: msg.data.port,
        eacnEndpoint: msg.data.port != null ? `http://127.0.0.1:${msg.data.port}` : "",
      };
      break;
    default: return;
  }
  notify();
}

function sendSelect(sel: Saved) {
  if (wsRef && wsRef.readyState === WebSocket.OPEN) {
    wsRef.send(JSON.stringify({ type: "select", gruId: sel.gruId, port: sel.port }));
  }
}

export function select(gruId: string | null, port: number | null) {
  const sel: Saved = { gruId, port };
  saveSelection(sel);
  sendSelect(sel);
  snapshot = {
    ...snapshot, selectedGruId: gruId, selectedPort: port,
    eacnEndpoint: port != null ? `http://127.0.0.1:${port}` : "",
    tasks: [], agents: [], cluster: null, logs: [], messages: [], connected: false,
  };
  notify();
}

export function selectGru(gruId: string | null) {
  select(gruId, null);
}

export function selectProject(port: number | null) {
  select(snapshot.selectedGruId, port);
}

function startWebSocket(): () => void {
  let cancelled = false;
  let reconnectTimer: ReturnType<typeof setTimeout>;
  function connect() {
    if (cancelled) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    wsRef = ws;
    ws.onopen = () => {
      const saved = getSavedSelection();
      if (saved.gruId || saved.port != null) sendSelect(saved);
    };
    ws.onmessage = (e) => { try { applyMessage(JSON.parse(e.data)); } catch {} };
    ws.onclose = () => { if (!cancelled) reconnectTimer = setTimeout(connect, 2000); };
    ws.onerror = () => ws.close();
  }
  connect();
  return () => {
    cancelled = true;
    clearTimeout(reconnectTimer);
    wsRef?.close();
  };
}

export function useStore(): NetworkSnapshot {
  const cleanupRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    cleanupRef.current = startWebSocket();
    return () => { cleanupRef.current?.(); };
  }, []);
  const subscribe = useCallback((cb: () => void) => {
    listeners.add(cb);
    return () => { listeners.delete(cb); };
  }, []);
  return useSyncExternalStore(subscribe, () => snapshot);
}

export function gruById(grus: GruInfo[], id: string | null): GruInfo | null {
  if (!id) return null;
  return grus.find((g) => g.id === id) ?? null;
}

export function projectByPort(projects: MosProject[], port: number | null): MosProject | null {
  if (port == null) return null;
  return projects.find((p) => p.port === port) ?? null;
}
