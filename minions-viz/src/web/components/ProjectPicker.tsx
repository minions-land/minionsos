import { selectProject, selectGru } from "../hooks/useStore";
import type { GruInfo, MosProject } from "@shared/types";

interface Props { gru: GruInfo; }

function statusColor(status: string) {
  if (status === "active") return "bg-indigo-600 text-white";
  if (status === "dormant") return "bg-amber-500 text-white";
  return "bg-neutral-400 text-white";
}

export default function ProjectPicker({ gru }: Props) {
  const projects = gru.projects;
  const active = projects.filter((p) => p.status !== "closed");
  const closed = projects.filter((p) => p.status === "closed");
  return (
    <div className="absolute inset-0 overflow-auto bg-[#fbf8f2] p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] text-indigo-600 tracking-[0.14em] uppercase">
              Gru · {gru.label}
            </div>
            <h1 className="text-2xl font-bold text-[#171717] tracking-tight">Projects</h1>
            <p className="text-sm text-[#5f5a52] mt-1 font-mono">{gru.rootPath}</p>
          </div>
          <button
            onClick={() => selectGru(null)}
            className="text-xs px-3 py-1.5 rounded-full bg-white border border-[rgba(23,23,23,0.1)] hover:border-indigo-400 text-[#5f5a52]"
          >
            ← Switch Gru
          </button>
        </div>

        {projects.length === 0 && (
          <div className="rounded-2xl border border-[rgba(23,23,23,0.1)] bg-white p-8 text-center text-[#5f5a52]">
            No projects in this Gru yet.
          </div>
        )}

        {active.length > 0 && (
          <>
            <h2 className="text-xs font-mono uppercase tracking-widest text-[#5f5a52] mb-3">Active / Dormant</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              {active.map((p) => <ProjectCard key={p.port} p={p} />)}
            </div>
          </>
        )}

        {closed.length > 0 && (
          <>
            <h2 className="text-xs font-mono uppercase tracking-widest text-[#5f5a52] mb-3">Closed</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 opacity-70">
              {closed.map((p) => <ProjectCard key={p.port} p={p} />)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ProjectCard({ p }: { p: MosProject }) {
  return (
    <button
      onClick={() => selectProject(p.port)}
      className="text-left rounded-2xl border border-[rgba(23,23,23,0.1)] bg-white hover:border-indigo-500 hover:shadow-lg transition-all p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[11px] text-[#5f5a52]">port {p.port}</div>
          <div className="text-base font-semibold text-[#171717] truncate">{p.real_name}</div>
        </div>
        <span className={`shrink-0 text-[10px] font-mono uppercase px-2 py-1 rounded-full ${statusColor(p.status)}`}>
          {p.status}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-[#5f5a52]">
        <div>Venue: <span className="text-[#171717]">{p.venue ?? "—"}</span></div>
        <div>Roles: <span className="text-[#171717]">{p.active_roles.filter(r => r.state !== "dismissed").length}</span></div>
        <div>Branch: <span className="font-mono text-[10px] text-[#171717]">{p.current_branch || "—"}</span></div>
        <div>Created: <span className="text-[#171717]">{new Date(p.created).toLocaleDateString()}</span></div>
      </div>
    </button>
  );
}
