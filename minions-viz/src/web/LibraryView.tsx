import { useEffect, useState, useMemo } from "react";
import { useStore } from "./store";

interface LibraryEntry {
  title: string;
  content: string;
  tags?: string[];
  created_at?: string;
  updated_at?: string;
  links?: string[];
}

interface LibraryGraph {
  nodes: Array<{ id: string; label: string; type: string }>;
  edges: Array<{ source: string; target: string; label?: string }>;
}

export function LibraryView() {
  const store = useStore();
  const gruId = store.selectedGruId;
  const port = store.selectedPort;
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<LibraryEntry | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "graph">("list");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!gruId || port == null) return;
    setLoading(true);
    fetch(`/api/mos/project/${port}/book?gru=${gruId}`)
      .then((r) => r.json())
      .then((data) => {
        setEntries(data.entries || []);
        setLoading(false);
      })
      .catch(() => {
        setEntries([]);
        setLoading(false);
      });
  }, [gruId, port]);

  const filteredEntries = useMemo(() => {
    if (!searchQuery) return entries;
    const q = searchQuery.toLowerCase();
    return entries.filter(
      (e) =>
        e.title.toLowerCase().includes(q) ||
        e.content.toLowerCase().includes(q) ||
        (e.tags && e.tags.some((t) => t.toLowerCase().includes(q)))
    );
  }, [entries, searchQuery]);

  const libraryGraph = useMemo(() => {
    const nodes = entries.map((e) => ({
      id: e.title,
      label: e.title,
      type: "library-entry",
    }));
    const edges: Array<{ source: string; target: string; label?: string }> = [];
    entries.forEach((e) => {
      if (e.links) {
        e.links.forEach((link) => {
          if (entries.some((entry) => entry.title === link)) {
            edges.push({ source: e.title, target: link, label: "links-to" });
          }
        });
      }
    });
    return { nodes, edges };
  }, [entries]);

  if (!gruId || port == null) {
    return (
      <div className="library-view empty">
        <div className="empty-state">
          <div className="icon">📚</div>
          <div className="message">Select a project to view library entries</div>
        </div>
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
            placeholder="Search library entries..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <div className="view-toggle">
            <button
              className={viewMode === "list" ? "active" : ""}
              onClick={() => setViewMode("list")}
            >
              📝 List
            </button>
            <button
              className={viewMode === "graph" ? "active" : ""}
              onClick={() => setViewMode("graph")}
            >
              🕸️ Graph
            </button>
          </div>
        </div>
        <div className="library-stats">
          <span>{filteredEntries.length} entries</span>
          {searchQuery && <span>· filtered from {entries.length}</span>}
        </div>
      </div>

      {viewMode === "list" ? (
        <div className="library-list">
          {filteredEntries.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📭</div>
              <div className="message">
                {searchQuery ? "No matching entries found" : "No library entries yet"}
              </div>
            </div>
          ) : (
            filteredEntries.map((entry, idx) => (
              <div
                key={idx}
                className={`library-entry ${selectedEntry === entry ? "selected" : ""}`}
                onClick={() => setSelectedEntry(entry)}
              >
                <div className="entry-header">
                  <h3>{entry.title}</h3>
                  {entry.tags && entry.tags.length > 0 && (
                    <div className="entry-tags">
                      {entry.tags.map((tag, i) => (
                        <span key={i} className="tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="entry-preview">
                  {entry.content.substring(0, 200)}
                  {entry.content.length > 200 && "..."}
                </div>
                {entry.updated_at && (
                  <div className="entry-meta">
                    Updated: {new Date(entry.updated_at).toLocaleDateString()}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="library-graph-view">
          <LibraryGraphCanvas graph={libraryGraph} />
        </div>
      )}

      {selectedEntry && (
        <div className="library-detail-panel">
          <div className="panel-header">
            <h2>{selectedEntry.title}</h2>
            <button className="close-btn" onClick={() => setSelectedEntry(null)}>
              ✕
            </button>
          </div>
          <div className="panel-content">
            <div className="entry-full-content">{selectedEntry.content}</div>
            {selectedEntry.links && selectedEntry.links.length > 0 && (
              <div className="entry-links">
                <h4>Links</h4>
                <ul>
                  {selectedEntry.links.map((link, i) => (
                    <li key={i}>
                      <a
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          const linked = entries.find((e) => e.title === link);
                          if (linked) setSelectedEntry(linked);
                        }}
                      >
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function LibraryGraphCanvas({ graph }: { graph: LibraryGraph }) {
  useEffect(() => {
    // TODO: D3 force-directed graph; mirror DraftView style.
  }, [graph]);

  return (
    <div className="graph-canvas">
      <svg width="100%" height="100%">
        <text x="50%" y="50%" textAnchor="middle" fill="#666">
          Graph visualization coming soon...
        </text>
      </svg>
      <div className="graph-stats">
        <span>{graph.nodes.length} nodes</span>
        <span>{graph.edges.length} edges</span>
      </div>
    </div>
  );
}
