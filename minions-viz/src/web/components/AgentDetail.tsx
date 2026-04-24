import type { AgentInfo, Task, LogEntry } from "@shared/types";
import { tierBadge, statusColor, statusLabel, shortId, timeAgo, logColor } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  agentId: string;
  agents: AgentInfo[];
  tasks: Task[];
  logs: LogEntry[];
  onClose: () => void;
  onSelectTask: (id: string) => void;
}

export default function AgentDetail({ agentId, agents, tasks, logs, onClose, onSelectTask }: Props) {
  const { t, locale } = useI18n();
  const agent = agents.find((a) => a.agent_id === agentId);
  if (!agent) return null;

  const initiated = tasks.filter((t) => t.initiator_id === agentId);
  const bidOn = tasks.filter((t) => t.bids.some((b) => b.agent_id === agentId));
  const agentLogs = logs.filter((l) => l.agent_id === agentId).slice(0, 30);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-lg bg-[#fbf8f2] border-l border-[rgba(23,23,23,0.1)] h-full overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[rgba(249,244,234,0.95)] backdrop-blur-sm border-b border-[rgba(23,23,23,0.08)] p-4 flex items-center gap-3">
          <button onClick={onClose} className="text-[#5f5a52] hover:text-[#171717] text-lg">✕</button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[#171717] truncate">{agent.name}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${tierBadge(agent.tier)} text-white`}>
                {agent.tier}
              </span>
            </div>
            <div className="text-xs text-[#5f5a52] font-mono">{agent.agent_id}</div>
          </div>
        </div>

        <div className="p-4 space-y-5">
          {/* Basic info */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.basicInfo")}</h4>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="metric-card !p-3">
                <div className="text-[#5f5a52]">Server</div>
                <div className="text-[#171717] font-mono text-[10px]">{agent.server_id}</div>
              </div>
              <div className="metric-card !p-3">
                <div className="text-[#5f5a52]">URL</div>
                <div className="text-[#171717] text-[10px] truncate">{agent.url}</div>
              </div>
            </div>
          </section>

          {/* Reputation + Balance */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.repEcon")}</h4>
            <div className="grid grid-cols-2 gap-2">
              <div className="metric-card !p-3">
                <div className="text-xs text-[#5f5a52] mb-1">{t("detail.repScore")}</div>
                <div className="text-xl font-bold text-[#df6d2d]">{agent.reputation.toFixed(3)}</div>
                <div className="h-1.5 bg-[rgba(23,23,23,0.06)] rounded-full mt-2">
                  <div
                    className="h-full bg-gradient-to-r from-[#df6d2d] to-[#e8884f] rounded-full"
                    style={{ width: `${agent.reputation * 100}%` }}
                  />
                </div>
              </div>
              <div className="metric-card !p-3">
                <div className="text-xs text-[#5f5a52] mb-1">{t("detail.balanceLabel")}</div>
                <div className="text-xl font-bold text-teal-600">{agent.balance.available.toFixed(1)}</div>
                <div className="text-[10px] text-[#5f5a52] mt-1">
                  {t("detail.frozen") + ":"} {agent.balance.frozen.toFixed(1)}
                </div>
              </div>
            </div>
          </section>

          {/* Domains */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.domains")}</h4>
            <div className="flex flex-wrap gap-1">
              {agent.domains.map((d) => (
                <span key={d} className="pill">{d}</span>
              ))}
            </div>
          </section>

          {/* Skills */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.skills")}</h4>
            <div className="space-y-1">
              {agent.skills.map((s) => (
                <div key={s.name} className="metric-card !p-2.5 text-xs">
                  <span className="text-[#171717] font-medium">{s.name}</span>
                  {s.description && (
                    <span className="text-[#5f5a52] ml-2">{s.description}</span>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Tasks initiated */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.tasksInitiated")} ({initiated.length})</h4>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {initiated.slice(0, 20).map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelectTask(t.id)}
                  className="w-full flex items-center gap-2 p-2.5 metric-card !rounded-xl text-xs hover:shadow-md text-left transition-shadow"
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor(t.status)}`} />
                  <span className="text-[#171717] truncate flex-1">
                    {typeof t.content.description === "string"
                      ? t.content.description.slice(0, 60)
                      : shortId(t.id)}
                  </span>
                  <span className="text-[#5f5a52]">{statusLabel(t.status, locale)}</span>
                </button>
              ))}
            </div>
          </section>

          {/* Tasks bid on */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.tasksBidOn")} ({bidOn.length})</h4>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {bidOn.slice(0, 20).map((t) => {
                const bid = t.bids.find((b) => b.agent_id === agentId);
                return (
                  <button
                    key={t.id}
                    onClick={() => onSelectTask(t.id)}
                    className="w-full flex items-center gap-2 p-2.5 metric-card !rounded-xl text-xs hover:shadow-md text-left transition-shadow"
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor(t.status)}`} />
                    <span className="text-[#171717] truncate flex-1">{shortId(t.id)}</span>
                    {bid && (
                      <span className="text-[#5f5a52] font-mono">
                        {bid.status} · {bid.price}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Recent activity */}
          <section>
            <h4 className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-2">{t("detail.recentActivity")}</h4>
            <div className="space-y-1 max-h-64 overflow-y-auto font-mono">
              {agentLogs.map((log, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] py-0.5">
                  <span className="text-[#5f5a52]/60 w-14 shrink-0">{timeAgo(log.timestamp, locale)}</span>
                  <span className={`font-medium ${logColor(log.fn_name)}`}>{log.fn_name}</span>
                  {log.task_id && (
                    <button
                      onClick={() => onSelectTask(log.task_id!)}
                      className="text-[#5f5a52] hover:text-teal-600"
                    >
                      {shortId(log.task_id)}
                    </button>
                  )}
                </div>
              ))}
              {agentLogs.length === 0 && (
                <div className="text-[#5f5a52]/50 text-xs">{t("detail.noActivity")}</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
