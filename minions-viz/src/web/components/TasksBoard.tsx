import { useState, useMemo } from "react";
import type { Task, AgentInfo, TaskStatus } from "@shared/types";
import { statusColor, statusLabel, bidStatusColor, bidStatusLabel, truncate, shortId } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  onSelect: (id: string) => void;
}

const COLUMNS: TaskStatus[] = ["unclaimed", "bidding", "awaiting_retrieval", "completed", "no_one_able"];

export default function TasksBoard({ tasks, agents, onSelect }: Props) {
  const { t, locale } = useI18n();
  const [domainFilter, setDomainFilter] = useState("");
  const [hideAdj, setHideAdj] = useState(true);

  const filtered = useMemo(() => {
    let list = tasks;
    if (hideAdj) list = list.filter((t) => t.type !== "adjudication");
    if (domainFilter) {
      const d = domainFilter.toLowerCase();
      list = list.filter((t) => t.domains.some((dom) => dom.toLowerCase().includes(d)));
    }
    return list;
  }, [tasks, domainFilter, hideAdj]);

  const columns = useMemo(() => {
    const map = new Map<TaskStatus, Task[]>();
    for (const s of COLUMNS) map.set(s, []);
    for (const t of filtered) {
      map.get(t.status)?.push(t);
    }
    return map;
  }, [filtered]);

  const agentName = (id: string) => {
    const a = agents.find((a) => a.agent_id === id);
    return a?.name || shortId(id);
  };

  const desc = (t: Task) => {
    const d = t.content?.description;
    return typeof d === "string" ? truncate(d, 80) : truncate(JSON.stringify(t.content), 80);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Filters */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(23,23,23,0.08)] shrink-0 bg-[rgba(249,244,234,0.5)]">
        <input
          type="text"
          placeholder={t("tasks.filterDomain")}
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="eacn-input w-48 text-xs !py-1.5 !px-3"
        />
        <label className="flex items-center gap-1.5 text-xs text-[#5f5a52] cursor-pointer">
          <input
            type="checkbox"
            checked={hideAdj}
            onChange={(e) => setHideAdj(e.target.checked)}
            className="rounded accent-teal-600"
          />
          {t("tasks.hideAdj")}
        </label>
      </div>

      {/* Kanban columns */}
      <div className="flex-1 overflow-x-auto">
        <div className="flex gap-3 p-4 min-w-max h-full">
          {COLUMNS.map((status) => {
            const col = columns.get(status) || [];
            return (
              <div key={status} className="w-72 flex flex-col shrink-0">
                <div className="flex items-center gap-2 mb-2 px-1">
                  <span className={`w-2.5 h-2.5 rounded-full ${statusColor(status)}`} />
                  <span className="text-xs font-medium text-[#171717]">{statusLabel(status, locale)}</span>
                  <span className="text-xs text-[#5f5a52] font-mono ml-auto">{col.length}</span>
                </div>
                <div className="flex-1 overflow-y-auto space-y-2">
                  {col.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => onSelect(t.id)}
                      className="w-full panel-card p-3 text-left hover:shadow-lg transition-shadow"
                    >
                      <div className="text-xs font-mono text-[#5f5a52] mb-1">{shortId(t.id)}</div>
                      <div className="text-xs text-[#171717] mb-2 line-clamp-2">{desc(t)}</div>
                      <div className="flex flex-wrap gap-1 mb-2">
                        {t.domains.map((d) => (
                          <span key={d} className="pill">{d}</span>
                        ))}
                      </div>
                      <div className="flex items-center gap-3 text-[10px] text-[#5f5a52] font-mono">
                        <span>{t.budget} budget</span>
                        <span>{t.bids.length} bids</span>
                        <span>{t.results.length} results</span>
                      </div>
                      {t.bids.length > 0 && (
                        <div className="mt-2 space-y-0.5">
                          {t.bids.slice(0, 3).map((b) => (
                            <div key={b.agent_id} className="flex items-center gap-1 text-[10px]">
                              <span className={bidStatusColor(b.status)}>●</span>
                              <span className="text-[#5f5a52] truncate">{agentName(b.agent_id)}</span>
                              <span className="text-[#5f5a52]/60 ml-auto">{bidStatusLabel(b.status, locale)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
