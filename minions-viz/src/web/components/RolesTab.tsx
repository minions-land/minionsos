import { useEffect, useState } from "react";
import type { MosProject, MosScratchpad, MosThresholdStatus } from "@shared/types";

interface Props { port: number; gruId: string; project: MosProject | null; }

function thresholdColor(s: MosThresholdStatus): string {
  if (s === "ok")   return "bg-emerald-500";
  if (s === "soft") return "bg-amber-500";
  if (s === "hard") return "bg-red-500";
  return "bg-neutral-900";
}

function thresholdLabel(s: MosThresholdStatus): string {
  if (s === "ok")   return "ok";
  if (s === "soft") return "soft limit";
  if (s === "hard") return "hard limit";
  return "veto";
}

function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function stateStyle(state: string): { background: string; color: string } {
  if (state === "active")    return { background: "var(--status-active)",    color: "#fff" };
  if (state === "sleeping")  return { background: "var(--status-unclaimed)", color: "#fff" };
  if (state === "dismissed") return { background: "#9ca3af",                 color: "#fff" };
  return { background: "var(--neutral-200)", color: "var(--muted)" };
}

export default function RolesTab({ port, gruId, project }: Props) {
  const [pads, setPads] = useState<MosScratchpad[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [padContent, setPadContent] = useState<string>("");
  const [logTail, setLogTail] = useState<string>("");

  useEffect(() => {
    let cancel = false;
    async function load() {
      try {
        const r = await fetch(`/api/mos/project/${port}/scratchpads?gru=${encodeURIComponent(gruId)}`);
        const j = (await r.json()) as MosScratchpad[];
        if (!cancel) setPads(j);
      } catch {}
    }
    load();
    const id = setInterval(load, 5_000);
    return () => { cancel = true; clearInterval(id); };
  }, [port, gruId]);

  useEffect(() => {
    if (!open) return;
    let cancel = false;
    async function load() {
      try {
        const [padRes, logRes] = await Promise.all([
          fetch(`/api/mos/project/${port}/scratchpad/${open}?gru=${encodeURIComponent(gruId)}`),
          fetch(`/api/mos/project/${port}/log?which=role:${open}&tail=200&gru=${encodeURIComponent(gruId)}`),
        ]);
        const pc = padRes.ok ? await padRes.text() : "(no scratchpad)";
        const lt = logRes.ok ? await logRes.text() : "(no log)";
        if (!cancel) { setPadContent(pc); setLogTail(lt); }
      } catch {}
    }
    load();
    const id = setInterval(load, 5_000);
    return () => { cancel = true; clearInterval(id); };
  }, [port, gruId, open]);

  const rolesByName = new Map((project?.active_roles ?? []).map((r) => [r.name, r]));

  const allRoles = new Map(rolesByName);
  for (const pad of pads) {
    if (!allRoles.has(pad.role) && pad.exists) {
      allRoles.set(pad.role, {
        name: pad.role,
        state: "active",
        pid: null,
        spawned_at: null,
        poll_interval: null,
      });
    }
  }

  return (
    <div className="absolute inset-0 overflow-auto p-6" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-6xl mx-auto">
        <h2 className="section-label mb-4">Roles</h2>

        {pads.length === 0 && (
          <div className="surface-card p-8">
            <div className="empty-state">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>No role scratchpads found. Roles appear here once they have been active.</span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {pads.map((pad) => {
            const role = allRoles.get(pad.role);
            const pct = Math.min(100, (pad.approx_tokens / 200_000) * 100);
            const ss = stateStyle(role?.state ?? "");
            return (
              <button
                key={pad.role}
                onClick={() => setOpen(pad.role)}
                aria-label={`View ${pad.role} role details`}
                className="surface-card text-left p-4 transition-all"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="font-semibold capitalize" style={{ color: "var(--text)" }}>{pad.role}</div>
                  <span
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded-full"
                    style={role?.state ? ss : { background: "rgba(156,163,175,0.15)", color: "var(--muted)" }}
                    title={role?.state ? undefined : "Role not currently registered on EACN3"}
                  >
                    {role?.state ?? <span className="opacity-70">inactive</span>}
                  </span>
                </div>

                <div className="text-[11px] space-y-0.5 mb-3" style={{ color: "var(--muted)" }}>
                  <div>PID: <span className="font-mono" style={{ color: "var(--text)" }}>{role?.pid ?? "—"}</span></div>
                  <div>Poll: <span className="font-mono" style={{ color: "var(--text)" }}>{role?.poll_interval ?? "—"}</span></div>
                  <div>Spawned: {role?.spawned_at ? new Date(role.spawned_at).toLocaleTimeString() : "—"}</div>
                </div>

                <div>
                  <div className="flex justify-between text-[10px] mb-1" style={{ color: "var(--muted)" }}>
                    <span>Scratchpad · {thresholdLabel(pad.threshold_status)}</span>
                    <span className="font-mono">{fmtTokens(pad.approx_tokens)} tok</span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--neutral-100)" }}>
                    <div
                      className={`h-full transition-all ${thresholdColor(pad.threshold_status)}`}
                      style={{ width: `${pct}%` }}
                      role="progressbar"
                      aria-valuenow={pct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`Scratchpad usage: ${pct.toFixed(0)}%`}
                    />
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Role detail drawer */}
        {open && (
          <div
            className="fixed inset-0 z-30 flex items-stretch justify-end"
            style={{ background: "rgba(0,0,0,0.3)" }}
            onClick={() => setOpen(null)}
          >
            <div
              className="w-full md:w-[640px] h-full overflow-auto animate-slide-in"
              style={{ background: "var(--surface)" }}
              onClick={(e) => e.stopPropagation()}
            >
              <div
                className="sticky top-0 border-b p-4 flex items-center justify-between z-10"
                style={{ background: "var(--surface-muted)", borderColor: "var(--line)" }}
              >
                <div>
                  <div className="section-label">Role</div>
                  <div className="font-semibold capitalize mt-0.5" style={{ color: "var(--text)" }}>{open}</div>
                </div>
                <button
                  onClick={() => setOpen(null)}
                  aria-label="Close role detail"
                  className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors hover:bg-[rgba(23,23,23,0.06)]"
                  style={{ color: "var(--muted)" }}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="p-4 space-y-4">
                <div>
                  <div className="section-label mb-2">Scratchpad (L2)</div>
                  <pre
                    className="text-[11px] font-mono rounded-lg p-3 whitespace-pre-wrap max-h-[40vh] overflow-auto"
                    style={{ background: "var(--neutral-100)", color: "var(--text)" }}
                  >
                    {padContent || "(empty)"}
                  </pre>
                </div>
                <div>
                  <div className="section-label mb-2">role-{open}.log (tail 200)</div>
                  <pre
                    className="text-[10px] font-mono rounded-lg p-3 whitespace-pre-wrap max-h-[40vh] overflow-auto"
                    style={{ background: "#1a1a2e", color: "#e2e8f0" }}
                  >
                    {logTail || "(no log)"}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
