import { useEffect, useState } from "react";
import type { MosArtifactNode } from "@shared/types";

interface Props { port: number; gruId: string; }

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function Node({ node, depth, onPick }: { node: MosArtifactNode; depth: number; onPick: (n: MosArtifactNode) => void }) {
  const [open, setOpen] = useState(depth < 1);
  const pad = { paddingLeft: `${depth * 14}px` };
  if (node.kind === "dir") {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className="w-full text-left py-1 hover:bg-indigo-50 text-xs font-mono flex items-center gap-1"
          style={pad}
        >
          <span className="text-indigo-600">{open ? "▾" : "▸"}</span>
          <span className="text-[#171717]">{node.name}/</span>
          <span className="text-[10px] text-[#5f5a52]/60 ml-auto pr-2">{node.children?.length ?? 0}</span>
        </button>
        {open && node.children?.map((c) => (
          <Node key={c.path} node={c} depth={depth + 1} onPick={onPick} />
        ))}
      </div>
    );
  }
  return (
    <button
      onClick={() => onPick(node)}
      className="w-full text-left py-1 hover:bg-indigo-50 text-xs font-mono flex items-center gap-2"
      style={pad}
    >
      <span className="text-[#5f5a52]">·</span>
      <span className="text-[#171717] truncate">{node.name}</span>
      <span className="text-[10px] text-[#5f5a52]/60 ml-auto pr-2">{bytes(node.size)}</span>
    </button>
  );
}

export default function ArtifactsTab({ port, gruId }: Props) {
  const [tree, setTree] = useState<MosArtifactNode | null>(null);
  const [sel, setSel] = useState<MosArtifactNode | null>(null);
  const [preview, setPreview] = useState<{ content: string; binary: boolean; size: number } | null>(null);

  useEffect(() => {
    let cancel = false;
    async function load() {
      try {
        const r = await fetch(`/api/mos/project/${port}/artifacts?gru=${encodeURIComponent(gruId)}`);
        const j = (await r.json()) as MosArtifactNode;
        if (!cancel) setTree(j);
      } catch {}
    }
    load();
    const id = setInterval(load, 10_000);
    return () => { cancel = true; clearInterval(id); };
  }, [port, gruId]);

  useEffect(() => {
    if (!sel) { setPreview(null); return; }
    let cancel = false;
    (async () => {
      const r = await fetch(`/api/mos/project/${port}/artifact?path=${encodeURIComponent(sel.path)}&gru=${encodeURIComponent(gruId)}`);
      if (!r.ok) { if (!cancel) setPreview({ content: "(failed)", binary: false, size: 0 }); return; }
      const j = (await r.json()) as { content: string; binary: boolean; size: number };
      if (!cancel) setPreview(j);
    })();
    return () => { cancel = true; };
  }, [port, gruId, sel]);

  return (
    <div className="absolute inset-0 flex bg-[#fbf8f2]">
      <aside className="w-80 shrink-0 border-r border-[rgba(23,23,23,0.08)] overflow-auto p-2">
        <h2 className="text-[10px] font-mono uppercase tracking-widest text-indigo-600 p-2">Artifacts</h2>
        {tree ? <Node node={tree} depth={0} onPick={setSel} /> : <div className="text-xs text-[#5f5a52] p-2">Loading…</div>}
      </aside>
      <main className="flex-1 overflow-auto p-5">
        {!sel && <div className="text-sm text-[#5f5a52]">Pick a file to preview.</div>}
        {sel && (
          <>
            <div className="mb-3">
              <div className="font-mono text-[11px] text-[#5f5a52]">{sel.path}</div>
              <div className="font-semibold text-[#171717]">{sel.name}</div>
            </div>
            {!preview && <div className="text-xs text-[#5f5a52]">Loading…</div>}
            {preview?.binary && (
              <div className="text-xs text-[#5f5a52]">Binary or oversized file — {bytes(preview.size)}</div>
            )}
            {preview && !preview.binary && (
              <pre className="text-[11px] font-mono bg-white rounded-lg p-3 border border-[rgba(23,23,23,0.06)] whitespace-pre-wrap">{preview.content}</pre>
            )}
          </>
        )}
      </main>
    </div>
  );
}
