import { useState, useEffect, useCallback, useRef } from "react";
import { useStore, gruById, projectByPort } from "./hooks/useStore";
import { I18nProvider } from "./i18n";
import TopBar from "./components/TopBar";
import Dashboard from "./components/Dashboard";
import AgentsView from "./components/AgentsView";
import TasksBoard from "./components/TasksBoard";
import TaskTree from "./components/TaskTree";
import EventLog from "./components/EventLog";
import NetworkGraph from "./components/NetworkGraph";
import NoterView from "./components/NoterView";
import AgentDetail from "./components/AgentDetail";
import TaskDetail from "./components/TaskDetail";
import GlobalSearch from "./components/GlobalSearch";
import ToastContainer, { toast } from "./components/ToastContainer";
import GruPicker from "./components/GruPicker";
import ProjectPicker from "./components/ProjectPicker";
import OverviewTab from "./components/OverviewTab";
import RolesTab from "./components/RolesTab";
import ArtifactsTab from "./components/ArtifactsTab";

export type Tab = "overview" | "roles" | "dashboard" | "network" | "agents" | "tasks" | "tree" | "artifacts" | "logs" | "noter";

function AppInner() {
  const store = useStore();
  const [tab, setTab] = useState<Tab>("overview");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [showSearch, setShowSearch] = useState(false);

  const currentGru = gruById(store.grus, store.selectedGruId);
  const currentProject = currentGru ? projectByPort(currentGru.projects, store.selectedPort) : null;
  const prevRef = useRef({ taskCount: 0, agentCount: 0, connected: false });

  useEffect(() => {
    const prev = prevRef.current;
    if (prev.taskCount > 0 && store.tasks.length > prev.taskCount) {
      toast(`${store.tasks.length - prev.taskCount} new task(s)`, "info");
    }
    if (prev.connected && !store.connected && store.selectedPort != null) {
      toast(`EACN3 backend on ${store.selectedPort} disconnected`, "error");
    } else if (!prev.connected && store.connected) {
      toast("EACN3 backend connected", "success");
    }
    prevRef.current = {
      taskCount: store.tasks.length,
      agentCount: store.agents.length,
      connected: store.connected,
    };
  }, [store.tasks.length, store.agents.length, store.connected, store.selectedPort]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "Escape") {
        if (showSearch) { setShowSearch(false); return; }
        if (selectedTask) { setSelectedTask(null); return; }
        if (selectedAgent) { setSelectedAgent(null); return; }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setShowSearch((v) => !v); return; }
      const tabMap: Record<string, Tab> = {
        "1": "overview", "2": "roles", "3": "dashboard", "4": "network",
        "5": "agents", "6": "tasks", "7": "tree", "8": "artifacts", "9": "logs", "0": "noter",
      };
      if (tabMap[e.key]) setTab(tabMap[e.key]);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showSearch, selectedTask, selectedAgent]);

  const exportSnapshot = useCallback(() => {
    const blob = new Blob([JSON.stringify(store, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mos-snapshot-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Snapshot exported", "success");
  }, [store]);

  const port = store.selectedPort;
  const gruId = store.selectedGruId ?? "";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-transparent">
      <TopBar
        tab={tab} setTab={setTab}
        connected={store.connected} endpoint={store.eacnEndpoint}
        agentCount={store.agents.length} taskCount={store.tasks.length}
        lastUpdate={store.lastUpdate}
        onSearch={() => setShowSearch(true)} onExport={exportSnapshot}
        grus={store.grus} selectedGruId={store.selectedGruId} selectedPort={store.selectedPort}
      />

      <main className="flex-1 overflow-hidden relative">
        {!currentGru && <GruPicker grus={store.grus} />}
        {currentGru && !currentProject && <ProjectPicker gru={currentGru} />}

        {currentProject && !store.connected && tab !== "overview" && tab !== "roles" && tab !== "artifacts" && tab !== "logs" && (
          <div className="absolute top-0 left-0 right-0 z-10 bg-amber-100 border-b border-amber-300 px-4 py-2 text-xs text-amber-900">
            EACN3 backend for project_{port} is not running at 127.0.0.1:{port}.
            Filesystem views (Overview, Roles, Artifacts) still work.
          </div>
        )}

        {currentProject && tab === "overview" && <OverviewTab port={port!} gruId={gruId} />}
        {currentProject && tab === "roles" && <RolesTab port={port!} gruId={gruId} project={currentProject} />}
        {currentProject && tab === "artifacts" && <ArtifactsTab port={port!} gruId={gruId} />}
        {currentProject && tab === "noter" && <NoterView port={port!} gruId={gruId} project={currentProject} />}

        {currentProject && tab === "dashboard" && (
          <Dashboard store={store} onSelectAgent={setSelectedAgent} onSelectTask={setSelectedTask} />
        )}
        {currentProject && tab === "network" && (
          <NetworkGraph
            tasks={store.tasks}
            agents={store.agents}
            messages={store.messages}
            onSelectAgent={setSelectedAgent}
            onSelectTask={setSelectedTask}
          />
        )}
        {currentProject && tab === "agents" && (
          <AgentsView agents={store.agents} tasks={store.tasks} onSelect={setSelectedAgent} />
        )}
        {currentProject && tab === "tasks" && (
          <TasksBoard tasks={store.tasks} agents={store.agents} onSelect={setSelectedTask} />
        )}
        {currentProject && tab === "tree" && (
          <TaskTree tasks={store.tasks} onSelect={setSelectedTask} />
        )}
        {currentProject && tab === "logs" && <EventLog logs={store.logs} />}
      </main>

      {selectedAgent && (
        <AgentDetail
          agentId={selectedAgent} agents={store.agents} tasks={store.tasks} logs={store.logs}
          onClose={() => setSelectedAgent(null)} onSelectTask={setSelectedTask}
        />
      )}
      {selectedTask && (
        <TaskDetail
          taskId={selectedTask} tasks={store.tasks} agents={store.agents}
          onClose={() => setSelectedTask(null)} onSelectAgent={setSelectedAgent}
          onSelectTask={setSelectedTask}
        />
      )}
      {showSearch && (
        <GlobalSearch
          tasks={store.tasks} agents={store.agents} logs={store.logs}
          onSelectAgent={(id) => { setSelectedAgent(id); setShowSearch(false); }}
          onSelectTask={(id) => { setSelectedTask(id); setShowSearch(false); }}
          onClose={() => setShowSearch(false)}
        />
      )}
      <ToastContainer />
    </div>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <AppInner />
    </I18nProvider>
  );
}
