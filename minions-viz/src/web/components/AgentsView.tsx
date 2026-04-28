import { useState } from "react";
import type { AgentInfo, Task } from "@shared/types";
import { tierBadge, shortId } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  agents: AgentInfo[];
  tasks: Task[];
  onSelect: (id: string) => void;
}

export default function AgentsView({ agents, tasks, onSelect }: Props) {
  const { t } = useI18n();
  const [filter, setFilter] = useState("");

  const filtered = agents.filter((a) =>
    filter === "" ||
    a.name.toLowerCase().includes(filter.toLowerCase()) ||
    a.domains.some((d) => d.toLowerCase().includes(filter.toLowerCase())) ||
    a.agent_id.includes(filter)
  );

  function countTasks(agentId: string) {
    let initiated = 0, bidOn = 0;
    for (const tk of tasks) {
      if (tk.initiator_id === agentId) initiated++;
      if (tk.bids.some((b) => b.agent_id === agentId)) bidOn++;
    }
    return { initiated, bidOn };
  }

  const byServer = new Map<string, AgentInfo[]>();
  for (const a of filtered) {
    const list = byServer.get(a.server_id) || [];
    list.push(a);
    byServer.set(a.server_id, list);
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="toolbar shrink-0">
        <input
          type="text"
          placeholder={t("agents.searchPlaceholder")}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="eacn-input w-64"
        />
        <span className="text-[10px] text-[var(--muted)] font-mono ml-auto">{filtered.length} agents</span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {filtered.length === 0 ? (
          <div className="empty-state h-48">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span>{filter ? "No agents match your search" : "No agents registered yet"}</span>
          </div>
        ) : (
          <div className="space-y-6">
            {[...byServer.entries()].map(([serverId, serverAgents]) => (
              <div key={serverId}>
                <h3 className="section-label mb-3">
                  Server: {serverId}
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {serverAgents.map((a) => {
                    const { initiated, bidOn } = countTasks(a.agent_id);
                    return (
                      <button
                        key={a.agent_id}
                        onClick={() => onSelect(a.agent_id)}
                        className="panel-card p-4 text-left hover:shadow-lg transition-shadow"
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-sm font-semibold text-[var(--text)] truncate flex-1">
                            {a.name}
                          </span>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${tierBadge(a.tier)} text-white`}>
                            {a.tier}
                          </span>
                        </div>

                        <div className="text-[10px] text-[var(--muted)] font-mono mb-2">
                          {shortId(a.agent_id)}
                        </div>

                        <div className="flex flex-wrap gap-1 mb-3">
                          {a.domains.map((d) => (
                            <span key={d} className="pill">{d}</span>
                          ))}
                          {a.domains.length === 0 && (
                            <span className="text-[10px] text-[var(--muted-2)]">no domains</span>
                          )}
                        </div>

                        {/* Reputation bar */}
                        <div className="mb-2">
                          <div className="flex justify-between text-[10px] mb-1">
                            <span className="text-[var(--muted)]">{t("agents.reputation")}</span>
                            <span className="text-[#df6d2d] font-mono tabular-nums">{a.reputation.toFixed(2)}</span>
                          </div>
                          <div className="h-1 bg-[rgba(23,23,23,0.06)] rounded-full">
                            <div
                              className="h-full bg-gradient-to-r from-[#df6d2d] to-[#e8884f] rounded-full transition-all"
                              style={{ width: `${a.reputation * 100}%` }}
                            />
                          </div>
                        </div>

                        <div className="flex gap-3 text-[10px] text-[var(--muted)]">
                          <span>{t("agents.balance")}: <span className="text-[var(--text)] font-mono tabular-nums">{a.balance.available.toFixed(0)}</span></span>
                          <span>{t("agents.initiated")}: <span className="text-[var(--text)] font-mono">{initiated}</span></span>
                          <span>{t("agents.bidsLabel")}: <span className="text-[var(--text)] font-mono">{bidOn}</span></span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
