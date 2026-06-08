import { useEffect, useState, useMemo } from "react";
import { useStore } from "./store";

interface LibraryEntry {
  title: string;
  path: string;
  kind: string;
  content: string;
  updated_at?: string;
}

export function LibraryView() {
  const store = useStore();
  const gruId = store.selectedGruId;
  const port = store.selectedPort;
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<LibraryEntry | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeKind, setActiveKind] = useState<string>("all");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!gruId || port == null) return;
    setLoading(true);
    let cancelled = false;
    const fetchBook = () => {
      fetch(`/api/mos/project/${port}/book?gru=${gruId}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (cancelled) return;
          const raw = data && Array.isArray(data.entries) ? data.entries : [];
          const safe: LibraryEntry[] = raw
            .filter((e: unknown): e is Record<string, unknown> => !!e && typeof e === "object")
            .map((e: Record<string, unknown>) => ({
              title: typeof e.title === "string" ? e.title : "(untitled)",
              path: typeof e.path === "string" ? e.path : "",
              kind: typeof e.kind === "string" ? e.kind : "root",
              content: typeof e.content === "string" ? e.content : "",
              updated_at:
                typeof e.updated_at === "string"
                  ? e.updated_at
                  : typeof e.updated_at === "number"
                    ? new Date(e.updated_at).toISOString()
                    : undefined,
            }));
          setEntries(safe);
          setLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setEntries([]);
          setLoading(false);
        });
    };
    fetchBook();
    const interval = setInterval(fetchBook, 8000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [gruId, port]);

  const kinds = useMemo(() => {
    const set = new Set<string>();
    for (const e of entries) set.add(e.kind);
    return ["all", ...Array.from(set).sort()];
  }, [entries]);

  const filteredEntries = useMemo(() => {
    let result = entries;
    if (activeKind !== "all") {
      result = result.filter((e) => e.kind === activeKind);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (e) =>
          e.title.toLowerCase().includes(q) ||
          e.content.toLowerCase().includes(q) ||
          e.path.toLowerCase().includes(q),
      );
    }
    return result;
  }, [entries, searchQuery, activeKind]);

  if (!gruId || port == null) {
    return (
      <div className="library-view loading">
        <div className="spinner">Loading library…</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="library-view loading">
        <div className="spinner">Loading library...</div>
      </div>
    );
  }

  return (
    <div className="library-view">
      <div className="library-header">
        <div className="library-controls">
          <input
            type="text"
            className="library-search"
            placeholder="Search book entries…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <div className="library-kind-filters">
            {kinds.map((k) => (
              <button
                key={k}
                className={`library-kind-chip${activeKind === k ? " active" : ""}`}
                onClick={() => setActiveKind(k)}
              >
                {k}
              </button>
            ))}
          </div>
        </div>
        <div className="library-stats">
          <span>{filteredEntries.length} entries</span>
          {(searchQuery || activeKind !== "all") && (
            <span>· filtered from {entries.length}</span>
          )}
        </div>
      </div>

      <div className="library-list">
        {filteredEntries.length === 0 ? (
          <div className="empty-state">
            <div className="icon">📭</div>
            <div className="message">
              {searchQuery || activeKind !== "all"
                ? "No matching entries"
                : "Book is empty - no Ethics-curated sources have been added yet"}
            </div>
          </div>
        ) : (
          filteredEntries.map((entry, idx) => (
            <div
              key={entry.path || idx}
              className={`library-entry ${selectedEntry?.path === entry.path ? "selected" : ""}`}
              onClick={() => setSelectedEntry(entry)}
            >
              <div className="entry-header">
                <h3>{entry.title}</h3>
                <span className="tag" style={{ color: "var(--role-observatory)" }}>
                  {entry.kind}
                </span>
              </div>
              <div className="entry-preview">
                {entry.content.substring(0, 240)}
                {entry.content.length > 240 && "…"}
              </div>
              {entry.updated_at && (
                <div className="entry-meta">
                  Updated: {new Date(entry.updated_at).toLocaleString()}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {selectedEntry && (
        <div className="library-detail-panel">
          <div className="panel-header">
            <h2>{selectedEntry.title}</h2>
            <button className="close-btn" onClick={() => setSelectedEntry(null)}>
              ✕
            </button>
          </div>
          <div className="panel-content">
            <div className="entry-meta" style={{ marginBottom: 12 }}>
              <span className="tag" style={{ color: "var(--role-observatory)" }}>
                {selectedEntry.kind}
              </span>
              <span style={{ marginLeft: 8, fontFamily: "var(--font-mono)", fontSize: 11 }}>
                {selectedEntry.path}
              </span>
            </div>
            <div className="entry-full-content">{selectedEntry.content}</div>
          </div>
        </div>
      )}
    </div>
  );
}
