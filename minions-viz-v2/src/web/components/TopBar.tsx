import { useState, useEffect } from "react";
import { MagnifyingGlass, Export, Plugs, Crown } from "@phosphor-icons/react";
import { selectGru, selectProject, gruById, projectByPort } from "../hooks/useStore";
import type { GruInfo } from "@shared/types";

interface Props {
  grus: GruInfo[];
  selectedGruId: string | null;
  selectedPort: number | null;
  connected: boolean;
  agentCount: number;
  taskCount: number;
  onSearch: () => void;
  onExport: () => void;
}

export default function TopBar({
  grus, selectedGruId, selectedPort, connected, agentCount, taskCount, onSearch, onExport,
}: Props) {
  const [showGruDd, setShowGruDd] = useState(false);
  const [showProjDd, setShowProjDd] = useState(false);

  const currentGru = gruById(grus, selectedGruId);
  const currentProject = currentGru ? projectByPort(currentGru.projects, selectedPort) : null;

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!(e.target as Element).closest("[data-dropdown]")) {
        setShowGruDd(false);
        setShowProjDd(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: "var(--z-sticky)",
        height: 48,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 16px",
        background: "rgba(10,14,26,0.88)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--line)",
      }}
    >
      {/* Logo */}
      <div style={{
        fontFamily: "var(--font-sans)",
        fontWeight: 600,
        fontSize: 14,
        color: "var(--text)",
        textShadow: "0 0 12px rgba(6,182,212,0.4)",
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}>
        <Crown size={16} weight="fill" style={{ color: "var(--role-gru)" }} />
        MinionsVIZ
      </div>

      {/* Gru selector */}
      {currentGru && (
        <div style={{ position: "relative", flexShrink: 0 }} data-dropdown>
          <button
            onClick={() => { setShowGruDd((v) => !v); setShowProjDd(false); }}
            aria-expanded={showGruDd}
            aria-label={`Gru: ${currentGru.label}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 10px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--line)",
              background: "var(--surface)",
              color: "var(--text-2)",
              fontSize: 11,
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
              transition: `border-color 150ms var(--ease-out)`,
            }}
          >
            <span style={{
              width: 6, height: 6, borderRadius: "50%",
              background: currentGru.online ? "#10B981" : "#EF4444",
            }} />
            <span style={{ maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {currentGru.label}
            </span>
          </button>
          {showGruDd && (
            <div
              className="animate-slide-up"
              style={{
                position: "absolute",
                top: "calc(100% + 6px)",
                left: 0,
                width: 260,
                background: "var(--panel-bg)",
                backdropFilter: "blur(16px)",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-sm)",
                boxShadow: "var(--shadow-panel)",
                padding: 6,
                maxHeight: 280,
                overflowY: "auto",
              }}
            >
              {grus.map((g) => (
                <button
                  key={g.id}
                  onClick={() => { selectGru(g.id); setShowGruDd(false); }}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "8px 10px",
                    borderRadius: "var(--radius-xs)",
                    border: "none",
                    background: g.id === selectedGruId ? "var(--surface)" : "transparent",
                    color: "var(--text-2)",
                    fontSize: 11,
                    fontFamily: "var(--font-mono)",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: `background 100ms`,
                  }}
                  onMouseEnter={(e) => { if (g.id !== selectedGruId) (e.currentTarget as HTMLElement).style.background = "var(--surface-muted)"; }}
                  onMouseLeave={(e) => { if (g.id !== selectedGruId) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: g.online ? "#10B981" : "#EF4444", flexShrink: 0 }} />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.label}</span>
                  <span style={{ color: "var(--muted)", fontSize: 10 }}>{g.projects.length}p</span>
                </button>
              ))}
              <div style={{ borderTop: "1px solid var(--line)", marginTop: 4, paddingTop: 4 }}>
                <button
                  onClick={() => { selectGru(null); setShowGruDd(false); }}
                  style={{
                    width: "100%", padding: "6px 10px", borderRadius: "var(--radius-xs)",
                    border: "none", background: "transparent", color: "var(--role-noter)",
                    fontSize: 11, cursor: "pointer", textAlign: "left",
                  }}
                >
                  ← All Grus
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Project selector */}
      {currentGru && currentProject && (
        <div style={{ position: "relative", flexShrink: 0 }} data-dropdown>
          <button
            onClick={() => { setShowProjDd((v) => !v); setShowGruDd(false); }}
            aria-expanded={showProjDd}
            aria-label={`Project: ${currentProject.real_name}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 10px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--line)",
              background: "var(--surface)",
              color: "var(--text-2)",
              fontSize: 11,
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
            }}
          >
            <span style={{ color: "var(--muted)", fontSize: 10 }}>{currentProject.port}</span>
            <span style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {currentProject.real_name}
            </span>
          </button>
          {showProjDd && (
            <div
              className="animate-slide-up"
              style={{
                position: "absolute",
                top: "calc(100% + 6px)",
                left: 0,
                width: 280,
                background: "var(--panel-bg)",
                backdropFilter: "blur(16px)",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-sm)",
                boxShadow: "var(--shadow-panel)",
                padding: 6,
                maxHeight: 280,
                overflowY: "auto",
              }}
            >
              {currentGru.projects.map((p) => (
                <button
                  key={p.port}
                  onClick={() => { selectProject(p.port); setShowProjDd(false); }}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "8px 10px",
                    borderRadius: "var(--radius-xs)",
                    border: "none",
                    background: p.port === selectedPort ? "var(--surface)" : "transparent",
                    color: "var(--text-2)",
                    fontSize: 11,
                    fontFamily: "var(--font-mono)",
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                  onMouseEnter={(e) => { if (p.port !== selectedPort) (e.currentTarget as HTMLElement).style.background = "var(--surface-muted)"; }}
                  onMouseLeave={(e) => { if (p.port !== selectedPort) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <span style={{ color: "var(--muted)", fontSize: 10, flexShrink: 0 }}>{p.port}</span>
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.real_name}</span>
                  <span style={{
                    fontSize: 9, padding: "1px 5px", borderRadius: "var(--radius-pill)",
                    background: p.status === "active" ? "var(--status-active)" : p.status === "dormant" ? "var(--status-unclaimed)" : "var(--surface)",
                    color: "#fff",
                  }}>
                    {p.status}
                  </span>
                </button>
              ))}
              <div style={{ borderTop: "1px solid var(--line)", marginTop: 4, paddingTop: 4 }}>
                <button
                  onClick={() => { selectProject(null); setShowProjDd(false); }}
                  style={{
                    width: "100%", padding: "6px 10px", borderRadius: "var(--radius-xs)",
                    border: "none", background: "transparent", color: "var(--role-noter)",
                    fontSize: 11, cursor: "pointer", textAlign: "left",
                  }}
                >
                  ← All Projects
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Connection indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        <Plugs size={14} style={{ color: connected ? "#10B981" : "#EF4444" }} />
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: connected ? "#10B981" : "#EF4444",
          textTransform: "uppercase",
        }}>
          {connected ? "connected" : "disconnected"}
        </span>
      </div>

      {/* Cmd+K */}
      <button
        onClick={onSearch}
        aria-label="Search (Cmd+K)"
        style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "4px 8px", borderRadius: "var(--radius-xs)",
          border: "1px solid var(--line)", background: "transparent",
          color: "var(--muted)", cursor: "pointer", fontSize: 11,
        }}
      >
        <MagnifyingGlass size={13} />
        <span className="kbd">⌘K</span>
      </button>

      {/* Export */}
      <button
        onClick={onExport}
        aria-label="Export snapshot"
        style={{
          display: "grid", placeItems: "center",
          width: 28, height: 28, borderRadius: "var(--radius-xs)",
          border: "1px solid var(--line)", background: "transparent",
          color: "var(--muted)", cursor: "pointer",
        }}
      >
        <Export size={14} />
      </button>
    </header>
  );
}
