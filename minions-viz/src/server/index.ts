/**
 * MinionsOS Project Observatory — Express + WebSocket server (multi-Gru).
 *
 * - Discovers Grus from ~/.minionsos/grus.json; each has its own projects.json.
 * - Polls each (gruId, port) pair's local EACN3 backend only while a client
 *   has that pair selected.
 */
import express from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import path from "path";
import { fileURLToPath } from "url";
import {
  checkHealth, fetchTasks, fetchCluster, fetchLogs, fetchAgents,
  enrichAgents, collectDomains, endpointForPort,
} from "./poller.js";
import {
  addClient, removeClient, setConnected, updateTasks, updateAgents,
  updateCluster, updateLogs, snapshotFor, ensurePair, setSelection,
  getSelection, setGrus, activePairs,
} from "./state.js";
import { loadGrus, getGru, getProjectFor, registryPath } from "./grus.js";
import {
  getOverview, getScratchpads, getScratchpad, getArtifactsTree,
  getArtifact, tailLog, listRoleSystemPrompts,
} from "./mosFs.js";

const PORT = Number(process.env.PORT) || 7891;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server, path: "/ws" });

wss.on("connection", (ws: WebSocket) => {
  addClient(ws);
  ws.on("message", (raw) => {
    try {
      const msg = JSON.parse(raw.toString()) as {
        type?: string; gruId?: string | null; port?: number | null;
      };
      if (msg.type === "select") {
        const gruId = typeof msg.gruId === "string" ? msg.gruId : null;
        const port = typeof msg.port === "number" ? msg.port : null;
        setSelection(ws, { gruId, port });
      } else if (msg.type === "select_project") {
        // legacy: keep existing gruId if any, else pick first online Gru
        const cur = getSelection(ws);
        let gruId = cur.gruId;
        if (!gruId) {
          const grus = loadGrus();
          gruId = (grus.find((g) => g.online) ?? grus[0])?.id ?? null;
        }
        const port = typeof msg.port === "number" ? msg.port : null;
        setSelection(ws, { gruId, port });
      }
    } catch {}
  });
  ws.on("close", () => removeClient(ws));
  ws.on("error", () => removeClient(ws));
});

// ── HTTP routes ─────────────────────────────────────────────────────
const webDir = path.resolve(__dirname, "../../dist/web");

function resolveGruAndPort(req: express.Request, res: express.Response): { gruId: string; port: number } | null {
  const gruId = String(req.query.gru ?? "");
  const port = Number(req.params.port);
  if (!gruId) { res.status(400).json({ error: "missing ?gru=<id>" }); return null; }
  if (!Number.isFinite(port)) { res.status(400).json({ error: "bad port" }); return null; }
  const g = getGru(gruId);
  if (!g) { res.status(404).json({ error: "unknown gru" }); return null; }
  if (!getProjectFor(gruId, port)) { res.status(404).json({ error: "unknown project for gru" }); return null; }
  return { gruId, port };
}

app.get("/api/snapshot", (req, res) => {
  const gruId = req.query.gru ? String(req.query.gru) : null;
  const port = req.query.port ? Number(req.query.port) : null;
  res.json(snapshotFor({ gruId, port }));
});

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.get("/api/mos/grus", (_req, res) => res.json(loadGrus()));

// Legacy: flat projects list across all Grus.
app.get("/api/mos/projects", (_req, res) => {
  const all = loadGrus().flatMap((g) => g.projects);
  res.json(all);
});

app.get("/api/mos/roles", (req, res) => {
  const gruId = String(req.query.gru ?? "");
  res.json(listRoleSystemPrompts(gruId));
});

app.get("/api/mos/project/:port/overview", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const out = getOverview(p.gruId, p.port);
  if (!out) return res.status(404).json({ error: "not found" });
  res.json(out);
});

app.get("/api/mos/project/:port/scratchpads", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  res.json(getScratchpads(p.gruId, p.port));
});

app.get("/api/mos/project/:port/scratchpad/:role", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const content = getScratchpad(p.gruId, p.port, req.params.role);
  if (content == null) return res.status(404).json({ error: "not found" });
  res.type("text/markdown").send(content);
});

app.get("/api/mos/project/:port/artifacts", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  res.json(getArtifactsTree(p.gruId, p.port));
});

app.get("/api/mos/project/:port/artifact", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const rel = String(req.query.path ?? "");
  const out = getArtifact(p.gruId, p.port, rel);
  if (!out) return res.status(404).json({ error: "not found" });
  res.json(out);
});

app.get("/api/mos/project/:port/log", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const which = String(req.query.which ?? "backend");
  const tail = Number(req.query.tail ?? 500);
  const content = tailLog(p.gruId, p.port, which, tail);
  if (content == null) return res.status(404).json({ error: "not found" });
  res.type("text/plain").send(content);
});

app.use(express.static(webDir));
app.get("*", (_req, res) => res.sendFile(path.join(webDir, "index.html")));

// ── Polling ─────────────────────────────────────────────────────────
interface PollCtx { domains: Set<string>; }
const pollCtx = new Map<string, PollCtx>();
function ctxFor(gruId: string, port: number): PollCtx {
  const k = `${gruId}::${port}`;
  let c = pollCtx.get(k);
  if (!c) { c = { domains: new Set() }; pollCtx.set(k, c); }
  return c;
}

async function pollRegistry() {
  setGrus(loadGrus());
}

async function pollHealth() {
  for (const { gruId, port } of activePairs()) {
    const ok = await checkHealth(endpointForPort(port));
    setConnected(gruId, port, ok);
  }
}

async function pollTasks() {
  for (const { gruId, port } of activePairs()) {
    const snap = ensurePair(gruId, port);
    const tasks = await fetchTasks(endpointForPort(port));
    updateTasks(gruId, port, tasks);
    ctxFor(gruId, port).domains = collectDomains(tasks, snap.cluster);
  }
}

async function pollCluster() {
  for (const { gruId, port } of activePairs()) {
    const cluster = await fetchCluster(endpointForPort(port));
    updateCluster(gruId, port, cluster);
    if (cluster) {
      const c = ctxFor(gruId, port);
      for (const d of cluster.local.domains) c.domains.add(d);
      for (const m of cluster.members) for (const d of m.domains) c.domains.add(d);
    }
  }
}

async function pollAgents() {
  for (const { gruId, port } of activePairs()) {
    const cards = await fetchAgents(endpointForPort(port), ctxFor(gruId, port).domains);
    const agents = await enrichAgents(endpointForPort(port), cards);
    updateAgents(gruId, port, agents);
  }
}

async function pollLogsAll() {
  for (const { gruId, port } of activePairs()) {
    const logs = await fetchLogs(endpointForPort(port));
    if (logs.length > 0) updateLogs(gruId, port, logs);
  }
}

function startPolling() {
  pollRegistry();
  setInterval(pollRegistry, 5_000);
  setInterval(pollHealth, 15_000);
  setInterval(pollTasks, 3_000);
  setInterval(pollAgents, 10_000);
  setInterval(pollCluster, 30_000);
  setInterval(pollLogsAll, 3_000);
}

server.listen(PORT, () => {
  console.log(`[mos-viz] http://localhost:${PORT}`);
  console.log(`[mos-viz] Gru registry: ${registryPath()}`);
  startPolling();
});
