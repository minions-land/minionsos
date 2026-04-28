import { useEffect, useState } from "react";
import type { MosProject, AgentInfo, Task } from "@shared/types";
import { timeAgo, shortId } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  port: number;
  gruId: string;
  project: MosProject | null;
}

interface RoleRow {
  role: string;
  state: string;
  pid: number | null;
  last_seen: string | null;
  buffered: number;
}

interface NoteFile {
  name: string;
  path: string;
  mtime: number;
}

export default function NoterView({ port, gruId, project }: Props) {
  const { locale } = useI18n();
  const [backendUp, setBackendUp] = useState(false);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [notes, setNotes] = useState<NoteFile[]>([]);

  useEffect(() => {
    let cancel = false;
    async function load() {
      try {
        const healthRes = await fetch(`http://127.0.0.1:${port}/health`);
        const health = healthRes.ok;
        setBackendUp(health);

        if (!health) return;

        const [agentsRes, tasksRes, artifactsRes] = await Promise.all([
          fetch(`http://127.0.0.1:${port}/api/discovery/agents?domain=minionsos`),
          fetch(`http://127.0.0.1:${port}/api/tasks?limit=50`),
          fetch(`/api/mos/project/${port}/artifacts?gru=${encodeURIComponent(gruId)}`),
        ]);

        const agents: AgentInfo[] = agentsRes.ok ? await agentsRes.json() : [];
        const taskList: Task[] = tasksRes.ok ? await tasksRes.json() : [];
        const artifacts = artifactsRes.ok ? await artifactsRes.json() : null;

        const roleRows: RoleRow[] = [];
        const rolesByName = new Map((project?.active_roles ?? []).map(r => [r.name, r]));

        for (const agent of agents) {
          const role = rolesByName.get(agent.agent_id);
          roleRows.push({
            role: agent.agent_id,
            state: role?.state ?? "active",
            pid: role?.pid ?? null,
            last_seen: agent.agent_id,
            buffered: 0,
          });
        }

        const notesDir = artifacts?.children?.find((c: any) => c.name === "notes");
        const noteFiles: NoteFile[] = (notesDir?.children ?? [])
          .filter((c: any) => c.kind === "file")
          .map((c: any) => ({ name: c.name, path: c.path, mtime: c.mtime }))
          .sort((a: NoteFile, b: NoteFile) => b.mtime - a.mtime);

        if (!cancel) {
          setRoles(roleRows);
          setTasks(taskList.slice(0, 12));
          setNotes(noteFiles.slice(0, 10));
        }
      } catch {}
    }
    load();
    const id = setInterval(load, 5_000);
    return () => { cancel = true; clearInterval(id); };
  }, [port, gruId, project]);

  return (
    <div className="absolute inset-0 overflow-auto p-6 bg-[#fbf8f2]">
      <div className="max-w-[1400px] mx-auto space-y-6">
        {/* Header */}
        <div className="panel-card p-4">
          <div className="flex items-center gap-4 text-sm">
            <span className="font-semibold text-[#171717]">{project?.real_name ?? "—"}</span>
            <span className="text-[#5f5a52]">Port: <span className="font-mono">{port}</span></span>
            <span className="text-[#5f5a52]">Status: <span className={project?.status === "active" ? "text-emerald-600" : "text-amber-600"}>{project?.status ?? "—"}</span></span>
            <span className="text-[#5f5a52]">Backend: <span className={backendUp ? "text-emerald-600" : "text-red-600"}>{backendUp ? "UP" : "DOWN"}</span></span>
            <span className="text-[#5f5a52]">Tasks: <span className="font-mono">{tasks.length}</span></span>
          </div>
        </div>

        {/* Roles Table */}
        <div className="panel-card p-5">
          <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">Roles</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[rgba(23,23,23,0.08)]">
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Role</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">State</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">PID</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Buffered</th>
                </tr>
              </thead>
              <tbody>
                {roles.map((r, i) => (
                  <tr key={i} className="border-b border-[rgba(23,23,23,0.04)] hover:bg-[rgba(23,23,23,0.02)]">
                    <td className="py-2 px-3 font-mono text-[#171717]">{r.role}</td>
                    <td className="py-2 px-3">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        r.state === "active" ? "bg-indigo-100 text-indigo-700" :
                        r.state === "sleeping" ? "bg-amber-100 text-amber-700" :
                        "bg-neutral-100 text-neutral-600"
                      }`}>{r.state}</span>
                    </td>
                    <td className="py-2 px-3 font-mono text-[#5f5a52]">{r.pid ?? "—"}</td>
                    <td className="py-2 px-3 font-mono text-[#5f5a52]">{r.buffered}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Tasks Table */}
        <div className="panel-card p-5">
          <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">Recent EACN Tasks</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[rgba(23,23,23,0.08)]">
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Task</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Status</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Initiator</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Domains</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t, i) => (
                  <tr key={i} className="border-b border-[rgba(23,23,23,0.04)] hover:bg-[rgba(23,23,23,0.02)]">
                    <td className="py-2 px-3 font-mono text-[#5f5a52]">{shortId(t.id)}</td>
                    <td className="py-2 px-3">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        t.status === "completed" ? "bg-emerald-100 text-emerald-700" :
                        t.status === "bidding" ? "bg-blue-100 text-blue-700" :
                        t.status === "unclaimed" ? "bg-amber-100 text-amber-700" :
                        "bg-neutral-100 text-neutral-600"
                      }`}>{t.status}</span>
                    </td>
                    <td className="py-2 px-3 font-mono text-[#5f5a52]">{t.initiator_id}</td>
                    <td className="py-2 px-3 text-[#5f5a52]">{t.domains.slice(0, 2).join(", ")}</td>
                    <td className="py-2 px-3 text-[#5f5a52] truncate max-w-xs">{(t.content.description as string || "—").slice(0, 60)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Notes Table */}
        <div className="panel-card p-5">
          <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">Latest Notes</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[rgba(23,23,23,0.08)]">
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Note</th>
                  <th className="text-left py-2 px-3 text-[#5f5a52] font-medium">Modified</th>
                </tr>
              </thead>
              <tbody>
                {notes.map((n, i) => (
                  <tr key={i} className="border-b border-[rgba(23,23,23,0.04)] hover:bg-[rgba(23,23,23,0.02)]">
                    <td className="py-2 px-3 font-mono text-[#171717]">{n.name}</td>
                    <td className="py-2 px-3 text-[#5f5a52]">{timeAgo(new Date(n.mtime).toISOString(), locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
