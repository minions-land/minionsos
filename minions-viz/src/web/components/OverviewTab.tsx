import { useEffect, useState } from "react";
import type { MosOverview } from "@shared/types";

interface Props { port: number; gruId: string; }

function renderMarkdown(md: string): string {
  // Tiny, safe-ish markdown renderer (headings, bold, italic, inline code,
  // fences, lists, paragraphs). Not production grade but adequate for CLAUDE.md.
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
      .replace(/`([^`]+)`/g, '<code class="font-mono text-[12px] bg-neutral-100 px-1 py-0.5 rounded">$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }
  for (const ln of lines) {
    if (ln.startsWith("```")) {
      flushPara();
      if (inList) { out.push("</ul>"); inList = false; }
      if (!inCode) { out.push('<pre class="bg-neutral-900 text-neutral-100 text-xs rounded-lg p-3 overflow-x-auto"><code>'); inCode = true; }
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

  if (err) return <div className="p-6 text-sm text-red-600">Failed to load overview: {err}</div>;
  if (!data) return <div className="p-6 text-sm text-[#5f5a52]">Loading…</div>;

  const p = data.project;
  return (
    <div className="absolute inset-0 overflow-auto p-6 bg-[#fbf8f2]">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="rounded-2xl border border-[rgba(23,23,23,0.08)] bg-white p-5">
          <div className="font-mono text-[10px] uppercase tracking-widest text-indigo-600">Project</div>
          <div className="text-xl font-bold text-[#171717]">{p?.real_name ?? `project_${port}`}</div>
          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-xs text-[#5f5a52]">
            <Field label="Port" value={String(port)} mono />
            <Field label="Status" value={p?.status ?? "—"} />
            <Field label="Venue" value={p?.venue ?? "—"} />
            <Field label="Roles" value={String(p?.active_roles.length ?? 0)} />
            <Field label="Upstream branch" value={p?.upstream_branch ?? "—"} mono />
            <Field label="Current branch" value={p?.current_branch ?? "—"} mono />
            <Field label="Created" value={p?.created ? new Date(p.created).toLocaleString() : "—"} />
            <Field label="Workspace" value={data.workspace_dir} mono />
          </div>
        </div>

        <div className="rounded-2xl border border-[rgba(23,23,23,0.08)] bg-white p-5">
          <div className="font-mono text-[10px] uppercase tracking-widest text-indigo-600 mb-3">CLAUDE.md</div>
          {data.claude_md ? (
            <div className="prose-mos text-sm text-[#171717] leading-relaxed"
                 dangerouslySetInnerHTML={{ __html: renderMarkdown(data.claude_md) }} />
          ) : (
            <div className="text-xs text-[#5f5a52]">No CLAUDE.md at {data.project_dir}/CLAUDE.md</div>
          )}
        </div>

        {data.meta && (
          <div className="rounded-2xl border border-[rgba(23,23,23,0.08)] bg-white p-5">
            <div className="font-mono text-[10px] uppercase tracking-widest text-indigo-600 mb-3">meta.json</div>
            <pre className="text-[11px] font-mono bg-neutral-50 rounded-lg p-3 overflow-x-auto">
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
      <div className="text-[10px] uppercase tracking-wider text-[#5f5a52]/70">{label}</div>
      <div className={`text-[#171717] ${mono ? "font-mono text-[11px] truncate" : "text-xs"}`}>{value}</div>
    </div>
  );
}
