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

    for (const t of tasks) {
      const desc = typeof t.content.description === "string" ? t.content.description : "";
      if (
        t.id.toLowerCase().includes(q) ||
        desc.toLowerCase().includes(q) ||
        t.domains.some((d) => d.toLowerCase().includes(q)) ||
        t.initiator_id.toLowerCase().includes(q)
      ) {
        items.push({ kind: "task", task: t });
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
    <div className="fixed inset-0 z-[90] flex items-start justify-center pt-20" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-xl bg-[#fbf8f2] border border-[rgba(23,23,23,0.1)] rounded-3xl overflow-hidden"
        style={{ boxShadow: "0 30px 90px rgba(38,27,11,0.12)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[rgba(23,23,23,0.08)]">
          <svg className="w-4 h-4 text-[#5f5a52]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            placeholder={t("search.placeholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm text-[#171717] placeholder-[#5f5a52]/50 focus:outline-none"
          />
          <kbd className="text-[10px] text-[#5f5a52]/60 bg-[rgba(23,23,23,0.05)] px-1.5 py-0.5 rounded-md border border-[rgba(23,23,23,0.08)] font-mono">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto">
          {query.length >= 2 && results.length === 0 && (
            <div className="p-6 text-center text-sm text-[#5f5a52]">
              {t("search.noResults")}
            </div>
          )}

          {results.map((item, i) => {
            if (item.kind === "agent") {
              const a = item.agent;
              return (
                <button
                  key={`a-${a.agent_id}`}
                  onClick={() => handleSelect(item)}
                  className="w-full flex items-center gap-3 px-5 py-3 hover:bg-[rgba(23,23,23,0.04)] text-left border-b border-[rgba(23,23,23,0.05)] transition-colors"
                >
                  <span className="text-[10px] px-2 py-0.5 bg-[#174066] text-white rounded-full font-mono">Agent</span>
                  <span className="text-sm text-[#171717] truncate">{a.name}</span>
                  <span className="text-xs text-[#5f5a52] font-mono ml-auto">{shortId(a.agent_id)}</span>
                  <span className="text-xs text-[#df6d2d] font-mono">{a.reputation.toFixed(2)}</span>
                </button>
              );
            }
            if (item.kind === "task") {
              const t = item.task;
              const desc = typeof t.content.description === "string" ? t.content.description : "";
              return (
                <button
                  key={`t-${t.id}`}
                  onClick={() => handleSelect(item)}
                  className="w-full flex items-center gap-3 px-5 py-3 hover:bg-[rgba(23,23,23,0.04)] text-left border-b border-[rgba(23,23,23,0.05)] transition-colors"
                >
                  <span className={`text-[10px] px-2 py-0.5 rounded-full text-white ${statusColor(t.status)}`}>
                    {statusLabel(t.status, locale)}
                  </span>
                  <span className="text-sm text-[#171717] truncate flex-1">
                    {desc || shortId(t.id)}
                  </span>
                  <span className="text-xs text-[#5f5a52] font-mono">{shortId(t.id)}</span>
                </button>
              );
            }
            if (item.kind === "log") {
              const l = item.log;
              return (
                <button
                  key={`l-${item.index}`}
                  onClick={() => handleSelect(item)}
                  className="w-full flex items-center gap-3 px-5 py-3 hover:bg-[rgba(23,23,23,0.04)] text-left border-b border-[rgba(23,23,23,0.05)] transition-colors"
                >
                  <span className="text-[10px] px-2 py-0.5 bg-[rgba(23,23,23,0.08)] text-[#5f5a52] rounded-full font-mono">Log</span>
                  <span className={`text-xs font-medium ${logColor(l.fn_name)}`}>{l.fn_name}</span>
                  {l.task_id && <span className="text-xs text-[#5f5a52] font-mono">{shortId(l.task_id)}</span>}
                  {l.agent_id && <span className="text-xs text-[#5f5a52] font-mono">{shortId(l.agent_id)}</span>}
                  <span className="text-[10px] text-[#5f5a52]/50 ml-auto font-mono">{timeAgo(l.timestamp, locale)}</span>
                </button>
              );
            }
            return null;
          })}
        </div>

        {/* Footer */}
        {query.length >= 2 && results.length > 0 && (
          <div className="px-5 py-2.5 border-t border-[rgba(23,23,23,0.08)] text-[10px] text-[#5f5a52] font-mono">
            {results.length} {t("search.resultsFooter")}
          </div>
        )}
      </div>
    </div>
  );
}
