import { useState } from "react";
import type { Tab } from "../App";
import { useI18n } from "../i18n";
import { selectGru, selectProject, gruById, projectByPort } from "../hooks/useStore";
import type { GruInfo } from "@shared/types";

interface Props {
  tab: Tab;
  setTab: (t: Tab) => void;
  connected: boolean;
  endpoint: string;
  agentCount: number;
  taskCount: number;
  lastUpdate: number;
  onSearch: () => void;
  onExport: () => void;
  grus: GruInfo[];
  selectedGruId: string | null;
  selectedPort: number | null;
}

const TAB_KEYS: { key: Tab; label: string; shortcut: string }[] = [
  { key: "overview", label: "Overview", shortcut: "1" },
  { key: "roles", label: "Roles", shortcut: "2" },
  { key: "dashboard", label: "Dashboard", shortcut: "3" },
  { key: "agents", label: "EACN Agents", shortcut: "4" },
  { key: "tasks", label: "Tasks", shortcut: "5" },
  { key: "tree", label: "Task Tree", shortcut: "6" },
  { key: "artifacts", label: "Artifacts", shortcut: "7" },
  { key: "logs", label: "Event Log", shortcut: "8" },
];

export default function TopBar({
  tab, setTab, connected, endpoint, agentCount, taskCount, lastUpdate,
  onSearch, onExport, grus, selectedGruId, selectedPort,
}: Props) {
  const { locale, toggleLocale } = useI18n();
  const [showGruDd, setShowGruDd] = useState(false);
  const [showProjDd, setShowProjDd] = useState(false);

  const currentGru = gruById(grus, selectedGruId);
  const currentProject = currentGru ? projectByPort(currentGru.projects, selectedPort) : null;

  function formatLastUpdate(ts: number): string {
    if (!ts) return "—";
    const diff = Date.now() - ts;
    if (diff < 1000) return "just now";
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
    return `${Math.floor(diff / 60_000)}m ago`;
  }

  const gruDot = (online: boolean) => online ? "bg-emerald-500" : "bg-red-400";
  const projDot = (status: string) =>
    status === "active" ? "bg-indigo-600" :
    status === "dormant" ? "bg-amber-500" : "bg-neutral-400";

  return (
    <header className="shrink-0 sticky top-0 z-20 backdrop-blur-[18px] bg-[rgba(249,244,234,0.86)] border-b border-[rgba(23,23,23,0.08)]">
      <div className="flex items-center gap-3 px-5 py-3">
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-xl grid place-items-center border border-[rgba(23,23,23,0.08)]"
               style={{ background: "linear-gradient(145deg, rgba(99,102,241,0.22), rgba(139,92,246,0.18)), #fff9ef" }}>
            <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-indigo-600">
              <path d="M5 8.5 12 4l7 4.5v7L12 20l-7-4.5v-7Z" stroke="currentColor" strokeWidth="1.7"/>
              <path d="M5 8.5 12 13l7-4.5M12 13v7" stroke="currentColor" strokeWidth="1.7"/>
            </svg>
          </div>
          <div>
            <div className="font-mono text-[10px] text-indigo-600 tracking-[0.12em] uppercase leading-none">MinionsOS</div>
            <div className="text-sm font-bold text-[#171717] tracking-tight">Project Observatory <span className="text-[#5f5a52] font-normal text-[11px]">· 项目观察台</span></div>
          </div>
        </div>

        {/* Gru dropdown */}
        {currentGru && (
          <div className="relative ml-2">
            <button
              onClick={() => { setShowGruDd((v) => !v); setShowProjDd(false); }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium bg-white border border-[rgba(23,23,23,0.1)] hover:border-indigo-400 transition-colors"
            >
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${gruDot(currentGru.online)}`} />
              <span className="font-mono text-[11px] text-[#5f5a52]">gru</span>
              <span className="text-[#171717] max-w-[160px] truncate">{currentGru.label}</span>
              <span className="text-[#5f5a52]">▾</span>
            </button>
            {showGruDd && (
              <div className="absolute top-full left-0 mt-2 w-80 bg-white border border-[rgba(23,23,23,0.1)] rounded-2xl shadow-xl z-40 p-2">
                <div className="max-h-80 overflow-auto">
                  {grus.map((g) => (
                    <button
                      key={g.id}
                      onClick={() => { selectGru(g.id); setShowGruDd(false); }}
                      className={`w-full text-left px-3 py-2 rounded-xl text-xs flex items-center gap-2 hover:bg-indigo-50 ${
                        g.id === currentGru.id ? "bg-indigo-50" : ""
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${gruDot(g.online)}`} />
                      <span className="font-mono text-[11px] text-[#5f5a52]">{g.id}</span>
                      <span className="text-[#171717] truncate flex-1">{g.label}</span>
                      <span className="text-[10px] text-[#5f5a52]">{g.projects.length}p</span>
                    </button>
                  ))}
                </div>
                <div className="border-t border-[rgba(23,23,23,0.08)] mt-2 pt-2">
                  <button
                    onClick={() => { selectGru(null); setShowGruDd(false); }}
                    className="w-full text-left px-3 py-2 rounded-xl text-xs text-indigo-600 hover:bg-indigo-50"
                  >
                    ← Back to Gru picker
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Project dropdown */}
        {currentGru && currentProject && (
          <div className="relative">
            <button
              onClick={() => { setShowProjDd((v) => !v); setShowGruDd(false); }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium bg-white border border-[rgba(23,23,23,0.1)] hover:border-indigo-400 transition-colors"
            >
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${projDot(currentProject.status)}`} />
              <span className="font-mono text-[11px] text-[#5f5a52]">{currentProject.port}</span>
              <span className="text-[#171717] max-w-[180px] truncate">{currentProject.real_name}</span>
              <span className="text-[#5f5a52]">▾</span>
            </button>
            {showProjDd && (
              <div className="absolute top-full left-0 mt-2 w-80 bg-white border border-[rgba(23,23,23,0.1)] rounded-2xl shadow-xl z-40 p-2">
                <div className="max-h-80 overflow-auto">
                  {currentGru.projects.map((p) => (
                    <button
                      key={p.port}
                      onClick={() => { selectProject(p.port); setShowProjDd(false); }}
                      className={`w-full text-left px-3 py-2 rounded-xl text-xs flex items-center gap-2 hover:bg-indigo-50 ${
                        p.port === currentProject.port ? "bg-indigo-50" : ""
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${projDot(p.status)}`} />
                      <span className="font-mono text-[11px] text-[#5f5a52]">{p.port}</span>
                      <span className="text-[#171717] truncate flex-1">{p.real_name}</span>
                      <span className="text-[10px] text-[#5f5a52] uppercase">{p.status}</span>
                    </button>
                  ))}
                </div>
                <div className="border-t border-[rgba(23,23,23,0.08)] mt-2 pt-2">
                  <button
                    onClick={() => { selectProject(null); setShowProjDd(false); }}
                    className="w-full text-left px-3 py-2 rounded-xl text-xs text-indigo-600 hover:bg-indigo-50"
                  >
                    ← Back to Project picker
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tabs */}
        {currentProject && (
          <nav className="flex gap-1 ml-3 flex-wrap">
            {TAB_KEYS.map((item) => (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                title={`${item.label} (${item.shortcut})`}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  tab === item.key
                    ? "bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/20"
                    : "text-[#5f5a52] hover:text-[#171717] hover:bg-[rgba(23,23,23,0.06)]"
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
        )}

        <div className="flex-1" />

        <button onClick={toggleLocale} className="text-xs text-[#5f5a52] hover:text-[#171717] px-2">
          {locale === "en" ? "中文" : "EN"}
        </button>
        {currentProject && (
          <>
            <button onClick={onSearch} className="text-xs text-[#5f5a52] hover:text-[#171717] px-2">⌘K</button>
            <button onClick={onExport} className="text-xs text-[#5f5a52] hover:text-[#171717] px-2">Export</button>
            <div className="flex items-center gap-3 text-xs text-[#5f5a52] shrink-0 font-mono">
              <span className="pill">{agentCount} agents</span>
              <span className="pill">{taskCount} tasks</span>
              <span className="text-[#5f5a52]/50">↻ {formatLastUpdate(lastUpdate)}</span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <span className={`inline-block w-2 h-2 rounded-full ${connected ? "bg-indigo-600 animate-pulse-slow" : "bg-red-400"}`} />
              <span className="text-xs text-[#5f5a52]">{connected ? "EACN3 up" : "EACN3 down"}</span>
              <span className="text-[10px] text-[#5f5a52]/50 font-mono hidden lg:inline">{endpoint}</span>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
