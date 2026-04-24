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
  const { t, locale } = useI18n();
  const [filter, setFilter] = useState("");

  const filtered = agents.filter((a) =>
    filter === "" ||
    a.name.toLowerCase().includes(filter.toLowerCase()) ||
    a.domains.some((d) => d.toLowerCase().includes(filter.toLowerCase())) ||
    a.agent_id.includes(filter)
  );

  function countTasks(agentId: string) {
    let initiated = 0, bidOn = 0;
    for (const t of tasks) {
      if (t.initiator_id === agentId) initiated++;
      if (t.bids.some((b) => b.agent_id === agentId)) bidOn++;
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
    <div className="h-full overflow-y-auto p-6">
      <div className="mb-4">
        <input
          type="text"
          placeholder={t("agents.searchPlaceholder")}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="eacn-input w-full max-w-md"
        />
      </div>

      <div className="space-y-6">
        {[...byServer.entries()].map(([serverId, agents]) => (
          <div key={serverId}>
            <h3 className="text-xs text-[#5f5a52] font-mono mb-2 uppercase tracking-wider">
              Server: {serverId}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {agents.map((a) => {
                const { initiated, bidOn } = countTasks(a.agent_id);
                return (
                  <button
                    key={a.agent_id}
                    onClick={() => onSelect(a.agent_id)}
                    className="panel-card p-5 text-left hover:shadow-lg transition-shadow"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-semibold text-[#171717] truncate flex-1">
                        {a.name}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${tierBadge(a.tier)} text-white`}>
                        {a.tier}
                      </span>
                    </div>

                    <div className="text-xs text-[#5f5a52] font-mono mb-2">
                      {shortId(a.agent_id)}
                    </div>

                    {/* Domains */}
                    <div className="flex flex-wrap gap-1 mb-3">
                      {a.domains.map((d) => (
                        <span key={d} className="pill">{d}</span>
                      ))}
                    </div>

                    {/* Reputation bar */}
                    <div className="mb-2">
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="text-[#5f5a52]">{t("agents.reputation")}</span>
                        <span className="text-[#df6d2d] font-mono">{a.reputation.toFixed(2)}</span>
                      </div>
                      <div className="h-1.5 bg-[rgba(23,23,23,0.06)] rounded-full">
                        <div
                          className="h-full bg-gradient-to-r from-[#df6d2d] to-[#e8884f] rounded-full transition-all"
                          style={{ width: `${a.reputation * 100}%` }}
                        />
                      </div>
                    </div>

                    {/* Stats */}
                    <div className="flex gap-3 text-[10px] text-[#5f5a52]">
                      <span>{t("agents.balance") + ":"} <span className="text-[#171717] font-mono">{a.balance.available.toFixed(0)}</span></span>
                      <span>{t("agents.initiated") + ":"} <span className="text-[#171717] font-mono">{initiated}</span></span>
                      <span>{t("agents.bidsLabel") + ":"} <span className="text-[#171717] font-mono">{bidOn}</span></span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
