/**
 * MinionsOS Project Observatory — Express + WebSocket server (multi-Gru).
 */
import express from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";
import {
  checkHealth, fetchTasks, fetchCluster, fetchLogs, fetchAgents,
  enrichAgents, collectDomains, endpointForPort, fetchMessages,
} from "./poller.js";
import {
  addClient, removeClient, setConnected, updateTasks, updateAgents,
  updateCluster, updateLogs, updateMessages, snapshotFor, ensurePair, setSelection,
  getSelection, setGrus, activePairs,
} from "./state.js";
import { loadGrus, getGru, getProjectFor, registryPath, projectDirFor } from "./grus.js";
import {
  getOverview, getDrafts, getDraft, getArtifactsTree,
  getArtifact, tailLog, roleLogPath,
} from "./mosFs.js";
import {
  addRoleLogViewer, removeRoleLogViewer, dropAllViewersFor,
} from "./roleLogTail.js";

const PORT = Number(process.env.PORT) || 7891;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server, path: "/ws" });

const wsViewers = new WeakMap<WebSocket, Set<string>>();
function viewerKey(gruId: string, port: number, role: string) {
  return `${gruId}::${port}::${role}`;
}

wss.on("connection", (ws: WebSocket) => {
  addClient(ws);
  wsViewers.set(ws, new Set());

  ws.on("message", (raw) => {
    try {
      const msg = JSON.parse(raw.toString()) as {
        type?: string; gruId?: string | null; port?: number | null; role?: string | null;
      };
      if (msg.type === "select") {
        const old = getSelection(ws);
        if (old.gruId && old.port != null) {
          const set = wsViewers.get(ws);
          if (set) {
            for (const k of Array.from(set)) {
              const [gid, portStr, role] = k.split("::");
              removeRoleLogViewer(gid, Number(portStr), role);
              set.delete(k);
            }
          }
        }
        const gruId = typeof msg.gruId === "string" ? msg.gruId : null;
        const port = typeof msg.port === "number" ? msg.port : null;
        setSelection(ws, { gruId, port });
        if (gruId && port != null) pollPairNow(gruId, port);
      } else if (msg.type === "subscribe-role-log") {
        const sel = getSelection(ws);
        const role = typeof msg.role === "string" ? msg.role.trim() : "";
        if (!role || !sel.gruId || sel.port == null) return;
        const k = viewerKey(sel.gruId, sel.port, role);
        const set = wsViewers.get(ws) ?? new Set<string>();
        if (!set.has(k)) {
          set.add(k); wsViewers.set(ws, set);
          addRoleLogViewer(sel.gruId, sel.port, role);
        }
      } else if (msg.type === "unsubscribe-role-log") {
        const sel = getSelection(ws);
        const role = typeof msg.role === "string" ? msg.role.trim() : "";
        if (!role || !sel.gruId || sel.port == null) return;
        const k = viewerKey(sel.gruId, sel.port, role);
        const set = wsViewers.get(ws);
        if (set && set.has(k)) {
          set.delete(k);
          removeRoleLogViewer(sel.gruId, sel.port, role);
        }
      }
    } catch {}
  });

  ws.on("close", () => {
    const set = wsViewers.get(ws);
    if (set) {
      for (const k of set) {
        const [gid, portStr, role] = k.split("::");
        removeRoleLogViewer(gid, Number(portStr), role);
      }
    }
    wsViewers.delete(ws);
    removeClient(ws);
  });
  ws.on("error", () => { removeClient(ws); });
});

// ── HTTP routes ─────────────────────────────────────────────────────
const webDir = path.resolve(__dirname, "../../dist/web");

app.use(express.static(webDir, {
  setHeaders(res, filePath) {
    if (filePath.endsWith(".html")) {
      res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    }
  },
}));

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

app.get("/api/mos/projects", (_req, res) => {
  const all = loadGrus().flatMap((g) => g.projects);
  res.json(all);
});

app.get("/api/mos/project/:port/overview", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const out = getOverview(p.gruId, p.port);
  if (!out) return res.status(404).json({ error: "not found" });
  res.json(out);
});

app.get("/api/mos/project/:port/drafts", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  res.json(getDrafts(p.gruId, p.port));
});

app.get("/api/mos/project/:port/draft/:role", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const content = getDraft(p.gruId, p.port, req.params.role);
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

app.get("/api/mos/project/:port/draft", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const g = getGru(p.gruId);
  if (!g) return res.status(404).json({ error: "unknown gru" });
  // The canonical L1 Draft path is branches/shared/draft/draft.json
  // (Noter publishes there via mos_draft_commit_shared). The legacy
  // <project>/draft/ path is a pre-shared-branch artefact that's no
  // longer maintained — read both with shared/ first, fall back for
  // ancient projects that still have the old layout.
  const projectDir = projectDirFor(g.rootPath, p.port);
  const draftCandidates = [
    path.join(projectDir, "branches", "shared", "draft", "draft.json"),
    path.join(projectDir, "draft", "draft.json"),
  ];
  for (const draftFile of draftCandidates) {
    try {
      const raw = fs.readFileSync(draftFile, "utf8");
      const parsed = JSON.parse(raw);
      // Guard against malformed draft files: ensure nodes/edges are arrays
      // before sending to the client (DraftView assumes both are arrays).
      const safe = {
        project_port: parsed.project_port ?? p.port,
        root_question: typeof parsed.root_question === "string" ? parsed.root_question : "",
        nodes: Array.isArray(parsed.nodes) ? parsed.nodes : [],
        edges: Array.isArray(parsed.edges) ? parsed.edges : [],
      };
      return res.json(safe);
    } catch {
      // try next candidate
    }
  }
  return res.json({ project_port: p.port, root_question: "", nodes: [], edges: [] });
});

app.get("/api/mos/project/:port/book", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const g = getGru(p.gruId);
  if (!g) return res.status(404).json({ error: "unknown gru" });
  const bookDir = path.join(projectDirFor(g.rootPath, p.port), "branches", "shared", "book");
  const MAX_ENTRIES = 500;
  const MAX_BYTES_PER_FILE = 256 * 1024;
  try {
    const entries: any[] = [];
    if (fs.existsSync(bookDir)) {
      const stack: string[] = [bookDir];
      while (stack.length && entries.length < MAX_ENTRIES) {
        const dir = stack.pop()!;
        for (const name of fs.readdirSync(dir)) {
          const abs = path.join(dir, name);
          const st = fs.statSync(abs);
          if (st.isDirectory()) {
            stack.push(abs);
          } else if (st.isFile() && name.endsWith(".md") && st.size <= MAX_BYTES_PER_FILE) {
            const rel = path.relative(bookDir, abs).replace(/\\/g, "/");
            const title = rel.replace(/\.md$/, "");
            const kind = rel.includes("/") ? rel.split("/")[0] : "root";
            entries.push({
              title,
              path: rel,
              kind,
              content: fs.readFileSync(abs, "utf8"),
              updated_at: st.mtime,
            });
            if (entries.length >= MAX_ENTRIES) break;
          }
        }
      }
    }
    res.json({ entries });
  } catch {
    res.json({ entries: [] });
  }
});

app.get("/api/mos/project/:port/role-log/:role", (req, res) => {
  const p = resolveGruAndPort(req, res); if (!p) return;
  const role = req.params.role;
  const abs = roleLogPath(p.gruId, p.port, role);
  if (!abs) return res.status(400).type("text/plain").send("");
  const tail = Number(req.query.tail ?? 500);
  try {
    const raw = fs.readFileSync(abs, "utf8");
    const lines = raw.split("\n");
    res.type("text/plain").send(lines.slice(Math.max(0, lines.length - tail)).join("\n"));
  } catch {
    // Role log file doesn't exist yet — that's fine; return 200 + empty body
    // so clients don't emit console errors.
    res.type("text/plain").send("");
  }
});

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

async function pollRegistry() { setGrus(loadGrus()); }

async function pollPairNow(gruId: string, port: number) {
  const ep = endpointForPort(port);
  const ok = await checkHealth(ep);
  setConnected(gruId, port, ok);
  if (!ok) return;
  ensurePair(gruId, port);
  const [tasks, cluster, logs, messages] = await Promise.all([
    fetchTasks(ep), fetchCluster(ep), fetchLogs(ep), fetchMessages(ep),
  ]);
  updateTasks(gruId, port, tasks);
  updateCluster(gruId, port, cluster);
  if (logs.length > 0) updateLogs(gruId, port, logs);
  if (messages.length > 0) updateMessages(gruId, port, messages);
  const ctx = ctxFor(gruId, port);
  ctx.domains = collectDomains(tasks, cluster);
  if (cluster) {
    for (const d of cluster.local.domains) ctx.domains.add(d);
    for (const m of cluster.members) for (const d of m.domains) ctx.domains.add(d);
  }
  const cards = await fetchAgents(ep, ctx.domains);
  const agents = await enrichAgents(ep, cards);
  updateAgents(gruId, port, agents);
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

async function pollMessages() {
  for (const { gruId, port } of activePairs()) {
    const messages = await fetchMessages(endpointForPort(port));
    if (messages.length > 0) updateMessages(gruId, port, messages);
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
  setInterval(pollMessages, 5_000);
}

void dropAllViewersFor;

server.listen(PORT, () => {
  console.log(`[mos-viz] http://localhost:${PORT}`);
  console.log(`[mos-viz] Gru registry: ${registryPath()}`);
  startPolling();
});
