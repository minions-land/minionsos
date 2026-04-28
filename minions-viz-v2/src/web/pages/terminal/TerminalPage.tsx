import { useState, useMemo } from "react";
import { useStore } from "../../hooks/useStore";
import {
  Terminal as TerminalIcon,
  Rows,
  SplitHorizontal,
  GridFour,
  WifiSlash,
  Robot,
} from "@phosphor-icons/react";
import RoleSidebar from "./RoleSidebar";
import TerminalViewport from "./TerminalViewport";
import EmptyState from "../../components/EmptyState";
import { getRoleIdentity } from "../../utils/roleIdentity";

type Mode = "single" | "split" | "grid";

const MODE_OPTIONS: { mode: Mode; icon: typeof Rows; label: string }[] = [
  { mode: "single", icon: Rows, label: "Single" },
  { mode: "split", icon: SplitHorizontal, label: "Split" },
  { mode: "grid", icon: GridFour, label: "Grid" },
];

export default function TerminalPage() {
  const store = useStore();
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("single");

  const port = store.selectedPort;
  const gruId = store.selectedGruId ?? "";
  const agents = store.agents ?? [];

  // Auto-select first agent if nothing selected
  const activeKeys = useMemo(
    () => agents.map((a) => getRoleIdentity(a.agent_id).key),
    [agents],
  );

  const effectiveSelected = selectedRole && activeKeys.includes(selectedRole)
    ? selectedRole
    : activeKeys[0] ?? null;

  // Determine which roles to render in the viewport
  const viewportRoles = useMemo<string[]>(() => {
    if (!effectiveSelected) return [];
    if (mode === "single") return [effectiveSelected];
    if (mode === "split") {
      const idx = activeKeys.indexOf(effectiveSelected);
      const next = activeKeys[(idx + 1) % activeKeys.length];
      return next && next !== effectiveSelected
        ? [effectiveSelected, next]
        : [effectiveSelected];
    }
    // grid: all active
    return activeKeys.length > 0 ? activeKeys : [effectiveSelected];
  }, [mode, effectiveSelected, activeKeys]);

  if (!store.connected) {
    return (
      <div className="page-container animate-fade-in" style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
        <EmptyState icon={WifiSlash} message="Backend not connected" />
      </div>
    );
  }

  if (!port) {
    return (
      <div className="page-container animate-fade-in" style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
        <EmptyState icon={TerminalIcon} message="Select a project to view terminals" />
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="page-container animate-fade-in" style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
        <EmptyState icon={Robot} message="No agents registered for this project" />
      </div>
    );
  }

  return (
    <div
      className="page-container animate-fade-in"
      style={{ display: "flex", height: "100%", overflow: "hidden" }}
    >
      <RoleSidebar
        agents={agents}
        selectedRole={effectiveSelected}
        onSelect={setSelectedRole}
      />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Toolbar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "6px 12px",
            borderBottom: "1px solid var(--line)",
            background: "var(--panel-bg)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <TerminalIcon size={16} color="var(--muted)" />
            <span
              style={{
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "var(--text-2)",
              }}
            >
              Terminal Hub
            </span>
          </div>
          {/* Mode toggle */}
          <div
            style={{
              display: "flex",
              borderRadius: 6,
              overflow: "hidden",
              border: "1px solid var(--line)",
            }}
          >
            {MODE_OPTIONS.map(({ mode: m, icon: Icon, label }) => (
              <button
                key={m}
                title={label}
                onClick={() => setMode(m)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 30,
                  height: 26,
                  border: "none",
                  cursor: "pointer",
                  background: mode === m ? "rgba(255,255,255,0.08)" : "transparent",
                  transition: "background 150ms",
                }}
              >
                <Icon
                  size={14}
                  color={mode === m ? "var(--text)" : "var(--muted)"}
                />
              </button>
            ))}
          </div>
        </div>
        {/* Viewport */}
        <TerminalViewport
          key={`${viewportRoles.join(",")}-${port}-${gruId}`}
          port={port}
          gruId={gruId}
          roles={viewportRoles}
          mode={mode}
        />
      </div>
    </div>
  );
}
