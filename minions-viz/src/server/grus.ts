/**
 * Multi-Gru registry reader. Reads ~/.minionsos/grus.json and each
 * registered Gru's minions/state/projects.json.
 */
import fs from "fs";
import path from "path";
import os from "os";
import type { MosProject, GruInfo } from "../shared/types.js";

const USER_DIR = path.join(os.homedir(), ".minionsos");
const REGISTRY = path.join(USER_DIR, "grus.json");
const LOCK = path.join(USER_DIR, "grus.lock");
const STALE_MS = 2 * 60 * 1000;

interface GruRegEntry {
  id: string;
  label: string;
  root_path: string;
  state_dir: string;
  parent_repo: string;
  registered_at: string;
  last_seen: string;
}

interface Registry { grus: GruRegEntry[] }

export function userDir(): string { return USER_DIR; }
export function registryPath(): string { return REGISTRY; }

function ensureUserDir() {
  try { fs.mkdirSync(USER_DIR, { recursive: true, mode: 0o700 }); } catch {}
}

function acquireLock(timeoutMs = 3000): boolean {
  const start = Date.now();
  ensureUserDir();
  while (Date.now() - start < timeoutMs) {
    try {
      fs.mkdirSync(LOCK);
      return true;
    } catch {
      // busy
      const age = (() => {
        try { return Date.now() - fs.statSync(LOCK).mtimeMs; } catch { return 0; }
      })();
      if (age > 30_000) {
        try { fs.rmdirSync(LOCK); } catch {}
      }
      // small sleep
      const until = Date.now() + 50;
      while (Date.now() < until) { /* spin */ }
    }
  }
  return false;
}

function releaseLock() {
  try { fs.rmdirSync(LOCK); } catch {}
}

function readRegistry(): Registry {
  try {
    const raw = fs.readFileSync(REGISTRY, "utf8");
    const parsed = JSON.parse(raw) as Registry;
    return { grus: parsed.grus ?? [] };
  } catch {
    return { grus: [] };
  }
}

function writeRegistry(reg: Registry) {
  ensureUserDir();
  const tmp = REGISTRY + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(reg, null, 2), { mode: 0o600 });
  fs.renameSync(tmp, REGISTRY);
}

/** Read a Gru's projects.json from its state_dir. */
function readProjectsForGru(stateDir: string): { projects: MosProject[]; mtimeMs: number } {
  const pj = path.join(stateDir, "projects.json");
  try {
    const st = fs.statSync(pj);
    const raw = fs.readFileSync(pj, "utf8");
    const parsed = JSON.parse(raw) as { projects?: MosProject[] };
    const projects = (parsed.projects ?? []).map((p) => ({
      port: p.port,
      real_name: p.real_name,
      status: p.status,
      created: p.created,
      dormant_at: p.dormant_at ?? null,
      closed_at: p.closed_at ?? null,
      venue: p.venue ?? null,
      upstream_branch: p.upstream_branch ?? "main",
      current_branch: p.current_branch ?? "",
      active_roles: p.active_roles ?? [],
    }));
    return { projects, mtimeMs: st.mtimeMs };
  } catch {
    return { projects: [], mtimeMs: 0 };
  }
}

interface CacheEntry {
  info: GruInfo;
  readAt: number;
  projectsMtimeMs: number;
}

const cache = new Map<string, CacheEntry>();
const CACHE_TTL = 5_000;

export function loadGrus(): GruInfo[] {
  const reg = readRegistry();
  const now = Date.now();
  const out: GruInfo[] = [];
  let touchedRegistry = false;

  for (const e of reg.grus) {
    const cached = cache.get(e.id);
    if (cached && now - cached.readAt < CACHE_TTL) {
      out.push(cached.info);
      continue;
    }
    const { projects, mtimeMs } = readProjectsForGru(e.state_dir);
    // server-side auto-heartbeat: touch last_seen if read succeeded
    if (mtimeMs > 0) {
      e.last_seen = new Date().toISOString();
      touchedRegistry = true;
    }
    const lastSeenMs = e.last_seen ? new Date(e.last_seen).getTime() : 0;
    const online =
      (now - lastSeenMs < STALE_MS) ||
      (mtimeMs > 0 && now - mtimeMs < STALE_MS);
    const info: GruInfo = {
      id: e.id,
      label: e.label,
      rootPath: e.root_path,
      parentRepo: e.parent_repo,
      stateDir: e.state_dir,
      lastSeen: e.last_seen,
      online,
      projects,
    };
    cache.set(e.id, { info, readAt: now, projectsMtimeMs: mtimeMs });
    out.push(info);
  }

  if (touchedRegistry) {
    if (acquireLock()) {
      try {
        // re-read, merge last_seen updates, write back
        const cur = readRegistry();
        const byId = new Map(cur.grus.map((g) => [g.id, g]));
        for (const e of reg.grus) {
          const existing = byId.get(e.id);
          if (existing && e.last_seen > (existing.last_seen ?? "")) {
            existing.last_seen = e.last_seen;
          }
        }
        writeRegistry(cur);
      } finally { releaseLock(); }
    }
  }

  return out;
}

export function getGru(gruId: string): GruInfo | null {
  return loadGrus().find((g) => g.id === gruId) ?? null;
}

export function getProjectFor(gruId: string, port: number): MosProject | null {
  const g = getGru(gruId);
  if (!g) return null;
  return g.projects.find((p) => p.port === port) ?? null;
}

/** Resolve `project_{port}` dir for a given Gru's rootPath. */
export function projectDirFor(gruRootPath: string, port: number): string {
  // Default: MINIONS_ROOT/projects/project_{port}
  // Honors MINIONS_PROJECTS_ROOT if set (read from process.env at runtime)
  const projectsRoot = process.env.MINIONS_PROJECTS_ROOT || path.join(gruRootPath, "projects");
  return path.join(projectsRoot, `project_${port}`);
}

export function gruLogPath(gruRootPath: string): string {
  return path.join(gruRootPath, "minions", "state", "logs", "gru.log");
}
