/**
 * MinionsOS filesystem views (read-only).
 */
import fs from "fs";
import path from "path";
import type {
  MosOverview, MosDraft, MosArtifactNode, MosThresholdStatus,
} from "../shared/types.js";
import { getGru, getProjectFor, projectDirFor, gruLogPath } from "./grus.js";

export const CANONICAL_ROLES = ["gru", "noter", "coder", "writer", "expert", "ethics"];

const CONTEXT_WINDOW_TOKENS = 1_000_000;
const SOFT_TOKENS = 0.10 * CONTEXT_WINDOW_TOKENS;
const HARD_TOKENS = 0.15 * CONTEXT_WINDOW_TOKENS;
const VETO_TOKENS = 0.20 * CONTEXT_WINDOW_TOKENS;

function safeResolve(root: string, rel: string): string | null {
  const abs = path.resolve(root, rel);
  const normRoot = path.resolve(root) + path.sep;
  if (abs !== path.resolve(root) && !abs.startsWith(normRoot)) return null;
  return abs;
}

function statusFor(tokens: number): MosThresholdStatus {
  if (tokens >= VETO_TOKENS) return "veto";
  if (tokens >= HARD_TOKENS) return "hard";
  if (tokens >= SOFT_TOKENS) return "soft";
  return "ok";
}

function resolveProjectDir(gruId: string, port: number): string | null {
  const g = getGru(gruId);
  if (!g) return null;
  return projectDirFor(g.rootPath, port);
}

export function getOverview(gruId: string, port: number): MosOverview | null {
  const pdir = resolveProjectDir(gruId, port);
  if (!pdir) return null;
  const project = getProjectFor(gruId, port);
  let claude_md: string | null = null;
  let meta: Record<string, unknown> | null = null;
  try { claude_md = fs.readFileSync(path.join(pdir, "CLAUDE.md"), "utf8"); } catch {}
  try { meta = JSON.parse(fs.readFileSync(path.join(pdir, "meta.json"), "utf8")); } catch {}
  return {
    port, project, claude_md, meta,
    project_dir: pdir,
    workspace_dir: path.join(pdir, "workspace"),
    artifacts_dir: path.join(pdir, "artifacts"),
  };
}

export function getDrafts(gruId: string, port: number): MosDraft[] {
  const pdir = resolveProjectDir(gruId, port);
  if (!pdir) return [];
  const memDir = path.join(pdir, "memory");
  return CANONICAL_ROLES.map((role) => {
    const p = path.join(memDir, `${role}.md`);
    try {
      const st = fs.statSync(p);
      const tokens = Math.round(st.size / 4);
      return {
        role, path: p, exists: true, bytes: st.size,
        approx_tokens: tokens, threshold_status: statusFor(tokens),
        mtime: st.mtimeMs,
      };
    } catch {
      return {
        role, path: p, exists: false, bytes: 0, approx_tokens: 0,
        threshold_status: "ok" as const, mtime: null,
      };
    }
  });
}

export function getDraft(gruId: string, port: number, role: string): string | null {
  if (!CANONICAL_ROLES.includes(role)) return null;
  const pdir = resolveProjectDir(gruId, port);
  if (!pdir) return null;
  const p = path.join(pdir, "memory", `${role}.md`);
  try { return fs.readFileSync(p, "utf8"); } catch { return null; }
}

export function getArtifactsTree(gruId: string, port: number, maxDepth = 2): MosArtifactNode | null {
  const pdir = resolveProjectDir(gruId, port);
  if (!pdir) return null;
  const root = path.join(pdir, "artifacts");
  function walk(abs: string, rel: string, depth: number): MosArtifactNode | null {
    let st: fs.Stats;
    try { st = fs.statSync(abs); } catch { return null; }
    const name = path.basename(abs) || "artifacts";
    if (st.isDirectory()) {
      let children: MosArtifactNode[] | undefined;
      if (depth < maxDepth) {
        try {
          children = fs.readdirSync(abs)
            .map((c) => walk(path.join(abs, c), path.join(rel, c), depth + 1))
            .filter((x): x is MosArtifactNode => x !== null)
            .sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1));
        } catch { children = []; }
      }
      return { name, path: rel, kind: "dir", size: 0, mtime: st.mtimeMs, children };
    }
    if (st.isFile()) {
      return { name, path: rel, kind: "file", size: st.size, mtime: st.mtimeMs };
    }
    return null;
  }
  return walk(root, "", 0);
}

export function getArtifact(gruId: string, port: number, rel: string): { content: string; binary: boolean; size: number } | null {
  const pdir = resolveProjectDir(gruId, port);
  if (!pdir) return null;
  const root = path.join(pdir, "artifacts");
  const abs = safeResolve(root, rel);
  if (!abs) return null;
  try {
    const st = fs.statSync(abs);
    if (!st.isFile()) return null;
    if (st.size > 2_000_000) return { content: "", binary: true, size: st.size };
    const buf = fs.readFileSync(abs);
    for (let i = 0; i < Math.min(buf.length, 1024); i++) {
      if (buf[i] === 0) return { content: "", binary: true, size: st.size };
    }
    return { content: buf.toString("utf8"), binary: false, size: st.size };
  } catch { return null; }
}

export function tailLog(gruId: string, port: number, which: string, tail = 500): string | null {
  const g = getGru(gruId);
  if (!g) return null;
  const pdir = projectDirFor(g.rootPath, port);
  let abs: string | null = null;
  if (which === "backend") abs = path.join(pdir, "logs", "backend.log");
  else if (which === "gru") abs = gruLogPath(g.rootPath);
  else if (which.startsWith("role:")) {
    const role = which.slice(5).replace(/[^a-z0-9_-]/gi, "");
    abs = path.join(pdir, "logs", `role-${role}.log`);
  }
  if (!abs) return null;
  try {
    const raw = fs.readFileSync(abs, "utf8");
    const lines = raw.split("\n");
    return lines.slice(Math.max(0, lines.length - tail)).join("\n");
  } catch { return null; }
}

export function roleLogPath(gruId: string, port: number, role: string): string | null {
  const g = getGru(gruId);
  if (!g) return null;
  // Gru is not a project-local Role — it has one log per Gru installation
  // at <gruRoot>/minions/state/logs/gru.log. We treat "gru" as a virtual
  // role so the WebSocket tailer can stream it the same way it streams
  // role-{name}.log.
  if (role === "gru") {
    return gruLogPath(g.rootPath);
  }
  const clean = role.replace(/[^a-z0-9_-]/gi, "");
  if (!clean) return null;
  return path.join(projectDirFor(g.rootPath, port), "logs", `role-${clean}.log`);
}

export function listRoleSystemPrompts(gruId: string): { role: string; path: string; exists: boolean }[] {
  const g = getGru(gruId);
  if (!g) return [];
  const base = path.join(g.rootPath, "minions", "roles");
  return CANONICAL_ROLES.map((role) => {
    const p = path.join(base, role, "SYSTEM.md");
    return { role, path: p, exists: fs.existsSync(p) };
  });
}
