import { useState, useEffect, useRef } from "react";
import type { GruInfo, MosProject } from "@shared/types";
import { selectGruProject } from "./store";

interface Props {
  grus: GruInfo[];
  selectedGruId: string | null;
  selectedPort: number | null;
  connected: boolean;
  onOpenVR: () => void;
  isVRSupported: boolean | null;
}

export default function TopBar({
  grus,
  selectedGruId,
  selectedPort,
  connected,
  onOpenVR,
  isVRSupported,
}: Props) {
  const gru = grus.find((g) => g.id === selectedGruId) ?? null;
  const project =
    gru?.projects.find((p) => p.port === selectedPort) ?? null;

  const [showGru, setShowGru] = useState(false);
  const [showProj, setShowProj] = useState(false);
  const gruBtnRef = useRef<HTMLDivElement>(null);
  const projBtnRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!(e.target as Element).closest("[data-dropdown]")) {
        setShowGru(false);
        setShowProj(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <header className="topbar">
      <div className="brand">
        <span className="dot" />
        MinionsVIZ · Observatory
      </div>

      {/* Gru picker */}
      <div ref={gruBtnRef} style={{ position: "relative" }} data-dropdown>
        <button
          className="chip"
          onClick={() => {
            setShowGru((v) => !v);
            setShowProj(false);
          }}
        >
          <span
            className="status-dot"
            style={{ background: gru?.online ? "#22c55e" : "#ef4444" }}
          />
          <span style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>
            {gru ? gru.label : "Select Gru"}
          </span>
          <span style={{ color: "var(--muted)" }}>▾</span>
        </button>
        {showGru && (
          <div className="dropdown">
            {grus.length === 0 && (
              <div className="empty" style={{ padding: 10 }}>no Grus registered</div>
            )}
            {grus.map((g) => (
              <button
                key={g.id}
                className={g.id === selectedGruId ? "active" : ""}
                onClick={() => {
                  selectGruProject(g.id, null);
                  setShowGru(false);
                }}
              >
                <span
                  className="status-dot"
                  style={{ background: g.online ? "#22c55e" : "#ef4444", marginRight: 4 }}
                />
                <span style={{ flex: 1 }}>{g.label}</span>
                <span style={{ color: "var(--muted)", fontFamily: "var(--font-mono)", fontSize: 10 }}>
                  {g.projects.length}p
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Project picker */}
      {gru && (
        <div ref={projBtnRef} style={{ position: "relative" }} data-dropdown>
          <button
            className="chip"
            onClick={() => {
              setShowProj((v) => !v);
              setShowGru(false);
            }}
          >
            <span style={{ color: "var(--muted)", fontSize: 10 }}>
              {project ? project.port : "—"}
            </span>
            <span style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>
              {project ? project.real_name : "Select project"}
            </span>
            <span style={{ color: "var(--muted)" }}>▾</span>
          </button>
          {showProj && (
            <div className="dropdown">
              {gru.projects.length === 0 && (
                <div className="empty" style={{ padding: 10 }}>no projects</div>
              )}
              {gru.projects.map((p: MosProject) => (
                <button
                  key={p.port}
                  className={p.port === selectedPort ? "active" : ""}
                  onClick={() => {
                    selectGruProject(gru.id, p.port);
                    setShowProj(false);
                  }}
                >
                  <span style={{ color: "var(--muted)", fontSize: 10, minWidth: 44 }}>
                    {p.port}
                  </span>
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {p.real_name}
                  </span>
                  <span
                    className={`badge ${p.status === "active" ? "active" : p.status === "dormant" ? "sleeping" : "dismissed"}`}
                  >
                    {p.status}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="spacer" />

      <div
        className="chip"
        style={{ cursor: "default", gap: 6 }}
        aria-live="polite"
      >
        <span
          className="status-dot"
          style={{ background: connected ? "#22c55e" : "#ef4444" }}
        />
        <span style={{ color: connected ? "#86efac" : "#fca5a5" }}>
          {connected ? "link up" : "no link"}
        </span>
      </div>

      <button
        className={isVRSupported ? "chip primary" : "chip"}
        disabled={!isVRSupported}
        onClick={() => isVRSupported && onOpenVR()}
        title={
          isVRSupported
            ? "Enter WebXR immersive VR"
            : "WebXR not available in this browser / no headset"
        }
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M3 8c0-1.1.9-2 2-2h14c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2h-4l-2-2h-4l-2 2H5c-1.1 0-2-.9-2-2V8zm5 4a2 2 0 100-4 2 2 0 000 4zm8 0a2 2 0 100-4 2 2 0 000 4z" />
        </svg>
        Enter VR
      </button>
    </header>
  );
}
