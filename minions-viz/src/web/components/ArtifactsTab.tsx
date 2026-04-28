import { useEffect, useState } from "react";
import type { MosArtifactNode } from "@shared/types";

interface Props { port: number; gruId: string; }

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function FileIcon() {
  return (
    <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function Node({ node, depth, onPick, selected }: {
  node: MosArtifactNode;
  depth: number;
  onPick: (n: MosArtifactNode) => void;
  selected: MosArtifactNode | null;
}) {
  const [open, setOpen] = useState(depth < 1);
  const pad = { paddingLeft: `${depth * 14 + 8}px` };

  if (node.kind === "dir") {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="w-full text-left py-1.5 pr-2 text-xs font-mono flex items-center gap-1.5 transition-colors hover:bg-indigo-50 rounded"
          style={{ ...pad, color: "var(--text)" }}
        >
          <svg
            className="w-3 h-3 shrink-0 transition-transform"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)", color: "var(--accent)" }}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span>{node.name}/</span>
          <span className="text-[10px] ml-auto pr-1" style={{ color: "var(--muted-2)" }}>{node.children?.length ?? 0}</span>
        </button>
        {open && node.children?.map((c) => (
          <Node key={c.path} node={c} depth={depth + 1} onPick={onPick} selected={selected} />
        ))}
      </div>
    );
  }

  const isSelected = selected?.path === node.path;
  return (
    <button
      onClick={() => onPick(node)}
      aria-current={isSelected ? "true" : undefined}
      className="w-full text-left py-1.5 pr-2 text-xs font-mono flex items-center gap-1.5 transition-colors rounded"
      style={{
        ...pad,
        color: isSelected ? "var(--accent)" : "var(--text)",
        background: isSelected ? "rgba(15,118,110,0.08)" : undefined,
      }}
      onMouseEnter={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = "rgba(79,70,229,0.05)"; }}
      onMouseLeave={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = ""; }}
    >
      <FileIcon />
      <span className="truncate flex-1">{node.name}</span>
      <span className="text-[10px] shrink-0" style={{ color: "var(--muted-2)" }}>{bytes(node.size)}</span>
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
      if (!r.ok) { if (!cancel) setPreview({ content: "(failed to load)", binary: false, size: 0 }); return; }
      const j = (await r.json()) as { content: string; binary: boolean; size: number };
      if (!cancel) setPreview(j);
    })();
    return () => { cancel = true; };
  }, [port, gruId, sel]);

  return (
    <div className="absolute inset-0 flex" style={{ background: "var(--bg-page)" }}>
      {/* File tree sidebar */}
      <aside
        className="w-72 shrink-0 border-r overflow-auto"
        style={{ borderColor: "var(--line)" }}
        aria-label="Artifact file tree"
      >
        <div className="sticky top-0 px-3 py-2.5 border-b" style={{ background: "var(--surface-muted)", borderColor: "var(--line)" }}>
          <h2 className="section-label">Artifacts</h2>
        </div>
        <div className="p-1">
          {!tree && (
            <div className="empty-state py-8">
              <svg className="w-6 h-6 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Loading…</span>
            </div>
          )}
          {tree && <Node node={tree} depth={0} onPick={setSel} selected={sel} />}
        </div>
      </aside>

      {/* Preview pane */}
      <main className="flex-1 overflow-auto p-5">
        {!sel && (
          <div className="h-full flex items-center justify-center">
            <div className="empty-state">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Select a file from the tree to preview its contents.</span>
            </div>
          </div>
        )}
        {sel && (
          <>
            <div className="mb-4">
              <div className="font-mono text-[11px]" style={{ color: "var(--muted)" }}>{sel.path}</div>
              <div className="font-semibold mt-0.5" style={{ color: "var(--text)" }}>{sel.name}</div>
            </div>
            {!preview && (
              <div className="empty-state py-8">
                <svg className="w-6 h-6 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>Loading…</span>
              </div>
            )}
            {preview?.binary && (
              <div className="surface-card p-4 text-sm" style={{ color: "var(--muted)" }}>
                Binary or oversized file — {bytes(preview.size)}
              </div>
            )}
            {preview && !preview.binary && (
              <pre
                className="text-[11px] font-mono rounded-lg p-4 border whitespace-pre-wrap"
                style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--text)" }}
              >
                {preview.content}
              </pre>
            )}
          </>
        )}
      </main>
    </div>
  );
}
