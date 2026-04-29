import { Router } from "express";
import { readFile, stat } from "fs/promises";
import { watch } from "fs";
import type { WebSocket } from "ws";
import { getGru, projectDirFor } from "./grus.js";

const router = Router();

router.get("/api/mos/project/:port/role-log/:role", async (req, res) => {
  const { port, role } = req.params;
  const gruId = req.query.gru as string;
  const tail = parseInt(req.query.tail as string) || 500;

  if (!gruId) return res.status(400).json({ error: "gru query param required" });

  const gru = getGru(gruId);
  if (!gru) return res.status(404).json({ error: "Gru not found" });

  const pdir = projectDirFor(gru.rootPath, Number(port));
  const logPath = `${pdir}/logs/role-${role}.log`;

  try {
    await stat(logPath);
  } catch {
    return res.status(404).json({ error: "Log file not found" });
  }

  try {
    const content = await readFile(logPath, "utf-8");
    const lines = content.split("\n");
    const tailLines = lines.slice(-tail).join("\n");
    res.type("text/plain").send(tailLines);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

export function setupRoleLogWatcher(wss: Set<WebSocket>, gruId: string, port: number, role: string) {
  const gru = getGru(gruId);
  if (!gru) return null;

  const pdir = projectDirFor(gru.rootPath, port);
  const logPath = `${pdir}/logs/role-${role}.log`;
  let lastSize = 0;

  try {
    const watcher = watch(logPath, async () => {
      try {
        const s = await stat(logPath);
        if (s.size > lastSize) {
          const content = await readFile(logPath, "utf-8");
          const newContent = content.slice(lastSize);
          lastSize = s.size;
          const msg = JSON.stringify({ type: "role-log", gruId, port, role, data: newContent });
          wss.forEach((ws) => { if (ws.readyState === 1) ws.send(msg); });
        }
      } catch {}
    });
    return watcher;
  } catch {
    return null;
  }
}

export default router;
