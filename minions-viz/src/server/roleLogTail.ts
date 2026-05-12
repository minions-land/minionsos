/**
 * Per-(gruId, port, role) role-log tailer. Each active viewer gets a tailer
 * that polls the file every 500ms and broadcasts only the newly-appended
 * bytes over WS. A tailer is reference-counted; dropped when no viewers remain.
 */
import fs from "fs";
import { roleLogPath } from "./mosFs.js";
import { broadcastRoleLog } from "./state.js";

interface Tailer {
  gruId: string;
  port: number;
  role: string;
  absPath: string;
  inode: number | null;
  pos: number;
  viewers: number;
  timer: NodeJS.Timeout;
}

const tailers = new Map<string, Tailer>();
const POLL_MS = 500;

function key(gruId: string, port: number, role: string) {
  return `${gruId}::${port}::${role}`;
}

function tickTailer(t: Tailer) {
  fs.stat(t.absPath, (err, st) => {
    if (err) return;
    // If inode changed (log rotated), rewind pos.
    if (t.inode != null && (st as unknown as { ino: number }).ino !== t.inode) {
      t.pos = 0;
    }
    t.inode = (st as unknown as { ino: number }).ino;
    if (st.size < t.pos) t.pos = 0; // truncated
    if (st.size === t.pos) return;
    const start = t.pos;
    const stream = fs.createReadStream(t.absPath, {
      start,
      end: st.size - 1,
      encoding: "utf8",
    });
    let chunk = "";
    stream.on("data", (buf: string | Buffer) => {
      chunk += typeof buf === "string" ? buf : buf.toString("utf8");
    });
    stream.on("end", () => {
      t.pos = st.size;
      if (chunk.length > 0) {
        broadcastRoleLog(t.gruId, t.port, t.role, chunk);
      }
    });
    stream.on("error", () => {});
  });
}

export function addRoleLogViewer(gruId: string, port: number, role: string) {
  const k = key(gruId, port, role);
  const existing = tailers.get(k);
  if (existing) {
    existing.viewers += 1;
    return;
  }
  const abs = roleLogPath(gruId, port, role);
  if (!abs) return;
  let initialPos = 0;
  try {
    initialPos = fs.statSync(abs).size;
  } catch {
    // file not present yet; start from 0 so when it appears we emit from top
  }
  const t: Tailer = {
    gruId,
    port,
    role,
    absPath: abs,
    inode: null,
    pos: initialPos,
    viewers: 1,
    timer: setInterval(() => tickTailer(t), POLL_MS),
  };
  tailers.set(k, t);
}

export function removeRoleLogViewer(
  gruId: string,
  port: number,
  role: string,
) {
  const k = key(gruId, port, role);
  const t = tailers.get(k);
  if (!t) return;
  t.viewers -= 1;
  if (t.viewers <= 0) {
    clearInterval(t.timer);
    tailers.delete(k);
  }
}

export function dropAllViewersFor(gruId: string | null, port: number | null) {
  // Drop viewers tied to a given pair. Used when a client switches selection.
  for (const [k, t] of tailers) {
    if (
      (gruId == null || t.gruId === gruId) &&
      (port == null || t.port === port)
    ) {
      t.viewers = 0;
      clearInterval(t.timer);
      tailers.delete(k);
    }
  }
}
