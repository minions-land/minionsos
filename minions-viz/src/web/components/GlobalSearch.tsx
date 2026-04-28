import { useState, useMemo, useRef, useEffect } from "react";
import type { Task, AgentInfo, LogEntry } from "@shared/types";
import { shortId, statusLabel, statusColor, logColor, timeAgo } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  logs: LogEntry[];
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
  onClose: () => void;
}

type ResultItem =
  | { kind: "agent"; agent: AgentInfo }
  | { kind: "task"; task: Task }
  | { kind: "log"; log: LogEntry; index: number };

export default function GlobalSearch({ tasks, agents, logs, onSelectAgent, onSelectTask, onClose }: Props) {
  const { t, locale } = useI18n();
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const results = useMemo<ResultItem[]>(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const items: ResultItem[] = [];

    for (const a of agents) {
      if (
        a.name.toLowerCase().includes(q) ||
        a.agent_id.toLowerCase().includes(q) ||
        a.domains.some((d) => d.toLowerCase().includes(q)) ||
        a.description.toLowerCase().includes(q)
      ) {
        items.push({ kind: "agent", agent: a });
      }
      if (items.length >= 50) break;
    }

    for (const tk of tasks) {
      const desc = typeof tk.content.description === "string" ? tk.content.description : "";
      if (
        tk.id.toLowerCase().includes(q) ||
        desc.toLowerCase().includes(q) ||
        tk.domains.some((d) => d.toLowerCase().includes(q)) ||
        tk.initiator_id.toLowerCase().includes(q)
      ) {
        items.push({ kind: "task", task: tk });
      }
      if (items.length >= 80) break;
    }

    for (let i = 0; i < logs.length && items.length < 100; i++) {
      const l = logs[i];
      if (
        l.fn_name.toLowerCase().includes(q) ||
        l.task_id?.toLowerCase().includes(q) ||
        l.agent_id?.toLowerCase().includes(q) ||
        l.error?.toLowerCase().includes(q)
      ) {
        items.push({ kind: "log", log: l, index: i });
      }
    }

    return items;
  }, [query, agents, tasks, logs]);

  function handleSelect(item: ResultItem) {
    if (item.kind === "agent") onSelectAgent(item.agent.agent_id);
    else if (item.kind === "task") onSelectTask(item.task.id);
    else if (item.kind === "log") {
      if (item.log.task_id) onSelectTask(item.log.task_id);
      else if (item.log.agent_id) onSelectAgent(item.log.agent_id);
    }
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center pt-20"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Global search"
    >
      <div className="absolute inset-0 backdrop-blur-sm" style={{ background: "rgba(0,0,0,0.2)" }} />
      <div
        className="relative w-full max-w-xl rounded-3xl overflow-hidden animate-slide-up"
        style={{
          background: "var(--bg-soft)",
          border: "1px solid var(--line)",
          boxShadow: "var(--shadow-xl)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b" style={{ borderColor: "var(--line)" }}>
          <svg className="w-4 h-4 shrink-0" style={{ color: "var(--muted)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            placeholder={t("search.placeholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search agents, tasks, and events"
            className="flex-1 bg-transparent text-sm focus:outline-none"
            style={{ color: "var(--text)" }}
          />
          <kbd className="kbd">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto" role="listbox" aria-label="Search results">
          {query.length >= 2 && results.length === 0 && (
            <div className="p-8 text-center">
              <div className="empty-state">
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <span>{t("search.noResults")}</span>
              </div>
            </div>
          )}

          {query.length < 2 && (
            <div className="p-6 text-center text-xs" style={{ color: "var(--muted)" }}>
              Type at least 2 characters to search agents, tasks, and events.
            </div>
          )}

          {results.map((item, i) => {
            if (item.kind === "agent") {
              const a = item.agent;
              return (
                <button
                  key={`a-${a.agent_id}`}
                  onClick={() => handleSelect(item)}
                  role="option"
                  className="w-full flex items-center gap-3 px-5 py-3 text-left border-b transition-colors hover:bg-[rgba(23,23,23,0.04)]"
                  style={{ borderColor: "var(--line-soft)" }}
                >
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-mono shrink-0"
                    style={{ background: "var(--accent-3)", color: "#fff" }}
                  >
                    Agent
                  </span>
                  <span className="text-sm truncate flex-1" style={{ color: "var(--text)" }}>{a.name}</span>
                  <span className="text-xs font-mono shrink-0" style={{ color: "var(--muted)" }}>{shortId(a.agent_id)}</span>
                  <span className="text-xs font-mono shrink-0" style={{ color: "var(--accent-2)" }}>{a.reputation.toFixed(2)}</span>
                </button>
              );
            }
            if (item.kind === "task") {
              const tk = item.task;
              const desc = typeof tk.content.description === "string" ? tk.content.description : "";
              return (
                <button
                  key={`t-${tk.id}`}
                  onClick={() => handleSelect(item)}
                  role="option"
                  className="w-full flex items-center gap-3 px-5 py-3 text-left border-b transition-colors hover:bg-[rgba(23,23,23,0.04)]"
                  style={{ borderColor: "var(--line-soft)" }}
                >
                  <span className={`text-[10px] px-2 py-0.5 rounded-full text-white shrink-0 ${statusColor(tk.status)}`}>
                    {statusLabel(tk.status, locale)}
                  </span>
                  <span className="text-sm truncate flex-1" style={{ color: "var(--text)" }}>
                    {desc || shortId(tk.id)}
                  </span>
                  <span className="text-xs font-mono shrink-0" style={{ color: "var(--muted)" }}>{shortId(tk.id)}</span>
                </button>
              );
            }
            if (item.kind === "log") {
              const l = item.log;
              return (
                <button
                  key={`l-${item.index}`}
                  onClick={() => handleSelect(item)}
                  role="option"
                  className="w-full flex items-center gap-3 px-5 py-3 text-left border-b transition-colors hover:bg-[rgba(23,23,23,0.04)]"
                  style={{ borderColor: "var(--line-soft)" }}
                >
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-mono shrink-0"
                    style={{ background: "rgba(23,23,23,0.08)", color: "var(--muted)" }}
                  >
                    Log
                  </span>
                  <span className={`text-xs font-medium ${logColor(l.fn_name)}`}>{l.fn_name}</span>
                  {l.task_id && <span className="text-xs font-mono" style={{ color: "var(--muted)" }}>{shortId(l.task_id)}</span>}
                  {l.agent_id && <span className="text-xs font-mono" style={{ color: "var(--muted)" }}>{shortId(l.agent_id)}</span>}
                  <span className="text-[10px] font-mono ml-auto shrink-0" style={{ color: "var(--muted-2)" }}>{timeAgo(l.timestamp, locale)}</span>
                </button>
              );
            }
            return null;
          })}
        </div>

        {/* Footer */}
        {query.length >= 2 && results.length > 0 && (
          <div className="px-5 py-2.5 border-t text-[10px] font-mono" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
            {results.length} {t("search.resultsFooter")}
          </div>
        )}
      </div>
    </div>
  );
}
