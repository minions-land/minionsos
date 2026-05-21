import { useState, useEffect, useMemo } from "react";
import type { AgentInfo } from "@shared/types";
import { useStore, gruById, projectByPort } from "./store";
import { computeActivity } from "./activity";
import TopBar from "./TopBar";
import Picker from "./Picker";
import UniverseScene, { xrStore } from "./scene/UniverseScene";
import TaskBoard from "./TaskBoard";
import TerminalWall from "./TerminalWall";
import AgentRoster from "./AgentRoster";
import AgentDetail from "./AgentDetail";
import MetricHUD from "./MetricHUD";
import EventLog from "./EventLog";
import Adjudication from "./Adjudication";
import DraftView from "./DraftView";
import { LibraryView } from "./LibraryView";
import { AtlasView } from "./AtlasView";

type View = "universe" | "tasks" | "terminals" | "events" | "adjudication" | "draft" | "book" | "atlas";

export default function App() {
  const store = useStore();
  const [view, setView] = useState<View>("universe");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [vrSupported, setVRSupported] = useState<boolean | null>(null);

  useEffect(() => {
    if (typeof navigator === "undefined" || !(navigator as any).xr) {
      setVRSupported(false);
      return;
    }
    (navigator as any).xr
      .isSessionSupported("immersive-vr")
      .then((ok: boolean) => setVRSupported(!!ok))
      .catch(() => setVRSupported(false));
  }, []);

  const gru = gruById(store.grus, store.selectedGruId);
  const project = gru ? projectByPort(gru.projects, store.selectedPort) : null;

  const selectedAgent: AgentInfo | null = useMemo(
    () =>
      selectedId
        ? (store.agents.find((a) => a.agent_id === selectedId) ?? null)
        : null,
    [selectedId, store.agents],
  );

  useEffect(() => {
    if (selectedId && !store.agents.some((a) => a.agent_id === selectedId)) {
      setSelectedId(null);
    }
  }, [store.agents, selectedId]);

  const activity = useMemo(
    () =>
      computeActivity(store.agents, store.tasks, store.messages, project),
    [store.agents, store.tasks, store.messages, project],
  );

  const showPicker = !gru || !project;

  const adjCount = useMemo(
    () => store.tasks.filter((t) => t.type === "adjudication").length,
    [store.tasks],
  );

  return (
    <div className="app-root">
      <TopBar
        grus={store.grus}
        selectedGruId={store.selectedGruId}
        selectedPort={store.selectedPort}
        connected={store.connected}
        isVRSupported={vrSupported}
        onOpenVR={() => xrStore.enterVR()}
      />

      <div className="stage">
        {showPicker ? (
          <Picker grus={store.grus} selectedGruId={store.selectedGruId} />
        ) : (
          <>
            {view === "universe" && (
              <>
                <UniverseScene
                  project={project}
                  agents={store.agents}
                  activity={activity}
                  selectedId={selectedId}
                  hoveredId={hoveredId}
                  onSelectAgent={(a) => setSelectedId(a?.agent_id ?? null)}
                  onHoverAgent={(a) => setHoveredId(a?.agent_id ?? null)}
                />
                <AgentRoster
                  agents={store.agents}
                  project={project}
                  tasks={store.tasks}
                  messages={store.messages}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onHover={setHoveredId}
                />
                <AgentDetail
                  agent={selectedAgent}
                  project={project}
                  tasks={store.tasks}
                  activity={activity}
                  onClose={() => setSelectedId(null)}
                />
                <MetricHUD
                  agents={store.agents}
                  tasks={store.tasks}
                  messageCount={store.messages.length}
                  connected={store.connected}
                />
                {vrSupported === false && (
                  <div className="vr-unsupported">
                    WebXR not available. Desktop: drag to orbit, wheel to zoom.
                  </div>
                )}
                <div
                  className="read-only-chip"
                  title="Observatory is read-only; no writes are ever sent to EACN."
                >
                  <span className="dot" />
                  read-only observatory
                </div>
              </>
            )}

            {view === "tasks" && (
              <TaskBoard tasks={store.tasks} agents={store.agents} />
            )}

            {view === "terminals" && <TerminalWall agents={store.agents} />}

            {view === "events" && (
              <EventLog
                logs={store.logs}
                messages={store.messages}
                agents={store.agents}
              />
            )}

            {view === "adjudication" && (
              <Adjudication tasks={store.tasks} agents={store.agents} />
            )}

            {view === "draft" && <DraftView />}
            {view === "book" && <LibraryView />}
            {view === "atlas" && <AtlasView />}
          </>
        )}
      </div>

      <nav className="bottom-dock">
        <button
          className={"tab" + (view === "universe" ? " active" : "")}
          onClick={() => setView("universe")}
          disabled={showPicker}
        >
          Universe
        </button>
        <button
          className={"tab" + (view === "tasks" ? " active" : "")}
          onClick={() => setView("tasks")}
          disabled={showPicker}
        >
          Tasks · {store.tasks.length}
        </button>
        <button
          className={"tab" + (view === "terminals" ? " active" : "")}
          onClick={() => setView("terminals")}
          disabled={showPicker}
        >
          Terminals · {store.agents.length}
        </button>
        <button
          className={"tab" + (view === "events" ? " active" : "")}
          onClick={() => setView("events")}
          disabled={showPicker}
        >
          Events · {store.logs.length + store.messages.length}
        </button>
        <button
          className={"tab" + (view === "adjudication" ? " active" : "")}
          onClick={() => setView("adjudication")}
          disabled={showPicker}
        >
          Adjudication · {adjCount}
        </button>
        <button
          className={"tab" + (view === "draft" ? " active" : "")}
          onClick={() => setView("draft")}
          disabled={showPicker}
        >
          Draft
        </button>
        <button
          className={"tab" + (view === "book" ? " active" : "")}
          onClick={() => setView("book")}
          disabled={showPicker}
        >
          📚 Book
        </button>
        <button
          className={"tab" + (view === "atlas" ? " active" : "")}
          onClick={() => setView("atlas")}
          disabled={showPicker}
        >
          🧠 Atlas
        </button>
      </nav>
    </div>
  );
}
