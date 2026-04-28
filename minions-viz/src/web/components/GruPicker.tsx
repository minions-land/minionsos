import { selectGru } from "../hooks/useStore";
import type { GruInfo } from "@shared/types";

interface Props { grus: GruInfo[]; }

function freshness(lastSeen: string | null): { label: string; dotClass: string; isLive: boolean } {
  if (!lastSeen) return { label: "never", dotClass: "bg-neutral-400", isLive: false };
  const age = Date.now() - new Date(lastSeen).getTime();
  if (age <= 30_000)  return { label: "live",   dotClass: "bg-emerald-500", isLive: true };
  if (age <= 120_000) return { label: "recent", dotClass: "bg-amber-500",   isLive: false };
  return { label: "stale", dotClass: "bg-red-400", isLive: false };
}

export default function GruPicker({ grus }: Props) {
  // Sort: live first, then recent, then stale/never
  const sorted = [...grus].sort((a, b) => {
    const order = (g: GruInfo) => {
      const f = freshness(g.lastSeen);
      if (f.label === "live")   return 0;
      if (f.label === "recent") return 1;
      if (f.label === "stale")  return 2;
      return 3;
    };
    return order(a) - order(b);
  });

  return (
    <div className="absolute inset-0 overflow-auto p-8" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-5xl mx-auto">
        <div className="mb-8">
          <div className="font-mono text-[10px] text-indigo-600 tracking-[0.14em] uppercase mb-1">MinionsOS</div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>Gru Installations</h1>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
            Each Gru is one MinionsOS checkout on this host. Pick one to view its projects.
          </p>
        </div>

        {grus.length === 0 && (
          <div className="surface-card p-8 text-center">
            <div className="empty-state">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
              </svg>
              <p style={{ color: "var(--muted)" }}>
                No Grus registered yet.{" "}
                Run <code className="font-mono text-xs bg-neutral-100 px-1.5 py-0.5 rounded">./gru</code> in any
                MinionsOS checkout to register it.
              </p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sorted.map((g) => {
            const active  = g.projects.filter((p) => p.status === "active").length;
            const dormant = g.projects.filter((p) => p.status === "dormant").length;
            const closed  = g.projects.filter((p) => p.status === "closed").length;
            const f = freshness(g.lastSeen);
            return (
              <button
                key={g.id}
                onClick={() => selectGru(g.id)}
                className={`surface-card text-left p-5 transition-all ${f.isLive ? "ring-2 ring-indigo-500 ring-offset-1" : "opacity-60 hover:opacity-80"}`}
                style={{ cursor: "pointer" }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-[11px]" style={{ color: "var(--muted)" }}>gru · {g.id}</div>
                    <div className={`text-base font-semibold truncate mt-0.5 ${f.isLive ? "" : "opacity-70"}`} style={{ color: "var(--text)" }}>{g.label}</div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {f.isLive && (
                      <span className="text-[9px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded bg-indigo-600 text-white">
                        LIVE
                      </span>
                    )}
                    <span
                      className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase px-2 py-1 rounded-full border"
                      style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--muted)" }}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${f.dotClass}`} />
                      {f.label}
                    </span>
                  </div>
                </div>
                <div className="font-mono text-[10px] truncate mt-1" style={{ color: "var(--muted-2)" }}>{g.rootPath}</div>
                <div className="mt-3 grid grid-cols-3 gap-x-3 text-xs" style={{ color: "var(--muted)" }}>
                  <div>Active: <span className="font-semibold" style={{ color: "var(--text)" }}>{active}</span></div>
                  <div>Dormant: <span className="font-semibold" style={{ color: "var(--text)" }}>{dormant}</span></div>
                  <div>Closed: <span className="font-semibold" style={{ color: "var(--text)" }}>{closed}</span></div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
