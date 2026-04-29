import { useState, useEffect, useCallback } from "react";
import { useStore, gruById, projectByPort, selectProject } from "./hooks/useStore";
import type { Page } from "./components/BottomDock";
import TopBar from "./components/TopBar";
import BottomDock from "./components/BottomDock";
import GruPicker from "./components/GruPicker";
import ProjectPicker from "./components/ProjectPicker";
import SlideOutPanel from "./components/SlideOutPanel";
import TaskDetailModal from "./components/TaskDetailModal";
import GlobalSearch from "./components/GlobalSearch";
import ToastContainer from "./components/ToastContainer";
import SolarSystemPage from "./pages/solar-system/SolarSystemPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import TerminalPage from "./pages/terminal/TerminalPage";
import { getRoleIdentity } from "./utils/roleIdentity";

export default function App() {
  const store = useStore();
  const [page, setPage] = useState<Page>("solar");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [showSearch, setShowSearch] = useState(false);

  const currentGru = gruById(store.grus, store.selectedGruId);
  const currentProject = currentGru
    ? projectByPort(currentGru.projects, store.selectedPort)
    : null;

  // Keyboard shortcuts
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (showSearch) { setShowSearch(false); return; }
        if (selectedTask) { setSelectedTask(null); return; }
        if (selectedAgent) { setSelectedAgent(null); return; }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowSearch((v) => !v);
      }
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "1") setPage("solar");
      else if (e.key === "2") setPage("dashboard");
      else if (e.key === "3") setPage("terminal");
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [showSearch, selectedTask, selectedAgent]);

  const handleExport = useCallback(() => {
    const blob = new Blob([JSON.stringify(store, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mos-v2-snapshot-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [store]);

  const accentColor = selectedAgent
    ? getRoleIdentity(selectedAgent).color
    : undefined;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden", background: "var(--bg-space)" }}>
      <TopBar
        grus={store.grus}
        selectedGruId={store.selectedGruId}
        selectedPort={store.selectedPort}
        connected={store.connected}
        agentCount={store.agents.length}
        taskCount={store.tasks.length}
        onSearch={() => setShowSearch(true)}
        onExport={handleExport}
      />

      <main style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {!currentGru ? (
          <GruPicker grus={store.grus} />
        ) : !currentProject && store.selectedPort == null ? (
          <ProjectPicker gru={currentGru} />
        ) : !currentProject && store.selectedPort != null ? (
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "var(--bg-space)",
          }}>
            <div style={{
              padding: 32, borderRadius: "var(--radius-sm)",
              border: "1px solid var(--line)", background: "var(--panel-bg)",
              backdropFilter: "blur(16px)", textAlign: "center",
              maxWidth: 360,
            }}>
              <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 8 }}>
                Project on port {store.selectedPort} is unavailable.
              </div>
              <button
                onClick={() => selectProject(null)}
                style={{
                  padding: "6px 14px", borderRadius: "var(--radius-pill)",
                  border: "1px solid var(--line)", background: "var(--surface)",
                  color: "var(--role-noter)", fontSize: 11, cursor: "pointer",
                }}
              >
                ← Back to projects
              </button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: page === "solar" ? "contents" : "none" }}>
              <SolarSystemPage store={store} onSelectAgent={setSelectedAgent} />
            </div>
            <div style={{ display: page === "dashboard" ? "contents" : "none" }}>
              <DashboardPage store={store} onSelectAgent={setSelectedAgent} onSelectTask={setSelectedTask} />
            </div>
            <div style={{ display: page === "terminal" ? "contents" : "none" }}>
              <TerminalPage store={store} />
            </div>
          </>
        )}
      </main>

      {currentProject && (
        <BottomDock page={page} onNavigate={setPage} />
      )}

      <SlideOutPanel
        open={selectedAgent != null}
        onClose={() => setSelectedAgent(null)}
        accentColor={accentColor}
      >
        <div style={{ padding: 20, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-2)" }}>
          {selectedAgent}
        </div>
      </SlideOutPanel>

      <TaskDetailModal
        open={selectedTask != null}
        taskId={selectedTask}
        tasks={store.tasks}
        agents={store.agents}
        onClose={() => setSelectedTask(null)}
        onSelectAgent={setSelectedAgent}
      />

      {showSearch && (
        <GlobalSearch
          tasks={store.tasks}
          agents={store.agents}
          logs={store.logs}
          onSelectAgent={(id) => { setSelectedAgent(id); setShowSearch(false); }}
          onSelectTask={(id) => { setSelectedTask(id); setShowSearch(false); }}
          onClose={() => setShowSearch(false)}
        />
      )}

      <ToastContainer />

      {/* Debug overlay */}
      <div style={{
        position: "fixed", bottom: 8, left: 8, zIndex: 99999,
        background: "rgba(0,0,0,0.85)", color: "#0f0", fontFamily: "monospace",
        fontSize: 10, padding: "6px 10px", borderRadius: 6, lineHeight: 1.6,
        pointerEvents: "none", maxWidth: 400,
      }}>
        <div>grus: {store.grus.length} | gruId: {store.selectedGruId ?? "null"}</div>
        <div>port: {store.selectedPort ?? "null"} | connected: {String(store.connected)}</div>
        <div>currentGru: {currentGru?.id ?? "null"} | currentProject: {currentProject?.port ?? "null"}</div>
        <div>agents: {store.agents.length} | tasks: {store.tasks.length}</div>
      </div>
    </div>
  );
}
