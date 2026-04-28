import type { AgentInfo, Task, LogEntry } from "@shared/types";
import { tierBadge, statusColor, statusLabel, shortId, timeAgo, logColor } from "../utils/format";
import { useI18n } from "../i18n";
import { useLimitPref } from "../hooks/useLimitPref";

interface Props {
  agentId: string;
  agents: AgentInfo[];
  tasks: Task[];
  logs: LogEntry[];
  onClose: () => void;
  onSelectTask: (id: string) => void;
}

const LOG_OPTIONS = [20, 50, 100];

export default function AgentDetail({ agentId, agents, tasks, logs, onClose, onSelectTask }: Props) {
  const { t, locale } = useI18n();
  const [logLimit, setLogLimit] = useLimitPref("viz.limit.agent.logs", 30, LOG_OPTIONS);
  const agent = agents.find((a) => a.agent_id === agentId);
  if (!agent) return null;

  const initiated = tasks.filter((tk) => tk.initiator_id === agentId);
  const bidOn     = tasks.filter((tk) => tk.bids.some((b) => b.agent_id === agentId));
  // newest-first
  const agentLogs = [...logs].reverse().filter((l) => l.agent_id === agentId).slice(0, logLimit);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-lg bg-[var(--bg-soft)] border-l border-[var(--line)] h-full overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[rgba(249,244,234,0.97)] backdrop-blur-sm border-b border-[var(--line)] p-4 flex items-center gap-3 z-10">
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)] w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[rgba(23,23,23,0.06)] transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[var(--text)] truncate">{agent.name}</span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${tierBadge(agent.tier)} text-white`}>
                {agent.tier}
              </span>
            </div>
            <div className="text-[10px] text-[var(--muted)] font-mono mt-0.5">{agent.agent_id}</div>
          </div>
        </div>

        <div className="p-4 space-y-5">
          {/* Basic info */}
          <section>
            <h4 className="section-label mb-2">{t("detail.basicInfo")}</h4>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="metric-card">
                <div className="text-[var(--muted)] text-[10px] mb-0.5">Server</div>
                <div className="text-[var(--text)] font-mono text-[10px]">{agent.server_id}</div>
              </div>
              <div className="metric-card">
                <div className="text-[var(--muted)] text-[10px] mb-0.5">URL</div>
                <div className="text-[var(--text)] text-[10px] truncate">{agent.url}</div>
              </div>
            </div>
          </section>

          {/* Reputation + Balance */}
          <section>
            <h4 className="section-label mb-2">{t("detail.repEcon")}</h4>
            <div className="grid grid-cols-2 gap-2">
              <div className="metric-card">
                <div className="text-[10px] text-[var(--muted)] mb-1">{t("detail.repScore")}</div>
                <div className="text-xl font-bold text-[#df6d2d] tabular-nums">{agent.reputation.toFixed(3)}</div>
                <div className="h-1 bg-[rgba(23,23,23,0.06)] rounded-full mt-2">
                  <div
                    className="h-full bg-gradient-to-r from-[#df6d2d] to-[#e8884f] rounded-full"
                    style={{ width: `${agent.reputation * 100}%` }}
                  />
                </div>
              </div>
              <div className="metric-card">
                <div className="text-[10px] text-[var(--muted)] mb-1">{t("detail.balanceLabel")}</div>
                <div className="text-xl font-bold text-teal-600 tabular-nums">{agent.balance.available.toFixed(1)}</div>
                <div className="text-[10px] text-[var(--muted)] mt-1">
                  {t("detail.frozen")}: {agent.balance.frozen.toFixed(1)}
                </div>
              </div>
            </div>
          </section>

          {/* Domains */}
          <section>
            <h4 className="section-label mb-2">{t("detail.domains")}</h4>
            <div className="flex flex-wrap gap-1">
              {agent.domains.map((d) => (
                <span key={d} className="pill">{d}</span>
              ))}
              {agent.domains.length === 0 && (
                <span className="text-[10px] text-[var(--muted-2)]">No domains registered</span>
              )}
            </div>
          </section>

          {/* Skills */}
          {agent.skills.length > 0 && (
            <section>
              <h4 className="section-label mb-2">{t("detail.skills")}</h4>
              <div className="space-y-1">
                {agent.skills.map((s) => (
                  <div key={s.name} className="metric-card text-xs">
                    <span className="text-[var(--text)] font-medium">{s.name}</span>
                    {s.description && (
                      <span className="text-[var(--muted)] ml-2">{s.description}</span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Tasks initiated — newest first */}
          <section>
            <h4 className="section-label mb-2">{t("detail.tasksInitiated")} ({initiated.length})</h4>
            {initiated.length === 0 ? (
              <div className="empty-state py-4 rounded-xl border border-dashed border-[var(--line)]">
                <span>No tasks initiated</span>
              </div>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {[...initiated].reverse().slice(0, 20).map((tk) => (
                  <button
                    key={tk.id}
                    onClick={() => onSelectTask(tk.id)}
                    className="w-full flex items-center gap-2 p-2.5 metric-card rounded-xl text-xs hover:shadow-md text-left transition-shadow"
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor(tk.status)}`} />
                    <span className="text-[var(--text)] truncate flex-1">
                      {typeof tk.content.description === "string"
                        ? tk.content.description.slice(0, 60)
                        : shortId(tk.id)}
                    </span>
                    <span className="text-[var(--muted)] text-[10px]">{statusLabel(tk.status, locale)}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* Tasks bid on — newest first */}
          <section>
            <h4 className="section-label mb-2">{t("detail.tasksBidOn")} ({bidOn.length})</h4>
            {bidOn.length === 0 ? (
              <div className="empty-state py-4 rounded-xl border border-dashed border-[var(--line)]">
                <span>No bids placed</span>
              </div>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {[...bidOn].reverse().slice(0, 20).map((tk) => {
                  const bid = tk.bids.find((b) => b.agent_id === agentId);
                  return (
                    <button
                      key={tk.id}
                      onClick={() => onSelectTask(tk.id)}
                      className="w-full flex items-center gap-2 p-2.5 metric-card rounded-xl text-xs hover:shadow-md text-left transition-shadow"
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor(tk.status)}`} />
                      <span className="text-[var(--text)] truncate flex-1">{shortId(tk.id)}</span>
                      {bid && (
                        <span className="text-[var(--muted)] font-mono text-[10px]">
                          {bid.status} · {bid.price}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* Recent activity — newest first */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="section-label flex-1">{t("detail.recentActivity")}</h4>
              <select
                value={logLimit}
                onChange={(e) => setLogLimit(Number(e.target.value))}
                className="limit-select"
              >
                {LOG_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            {agentLogs.length === 0 ? (
              <div className="empty-state py-4 rounded-xl border border-dashed border-[var(--line)]">
                <span>{t("detail.noActivity")}</span>
              </div>
            ) : (
              <div className="space-y-0.5 max-h-64 overflow-y-auto font-mono">
                {agentLogs.map((log, i) => (
                  <div key={i} className="flex items-center gap-2 text-[10px] py-0.5 border-b border-[var(--line-soft)] last:border-0">
                    <span className="text-[var(--muted-2)] w-14 shrink-0">{timeAgo(log.timestamp, locale)}</span>
                    <span className={`font-medium ${logColor(log.fn_name)}`}>{log.fn_name}</span>
                    {log.task_id && (
                      <button
                        onClick={() => onSelectTask(log.task_id!)}
                        className="text-[var(--muted)] hover:text-teal-600"
                      >
                        {shortId(log.task_id)}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
