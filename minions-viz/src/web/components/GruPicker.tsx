import { selectGru } from "../hooks/useStore";
import type { GruInfo } from "@shared/types";

interface Props { grus: GruInfo[]; }

function freshness(lastSeen: string | null): { label: string; color: string } {
  if (!lastSeen) return { label: "never", color: "bg-neutral-400" };
  const age = Date.now() - new Date(lastSeen).getTime();
  if (age <= 30_000) return { label: "live", color: "bg-emerald-500" };
  if (age <= 120_000) return { label: "recent", color: "bg-amber-500" };
  return { label: "stale", color: "bg-red-400" };
}

export default function GruPicker({ grus }: Props) {
  return (
    <div className="absolute inset-0 overflow-auto bg-[#fbf8f2] p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-8">
          <div className="font-mono text-[10px] text-indigo-600 tracking-[0.14em] uppercase">MinionsOS</div>
          <h1 className="text-2xl font-bold text-[#171717] tracking-tight">Gru Installations</h1>
          <p className="text-sm text-[#5f5a52] mt-1">
            Each Gru is one MinionsOS checkout on this host. Pick one to view its projects.
          </p>
        </div>

        {grus.length === 0 && (
          <div className="rounded-2xl border border-[rgba(23,23,23,0.1)] bg-white p-8 text-center text-[#5f5a52]">
            No Grus registered. Run <code className="font-mono text-xs bg-neutral-100 px-1.5 py-0.5 rounded">./gru</code> in any
            MinionsOS checkout to register it.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {grus.map((g) => {
            const active = g.projects.filter((p) => p.status === "active").length;
            const dormant = g.projects.filter((p) => p.status === "dormant").length;
            const closed = g.projects.filter((p) => p.status === "closed").length;
            const f = freshness(g.lastSeen);
            return (
              <button
                key={g.id}
                onClick={() => selectGru(g.id)}
                className="text-left rounded-2xl border border-[rgba(23,23,23,0.1)] bg-white hover:border-indigo-500 hover:shadow-lg transition-all p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-[11px] text-[#5f5a52]">gru · {g.id}</div>
                    <div className="text-base font-semibold text-[#171717] truncate">{g.label}</div>
                  </div>
                  <span className={`shrink-0 inline-flex items-center gap-1.5 text-[10px] font-mono uppercase px-2 py-1 rounded-full bg-white border border-[rgba(23,23,23,0.1)] text-[#5f5a52]`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${f.color}`} />
                    {f.label}
                  </span>
                </div>
                <div className="font-mono text-[10px] text-[#5f5a52]/80 truncate mt-1">{g.rootPath}</div>
                <div className="mt-3 grid grid-cols-3 gap-x-3 text-xs text-[#5f5a52]">
                  <div>Active: <span className="text-[#171717] font-semibold">{active}</span></div>
                  <div>Dormant: <span className="text-[#171717] font-semibold">{dormant}</span></div>
                  <div>Closed: <span className="text-[#171717] font-semibold">{closed}</span></div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
