import { useEffect, useState } from "react";
import type { MosProject, AgentInfo, Task } from "@shared/types";
import { timeAgo, shortId } from "../utils/format";
import { useI18n } from "../i18n";
import { useLimitPref } from "../hooks/useLimitPref";
import { useStore } from "../hooks/useStore";

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

const TASK_LIMIT_OPTIONS = [10, 20, 50];
const NOTE_LIMIT_OPTIONS = [10, 20, 50];

function stateStyle(state: string): { background: string; color: string } {
  if (state === "active")    return { background: "rgba(79,70,229,0.12)",  color: "var(--status-active)" };
  if (state === "sleeping")  return { background: "rgba(217,119,6,0.12)",  color: "var(--status-unclaimed)" };
  return { background: "rgba(156,163,175,0.15)", color: "var(--muted)" };
}

export default function NoterView({ port, gruId, project }: Props) {
  const { locale } = useI18n();
  const store = useStore();
  const backendUp = store.connected;
  const agents: AgentInfo[] = store.agents;
  const tasks: Task[] = store.tasks;
  const [notes, setNotes] = useState<NoteFile[]>([]);
  const [taskLimit, setTaskLimit] = useLimitPref("viz.limit.noter.tasks", 20, TASK_LIMIT_OPTIONS);
  const [noteLimit, setNoteLimit] = useLimitPref("viz.limit.noter.notes", 10, NOTE_LIMIT_OPTIONS);

  // Derive role rows from store agents + project active_roles
  const rolesByName = new Map((project?.active_roles ?? []).map(r => [r.name, r]));
  const roles: RoleRow[] = agents.map((agent) => {
    const role = rolesByName.get(agent.agent_id);
    return {
      role: agent.agent_id,
      state: role?.state ?? "active",
      pid: role?.pid ?? null,
      last_seen: agent.agent_id,
      buffered: 0,
    };
  });

  // Newest-first tasks (store tasks are in insertion order)
  const sortedTasks = [...tasks].reverse();

  // Fetch filesystem artifacts (notes) via proxied viz endpoint — no CORS issue
  useEffect(() => {
    let cancel = false;
    async function load() {
      try {
        const artifactsRes = await fetch(`/api/mos/project/${port}/artifacts?gru=${encodeURIComponent(gruId)}`);
        const artifacts = artifactsRes.ok ? await artifactsRes.json() : null;
        const notesDir = artifacts?.children?.find((c: any) => c.name === "notes");
        const noteFiles: NoteFile[] = (notesDir?.children ?? [])
          .filter((c: any) => c.kind === "file")
          .map((c: any) => ({ name: c.name, path: c.path, mtime: c.mtime }))
          .sort((a: NoteFile, b: NoteFile) => b.mtime - a.mtime);
        if (!cancel) setNotes(noteFiles);
      } catch {}
    }
    load();
    const id = setInterval(load, 5_000);
    return () => { cancel = true; clearInterval(id); };
  }, [port, gruId]);

  const statusStyle = (s: string) => {
    if (s === "completed") return { background: "rgba(5,150,105,0.12)",  color: "var(--status-completed)" };
    if (s === "bidding")   return { background: "rgba(37,99,235,0.12)",  color: "var(--status-bidding)" };
    if (s === "unclaimed") return { background: "rgba(217,119,6,0.12)",  color: "var(--status-unclaimed)" };
    return { background: "rgba(156,163,175,0.15)", color: "var(--muted)" };
  };

  return (
    <div className="absolute inset-0 overflow-auto p-6" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-[1400px] mx-auto space-y-5">
        {/* Header */}
        <div className="panel-card p-4">
          <div className="flex items-center gap-4 flex-wrap text-sm">
            <span className="font-semibold" style={{ color: "var(--text)" }}>{project?.real_name ?? "—"}</span>
            <span style={{ color: "var(--muted)" }}>Port: <span className="font-mono">{port}</span></span>
            <span style={{ color: "var(--muted)" }}>
              Status:{" "}
              <span style={{ color: project?.status === "active" ? "var(--status-completed)" : "var(--status-unclaimed)" }}>
                {project?.status ?? "—"}
              </span>
            </span>
            <span style={{ color: "var(--muted)" }}>
              Backend:{" "}
              <span style={{ color: backendUp ? "var(--status-completed)" : "var(--status-error)" }}>
                {backendUp ? "UP" : "DOWN"}
              </span>
            </span>
            <span style={{ color: "var(--muted)" }}>Tasks: <span className="font-mono">{tasks.length}</span></span>
          </div>
        </div>

        {/* Roles Table */}
        <div className="panel-card">
          <div className="toolbar">
            <h3 className="section-label flex-1">Roles</h3>
            <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{roles.length} registered</span>
          </div>
          {roles.length === 0 ? (
            <div className="empty-state py-8">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>{backendUp ? "No roles registered on EACN3." : "Backend is down — role data unavailable."}</span>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>State</th>
                    <th>PID</th>
                    <th>Buffered</th>
                  </tr>
                </thead>
                <tbody>
                  {roles.map((r, i) => (
                    <tr key={i}>
                      <td className="font-mono" style={{ color: "var(--text)" }}>{r.role}</td>
                      <td>
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-full font-mono"
                          style={stateStyle(r.state)}
                        >
                          {r.state}
                        </span>
                      </td>
                      <td className="font-mono" style={{ color: "var(--muted)" }}>{r.pid ?? "—"}</td>
                      <td className="font-mono" style={{ color: "var(--muted)" }}>{r.buffered}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Tasks Table — newest first */}
        <div className="panel-card">
          <div className="toolbar">
            <h3 className="section-label flex-1">Recent EACN Tasks</h3>
            <label className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--muted)" }}>
              Show
              <select value={taskLimit} onChange={(e) => setTaskLimit(Number(e.target.value))} className="limit-select">
                {TASK_LIMIT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </label>
          </div>
          {tasks.length === 0 ? (
            <div className="empty-state py-8">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <span>{backendUp ? "No tasks found." : "Backend is down — task data unavailable."}</span>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className="w-24">Task</th>
                    <th className="w-28">Status</th>
                    <th className="w-32">Initiator</th>
                    <th className="w-32">Domains</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedTasks.slice(0, taskLimit).map((t, i) => (
                    <tr key={i}>
                      <td className="font-mono" style={{ color: "var(--muted)" }}>{shortId(t.id)}</td>
                      <td>
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-full font-mono"
                          style={statusStyle(t.status)}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{shortId(t.initiator_id)}</td>
                      <td style={{ color: "var(--muted)" }}>{t.domains.slice(0, 2).join(", ") || "—"}</td>
                      <td className="truncate max-w-xs" style={{ color: "var(--muted)" }}>
                        {(t.content.description as string || "—").slice(0, 80)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Notes Table — newest first */}
        <div className="panel-card">
          <div className="toolbar">
            <h3 className="section-label flex-1">Latest Notes</h3>
            <label className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--muted)" }}>
              Show
              <select value={noteLimit} onChange={(e) => setNoteLimit(Number(e.target.value))} className="limit-select">
                {NOTE_LIMIT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </label>
          </div>
          {notes.length === 0 ? (
            <div className="empty-state py-8">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              <span>No notes found in artifacts/notes/.</span>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Note</th>
                    <th className="w-32">Modified</th>
                  </tr>
                </thead>
                <tbody>
                  {notes.slice(0, noteLimit).map((n, i) => (
                    <tr key={i}>
                      <td className="font-mono" style={{ color: "var(--text)" }}>{n.name}</td>
                      <td style={{ color: "var(--muted)" }}>{timeAgo(new Date(n.mtime).toISOString(), locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
