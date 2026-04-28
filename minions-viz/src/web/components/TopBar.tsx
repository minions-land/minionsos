import { useState, useRef, useEffect } from "react";
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
  { key: "overview",   label: "Overview",    shortcut: "1" },
  { key: "roles",      label: "Roles",       shortcut: "2" },
  { key: "dashboard",  label: "Dashboard",   shortcut: "3" },
  { key: "network",    label: "Network",     shortcut: "4" },
  { key: "agents",     label: "EACN Agents", shortcut: "5" },
  { key: "tasks",      label: "Tasks",       shortcut: "6" },
  { key: "tree",       label: "Task Tree",   shortcut: "7" },
  { key: "artifacts",  label: "Artifacts",   shortcut: "8" },
  { key: "logs",       label: "Event Log",   shortcut: "9" },
  { key: "noter",      label: "Noter",       shortcut: "0" },
];

export default function TopBar({
  tab, setTab, connected, endpoint, agentCount, taskCount, lastUpdate,
  onSearch, onExport, grus, selectedGruId, selectedPort,
}: Props) {
  const { locale, toggleLocale } = useI18n();
  const [showGruDd, setShowGruDd] = useState(false);
  const [showProjDd, setShowProjDd] = useState(false);
  const tabsRef = useRef<HTMLDivElement>(null);

  const currentGru = gruById(grus, selectedGruId);
  const currentProject = currentGru ? projectByPort(currentGru.projects, selectedPort) : null;

  // Close dropdowns on outside click
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

  // Scroll active tab into view
  useEffect(() => {
    if (!tabsRef.current) return;
    const active = tabsRef.current.querySelector("[data-active='true']") as HTMLElement | null;
    active?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [tab]);

  function formatLastUpdate(ts: number): string {
    if (!ts) return "—";
    const diff = Date.now() - ts;
    if (diff < 1000) return "just now";
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
    return `${Math.floor(diff / 60_000)}m ago`;
  }

  const gruDot = (online: boolean) => online ? "bg-emerald-500" : "bg-red-400";
  const projDot = (status: string) =>
    status === "active"  ? "bg-indigo-600" :
    status === "dormant" ? "bg-amber-500"  : "bg-neutral-400";

  return (
    <header
      className="shrink-0 sticky top-0 z-20 backdrop-blur-[18px] border-b"
      style={{
        background: "var(--topbar-bg)",
        borderColor: "var(--topbar-border)",
      }}
    >
      <div className="flex items-center gap-2 px-4 py-2 min-h-[52px]">
        {/* Logo */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div
            className="w-8 h-8 rounded-xl grid place-items-center border"
            style={{
              background: "linear-gradient(145deg, rgba(99,102,241,0.22), rgba(139,92,246,0.18)), #fff9ef",
              borderColor: "var(--line)",
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-indigo-600" aria-hidden="true">
              <path d="M5 8.5 12 4l7 4.5v7L12 20l-7-4.5v-7Z" stroke="currentColor" strokeWidth="1.7"/>
              <path d="M5 8.5 12 13l7-4.5M12 13v7" stroke="currentColor" strokeWidth="1.7"/>
            </svg>
          </div>
          <div className="hidden sm:block">
            <div className="font-mono text-[9px] text-indigo-600 tracking-[0.14em] uppercase leading-none">MinionsOS</div>
            <div className="text-xs font-bold tracking-tight" style={{ color: "var(--text)" }}>
              Observatory
            </div>
          </div>
        </div>

        {/* Gru dropdown */}
        {currentGru && (
          <div className="relative shrink-0" data-dropdown>
            <button
              onClick={() => { setShowGruDd((v) => !v); setShowProjDd(false); }}
              aria-label={`Selected Gru: ${currentGru.label}. Click to switch.`}
              aria-expanded={showGruDd}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium border transition-colors hover:border-indigo-400"
              style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--text)" }}
            >
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${gruDot(currentGru.online)}`} />
              <span className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>gru</span>
              <span className="max-w-[100px] truncate">{currentGru.label}</span>
              <svg className="w-3 h-3 shrink-0" style={{ color: "var(--muted)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showGruDd && (
              <div
                className="absolute top-full left-0 mt-2 w-80 rounded-2xl border z-40 p-2 animate-slide-up"
                style={{ background: "var(--surface)", borderColor: "var(--line)", boxShadow: "var(--shadow-xl)" }}
              >
                <div className="max-h-72 overflow-auto">
                  {grus.map((g) => (
                    <button
                      key={g.id}
                      onClick={() => { selectGru(g.id); setShowGruDd(false); }}
                      className="w-full text-left px-3 py-2 rounded-xl text-xs flex items-center gap-2 transition-colors hover:bg-indigo-50"
                      style={{ background: g.id === currentGru.id ? "var(--indigo-50)" : undefined }}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${gruDot(g.online)}`} />
                      <span className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{g.id}</span>
                      <span className="truncate flex-1" style={{ color: "var(--text)" }}>{g.label}</span>
                      <span className="text-[10px]" style={{ color: "var(--muted)" }}>{g.projects.length}p</span>
                    </button>
                  ))}
                </div>
                <div className="border-t mt-2 pt-2" style={{ borderColor: "var(--line)" }}>
                  <button
                    onClick={() => { selectGru(null); setShowGruDd(false); }}
                    className="w-full text-left px-3 py-2 rounded-xl text-xs text-indigo-600 hover:bg-indigo-50 transition-colors"
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
          <div className="relative shrink-0" data-dropdown>
            <button
              onClick={() => { setShowProjDd((v) => !v); setShowGruDd(false); }}
              aria-label={`Selected project: ${currentProject.real_name}. Click to switch.`}
              aria-expanded={showProjDd}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium border transition-colors hover:border-indigo-400"
              style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--text)" }}
            >
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${projDot(currentProject.status)}`} />
              <span className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{currentProject.port}</span>
              <span className="max-w-[140px] truncate">{currentProject.real_name}</span>
              <svg className="w-3 h-3 shrink-0" style={{ color: "var(--muted)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showProjDd && (
              <div
                className="absolute top-full left-0 mt-2 w-80 rounded-2xl border z-40 p-2 animate-slide-up"
                style={{ background: "var(--surface)", borderColor: "var(--line)", boxShadow: "var(--shadow-xl)" }}
              >
                <div className="max-h-72 overflow-auto">
                  {currentGru.projects.map((p) => (
                    <button
                      key={p.port}
                      onClick={() => { selectProject(p.port); setShowProjDd(false); }}
                      className="w-full text-left px-3 py-2 rounded-xl text-xs flex items-center gap-2 transition-colors hover:bg-indigo-50"
                      style={{ background: p.port === currentProject.port ? "var(--indigo-50)" : undefined }}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${projDot(p.status)}`} />
                      <span className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{p.port}</span>
                      <span className="truncate flex-1" style={{ color: "var(--text)" }}>{p.real_name}</span>
                      <span className="text-[10px] uppercase font-mono" style={{ color: "var(--muted)" }}>{p.status}</span>
                    </button>
                  ))}
                </div>
                <div className="border-t mt-2 pt-2" style={{ borderColor: "var(--line)" }}>
                  <button
                    onClick={() => { selectProject(null); setShowProjDd(false); }}
                    className="w-full text-left px-3 py-2 rounded-xl text-xs text-indigo-600 hover:bg-indigo-50 transition-colors"
                  >
                    ← Back to Project picker
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab strip — horizontally scrollable */}
        {currentProject && (
          <nav
            ref={tabsRef}
            className="flex gap-1 overflow-x-auto flex-1 min-w-0 mx-1"
            style={{ scrollbarWidth: "none" }}
            aria-label="Dashboard tabs"
          >
            {TAB_KEYS.map((item) => {
              const isActive = tab === item.key;
              return (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  title={`${item.label} (${item.shortcut})`}
                  data-active={isActive}
                  aria-current={isActive ? "page" : undefined}
                  className="px-3 py-1.5 rounded-full text-xs font-medium transition-all whitespace-nowrap shrink-0"
                  style={isActive ? {
                    background: "linear-gradient(135deg, #4f46e5, #7c3aed)",
                    color: "#ffffff",
                    boxShadow: "0 2px 8px rgba(79,70,229,0.25)",
                  } : {
                    color: "var(--muted)",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLElement).style.color = "var(--text)";
                      (e.currentTarget as HTMLElement).style.background = "rgba(23,23,23,0.06)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLElement).style.color = "var(--muted)";
                      (e.currentTarget as HTMLElement).style.background = "";
                    }
                  }}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        )}

        {/* Right side actions */}
        <div className="flex items-center gap-2 shrink-0 ml-auto">
          <button
            onClick={toggleLocale}
            aria-label={`Switch to ${locale === "en" ? "Chinese" : "English"}`}
            className="text-xs px-2 py-1 rounded-lg transition-colors hover:bg-[rgba(23,23,23,0.06)]"
            style={{ color: "var(--muted)" }}
          >
            {locale === "en" ? "中文" : "EN"}
          </button>

          {currentProject && (
            <>
              <button
                onClick={onSearch}
                aria-label="Open global search (⌘K)"
                className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg transition-colors hover:bg-[rgba(23,23,23,0.06)]"
                style={{ color: "var(--muted)" }}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <span className="hidden lg:inline kbd">⌘K</span>
              </button>

              <button
                onClick={onExport}
                aria-label="Export snapshot as JSON"
                className="text-xs px-2 py-1 rounded-lg transition-colors hover:bg-[rgba(23,23,23,0.06)] hidden md:block"
                style={{ color: "var(--muted)" }}
              >
                Export
              </button>

              <div className="hidden lg:flex items-center gap-2 text-xs font-mono" style={{ color: "var(--muted)" }}>
                <span className="pill">{agentCount} agents</span>
                <span className="pill">{taskCount} tasks</span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${connected ? "bg-indigo-600 animate-pulse-slow" : "bg-red-400"}`}
                  aria-label={connected ? "EACN3 connected" : "EACN3 disconnected"}
                />
                <span className="text-xs hidden sm:inline" style={{ color: "var(--muted)" }}>
                  {connected ? "live" : "down"}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
