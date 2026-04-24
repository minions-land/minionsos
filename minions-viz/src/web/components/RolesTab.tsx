import { useEffect, useState } from "react";
import type { MosProject, MosScratchpad, MosThresholdStatus } from "@shared/types";

interface Props { port: number; gruId: string; project: MosProject | null; }

function thresholdColor(s: MosThresholdStatus): string {
  if (s === "ok") return "bg-emerald-500";
  if (s === "soft") return "bg-amber-500";
  if (s === "hard") return "bg-red-500";
  return "bg-black";
}

function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
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

  return (
    <div className="absolute inset-0 overflow-auto p-6 bg-[#fbf8f2]">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-sm font-mono uppercase tracking-widest text-indigo-600 mb-3">Roles</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {pads.map((pad) => {
            const role = rolesByName.get(pad.role);
            const pct = Math.min(100, (pad.approx_tokens / 200_000) * 100);
            return (
              <button
                key={pad.role}
                onClick={() => setOpen(pad.role)}
                className="text-left rounded-2xl border border-[rgba(23,23,23,0.08)] bg-white p-4 hover:border-indigo-400 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-[#171717] capitalize">{pad.role}</div>
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-full text-white ${
                    role?.state === "active" ? "bg-indigo-600" :
                    role?.state === "sleeping" ? "bg-amber-500" :
                    role?.state === "dismissed" ? "bg-neutral-400" : "bg-neutral-300"
                  }`}>
                    {role?.state ?? "—"}
                  </span>
                </div>
                <div className="mt-2 text-[11px] text-[#5f5a52] space-y-0.5">
                  <div>PID: <span className="font-mono text-[#171717]">{role?.pid ?? "—"}</span></div>
                  <div>Poll: <span className="font-mono text-[#171717]">{role?.poll_interval ?? "—"}</span></div>
                  <div>Spawned: {role?.spawned_at ? new Date(role.spawned_at).toLocaleTimeString() : "—"}</div>
                </div>
                <div className="mt-3">
                  <div className="flex justify-between text-[10px] text-[#5f5a52] mb-1">
                    <span>Scratchpad</span>
                    <span className="font-mono">{fmtTokens(pad.approx_tokens)} tok</span>
                  </div>
                  <div className="h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                    <div className={`h-full ${thresholdColor(pad.threshold_status)}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {open && (
          <div className="fixed inset-0 z-30 bg-black/30 flex items-stretch justify-end" onClick={() => setOpen(null)}>
            <div className="w-full md:w-[640px] bg-white h-full overflow-auto" onClick={(e) => e.stopPropagation()}>
              <div className="sticky top-0 bg-white border-b border-[rgba(23,23,23,0.08)] p-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-mono uppercase text-indigo-600">Role</div>
                  <div className="font-semibold capitalize">{open}</div>
                </div>
                <button onClick={() => setOpen(null)} className="text-[#5f5a52] hover:text-black text-sm">✕</button>
              </div>
              <div className="p-4 space-y-4">
                <div>
                  <div className="text-xs font-mono uppercase text-[#5f5a52] mb-2">Scratchpad (L2)</div>
                  <pre className="text-[11px] font-mono bg-neutral-50 rounded-lg p-3 whitespace-pre-wrap max-h-[40vh] overflow-auto">{padContent}</pre>
                </div>
                <div>
                  <div className="text-xs font-mono uppercase text-[#5f5a52] mb-2">role-{open}.log (tail 200)</div>
                  <pre className="text-[10px] font-mono bg-neutral-900 text-neutral-100 rounded-lg p-3 whitespace-pre-wrap max-h-[40vh] overflow-auto">{logTail}</pre>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
