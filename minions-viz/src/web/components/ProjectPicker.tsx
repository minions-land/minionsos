import { selectProject, selectGru } from "../hooks/useStore";
import type { GruInfo, MosProject } from "@shared/types";

interface Props { gru: GruInfo; }

function statusBadgeStyle(status: string): { background: string; color: string } {
  if (status === "active")  return { background: "var(--status-active)",    color: "#fff" };
  if (status === "dormant") return { background: "var(--status-unclaimed)",  color: "#fff" };
  return { background: "#9ca3af", color: "#fff" };
}

export default function ProjectPicker({ gru }: Props) {
  const projects = gru.projects;
  const active = projects.filter((p) => p.status !== "closed");
  const closed = projects.filter((p) => p.status === "closed");

  return (
    <div className="absolute inset-0 overflow-auto p-8" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-5xl mx-auto">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] text-indigo-600 tracking-[0.14em] uppercase">
              Gru · {gru.label}
            </div>
            <h1 className="text-2xl font-bold tracking-tight mt-0.5" style={{ color: "var(--text)" }}>Projects</h1>
            <p className="font-mono text-[11px] mt-1" style={{ color: "var(--muted)" }}>{gru.rootPath}</p>
          </div>
          <button
            onClick={() => selectGru(null)}
            className="text-xs px-3 py-1.5 rounded-full border transition-colors hover:border-indigo-400"
            style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--muted)" }}
          >
            ← Switch Gru
          </button>
        </div>

        {projects.length === 0 && (
          <div className="surface-card p-8 text-center">
            <div className="empty-state">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p style={{ color: "var(--muted)" }}>No projects in this Gru yet.</p>
            </div>
          </div>
        )}

        {active.length > 0 && (
          <>
            <h2 className="section-label mb-3">Active / Dormant</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              {active.map((p) => <ProjectCard key={p.port} p={p} />)}
            </div>
          </>
        )}

        {closed.length > 0 && (
          <>
            <h2 className="section-label mb-3">Closed</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 opacity-60">
              {closed.map((p) => <ProjectCard key={p.port} p={p} />)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ProjectCard({ p }: { p: MosProject }) {
  const badge = p.status === "active"
    ? { background: "var(--status-active)", color: "#fff" }
    : p.status === "dormant"
    ? { background: "var(--status-unclaimed)", color: "#fff" }
    : { background: "#9ca3af", color: "#fff" };

  return (
    <button
      onClick={() => selectProject(p.port)}
      className="surface-card text-left p-5 transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[11px]" style={{ color: "var(--muted)" }}>port {p.port}</div>
          <div className="text-base font-semibold truncate mt-0.5" style={{ color: "var(--text)" }}>{p.real_name}</div>
        </div>
        <span
          className="shrink-0 text-[10px] font-mono uppercase px-2 py-1 rounded-full"
          style={badge}
        >
          {p.status}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs" style={{ color: "var(--muted)" }}>
        <div>Venue: <span style={{ color: "var(--text)" }}>{p.venue ?? "—"}</span></div>
        <div>Roles: <span style={{ color: "var(--text)" }}>{p.active_roles.filter(r => r.state !== "dismissed").length}</span></div>
        <div>Branch: <span className="font-mono text-[10px]" style={{ color: "var(--text)" }}>{p.current_branch || "—"}</span></div>
        <div>Created: <span style={{ color: "var(--text)" }}>{new Date(p.created).toLocaleDateString()}</span></div>
      </div>
    </button>
  );
}
