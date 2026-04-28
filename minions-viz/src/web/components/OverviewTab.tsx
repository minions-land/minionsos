import { useEffect, useState } from "react";
import type { MosOverview } from "@shared/types";

interface Props { port: number; gruId: string; }

function renderMarkdown(md: string): string {
  const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = md.split("\n");
  const out: string[] = [];
  let inCode = false, inList = false;
  let buf: string[] = [];
  const flushPara = () => {
    if (buf.length) {
      out.push(`<p>${inlineFmt(escape(buf.join(" ")))}</p>`);
      buf = [];
    }
  };
  function inlineFmt(s: string): string {
    return s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }
  for (const ln of lines) {
    if (ln.startsWith("```")) {
      flushPara();
      if (inList) { out.push("</ul>"); inList = false; }
      if (!inCode) { out.push('<pre><code>'); inCode = true; }
      else { out.push("</code></pre>"); inCode = false; }
      continue;
    }
    if (inCode) { out.push(escape(ln) + "\n"); continue; }
    const h = ln.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara();
      if (inList) { out.push("</ul>"); inList = false; }
      const lvl = h[1].length;
      const sz = ["text-2xl","text-xl","text-lg","text-base","text-sm","text-xs"][lvl - 1];
      out.push(`<h${lvl} class="${sz} font-semibold mt-4 mb-2">${inlineFmt(escape(h[2]))}</h${lvl}>`);
      continue;
    }
    const li = ln.match(/^[-*]\s+(.*)$/);
    if (li) {
      flushPara();
      if (!inList) { out.push('<ul class="list-disc pl-6 space-y-1">'); inList = true; }
      out.push(`<li>${inlineFmt(escape(li[1]))}</li>`);
      continue;
    }
    if (ln.trim() === "") {
      flushPara();
      if (inList) { out.push("</ul>"); inList = false; }
      continue;
    }
    buf.push(ln);
  }
  flushPara();
  if (inList) out.push("</ul>");
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

export default function OverviewTab({ port, gruId }: Props) {
  const [data, setData] = useState<MosOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    async function load() {
      try {
        const r = await fetch(`/api/mos/project/${port}/overview?gru=${encodeURIComponent(gruId)}`);
        if (!r.ok) throw new Error(String(r.status));
        const j = (await r.json()) as MosOverview;
        if (!cancel) setData(j);
      } catch (e) { if (!cancel) setErr(String(e)); }
    }
    load();
    const id = setInterval(load, 10_000);
    return () => { cancel = true; clearInterval(id); };
  }, [port, gruId]);

  if (err) return (
    <div className="absolute inset-0 overflow-auto p-6" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-5xl mx-auto">
        <div className="surface-card p-5 border-l-4 border-red-500">
          <p className="text-sm text-red-600">Failed to load overview: {err}</p>
        </div>
      </div>
    </div>
  );

  if (!data) return (
    <div className="absolute inset-0 overflow-auto p-6" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-5xl mx-auto">
        <div className="surface-card p-8">
          <div className="empty-state">
            <svg className="w-8 h-8 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span style={{ color: "var(--muted)" }}>Loading overview…</span>
          </div>
        </div>
      </div>
    </div>
  );

  const p = data.project;
  return (
    <div className="absolute inset-0 overflow-auto p-6" style={{ background: "var(--bg-page)" }}>
      <div className="max-w-5xl mx-auto space-y-5">
        {/* Project header */}
        <div className="surface-card p-5">
          <div className="section-label mb-1">Project</div>
          <div className="text-xl font-bold" style={{ color: "var(--text)" }}>{p?.real_name ?? `project_${port}`}</div>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-3">
            <Field label="Port"            value={String(port)} mono />
            <Field label="Status"          value={p?.status ?? "—"} />
            <Field label="Venue"           value={p?.venue ?? "—"} />
            <Field label="Active Roles"    value={String(p?.active_roles.length ?? 0)} />
            <Field label="Upstream branch" value={p?.upstream_branch ?? "—"} mono />
            <Field label="Current branch"  value={p?.current_branch ?? "—"} mono />
            <Field label="Created"         value={p?.created ? new Date(p.created).toLocaleString() : "—"} />
            <Field label="Workspace"       value={data.workspace_dir} mono />
          </div>
        </div>

        {/* CLAUDE.md */}
        <div className="surface-card p-5">
          <div className="section-label mb-3">CLAUDE.md</div>
          {data.claude_md ? (
            <div
              className="prose-mos text-sm leading-relaxed"
              style={{ color: "var(--text)" }}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(data.claude_md) }}
            />
          ) : (
            <div className="empty-state py-6">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>No CLAUDE.md at {data.project_dir}/CLAUDE.md</span>
            </div>
          )}
        </div>

        {/* meta.json */}
        {data.meta && (
          <div className="surface-card p-5">
            <div className="section-label mb-3">meta.json</div>
            <pre
              className="text-[11px] font-mono rounded-lg p-3 overflow-x-auto"
              style={{ background: "var(--neutral-100)", color: "var(--text)" }}
            >
              {JSON.stringify(data.meta, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider mb-0.5" style={{ color: "var(--muted-2)" }}>{label}</div>
      <div
        className={mono ? "font-mono text-[11px] truncate" : "text-xs"}
        style={{ color: "var(--text)" }}
        title={mono ? value : undefined}
      >
        {value}
      </div>
    </div>
  );
}
