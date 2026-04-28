import { useState, useMemo } from "react";
import type { Task, AgentInfo, TaskStatus } from "@shared/types";
import { statusColor, statusBadge, statusLabel, bidStatusColor, bidStatusLabel, truncate, shortId } from "../utils/format";
import { useI18n } from "../i18n";
import { useLimitPref } from "../hooks/useLimitPref";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  onSelect: (id: string) => void;
}

const COLUMNS: TaskStatus[] = ["unclaimed", "bidding", "awaiting_retrieval", "completed", "no_one_able"];
const LIMIT_OPTIONS = [20, 50, 100, 200];

export default function TasksBoard({ tasks, agents, onSelect }: Props) {
  const { t, locale } = useI18n();
  const [domainFilter, setDomainFilter] = useState("");
  const [hideAdj, setHideAdj]           = useState(true);
  const [colLimit, setColLimit]         = useLimitPref("viz.limit.tasks.col", 50, LIMIT_OPTIONS);

  const filtered = useMemo(() => {
    let list = tasks;
    if (hideAdj) list = list.filter((tk) => tk.type !== "adjudication");
    if (domainFilter) {
      const d = domainFilter.toLowerCase();
      list = list.filter((tk) => tk.domains.some((dom) => dom.toLowerCase().includes(d)));
    }
    return list;
  }, [tasks, domainFilter, hideAdj]);

  // newest-first per column (tasks don't have a timestamp field, so we rely on array order which is insertion order)
  const columns = useMemo(() => {
    const map = new Map<TaskStatus, Task[]>();
    for (const s of COLUMNS) map.set(s, []);
    for (const tk of [...filtered].reverse()) {
      map.get(tk.status)?.push(tk);
    }
    return map;
  }, [filtered]);

  const agentName = (id: string) => {
    const a = agents.find((a) => a.agent_id === id);
    return a?.name || shortId(id);
  };

  const desc = (tk: Task) => {
    const d = tk.content?.description;
    return typeof d === "string" ? truncate(d, 80) : truncate(JSON.stringify(tk.content), 80);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="toolbar shrink-0">
        <input
          type="text"
          placeholder={t("tasks.filterDomain")}
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="eacn-input w-44"
        />
        <label className="flex items-center gap-1.5 text-[10px] text-[var(--muted)] cursor-pointer">
          <input
            type="checkbox"
            checked={hideAdj}
            onChange={(e) => setHideAdj(e.target.checked)}
            className="rounded accent-teal-600"
          />
          {t("tasks.hideAdj")}
        </label>
        <div className="flex-1" />
        <label className="flex items-center gap-1.5 text-[10px] text-[var(--muted)]">
          Per column
          <select
            value={colLimit}
            onChange={(e) => setColLimit(Number(e.target.value))}
            className="limit-select"
          >
            {LIMIT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
      </div>

      {/* Kanban columns */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden">
        <div className="flex gap-3 p-4 h-full" style={{ minWidth: `max(1200px, 100%)` }}>
          {COLUMNS.map((status) => {
            const col = (columns.get(status) || []).slice(0, colLimit);
            const total = (columns.get(status) || []).length;
            return (
              <div key={status} className="w-56 flex flex-col shrink-0 h-full">
                {/* Column header */}
                <div className="flex items-center gap-2 mb-2 px-1 shrink-0">
                  <span className={`w-2 h-2 rounded-full ${statusColor(status)}`} />
                  <span className="text-xs font-semibold text-[var(--text)]">{statusLabel(status, locale)}</span>
                  <span className="text-[10px] text-[var(--muted)] font-mono ml-auto">
                    {col.length}{total > col.length ? `/${total}` : ""}
                  </span>
                </div>
                {/* Column body */}
                <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
                  {col.length === 0 ? (
                    <div className="empty-state py-8 rounded-xl border border-dashed border-[var(--line)]">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      <span>No tasks</span>
                    </div>
                  ) : (
                    col.map((tk) => (
                      <button
                        key={tk.id}
                        onClick={() => onSelect(tk.id)}
                        className="w-full panel-card p-3 text-left hover:shadow-lg transition-shadow"
                      >
                        <div className="text-[10px] font-mono text-[var(--muted)] mb-1">{shortId(tk.id)}</div>
                        <div className="text-xs text-[var(--text)] mb-2 line-clamp-2 leading-relaxed">{desc(tk)}</div>
                        <div className="flex flex-wrap gap-1 mb-2">
                          {tk.domains.map((d) => (
                            <span key={d} className="pill">{d}</span>
                          ))}
                        </div>
                        <div className="flex items-center gap-3 text-[10px] text-[var(--muted)] font-mono">
                          <span>{tk.budget} budget</span>
                          <span>{tk.bids.length} bids</span>
                          <span>{tk.results.length} results</span>
                        </div>
                        {tk.bids.length > 0 && (
                          <div className="mt-2 space-y-0.5">
                            {tk.bids.slice(0, 3).map((b) => (
                              <div key={b.agent_id} className="flex items-center gap-1 text-[10px]">
                                <span className={bidStatusColor(b.status)}>●</span>
                                <span className="text-[var(--muted)] truncate">{agentName(b.agent_id)}</span>
                                <span className="text-[var(--muted-2)] ml-auto">{bidStatusLabel(b.status, locale)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </button>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
