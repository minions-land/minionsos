import type { Task, AgentInfo } from "@shared/types";
import { statusColor, statusLabel, bidStatusColor, bidStatusLabel, shortId } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  taskId: string;
  tasks: Task[];
  agents: AgentInfo[];
  onClose: () => void;
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
}

export default function TaskDetail({ taskId, tasks, agents, onClose, onSelectAgent, onSelectTask }: Props) {
  const { t, locale } = useI18n();
  const task = tasks.find((t) => t.id === taskId);
  if (!task) return null;

  const agentName = (id: string) => {
    const a = agents.find((a) => a.agent_id === id);
    return a?.name || shortId(id);
  };

  const desc = typeof task.content.description === "string"
    ? task.content.description
    : JSON.stringify(task.content, null, 2);

  const discussions = Array.isArray(task.content.discussions) ? task.content.discussions : [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl bg-[#fbf8f2] border-l border-[rgba(23,23,23,0.1)] h-full overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[rgba(249,244,234,0.95)] backdrop-blur-sm border-b border-[rgba(23,23,23,0.08)] p-4">
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="text-[#5f5a52] hover:text-[#171717] text-lg">✕</button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${statusColor(task.status)}`} />
                <span className="text-sm font-medium text-[#171717]">{statusLabel(task.status, locale)}</span>
                {task.type === "adjudication" && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-[#df6d2d] text-white rounded-full">{t("node.adjudication")}</span>
                )}
                <span className="text-xs text-[#5f5a52] font-mono">L{task.depth}</span>
              </div>
              <div className="text-xs text-[#5f5a52] font-mono mt-0.5">{task.id}</div>
            </div>
          </div>
        </div>

        <div className="p-4 space-y-5">
          {/* Meta */}
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="metric-card !p-3">
              <div className="text-[#5f5a52] mb-1">{t("taskDetail.budget")}</div>
              <div className="text-lg font-bold text-teal-600">{task.budget}</div>
              {task.remaining_budget !== null && (
                <div className="text-[#5f5a52]">{t("taskDetail.remaining") + ":"} {task.remaining_budget.toFixed(1)}</div>
              )}
            </div>
            <div className="metric-card !p-3">
              <div className="text-[#5f5a52] mb-1">{t("taskDetail.bidsLabel")}</div>
              <div className="text-lg font-bold text-[#174066]">{task.bids.length}</div>
              <div className="text-[#5f5a52]">{t("taskDetail.maxConcurrent") + ":"} {task.max_concurrent_bidders}</div>
            </div>
            <div className="metric-card !p-3">
              <div className="text-[#5f5a52] mb-1">{t("taskDetail.results")}</div>
              <div className="text-lg font-bold text-purple-700">{task.results.length}</div>
              <div className="text-[#5f5a52]">
                {task.results.filter((r) => r.selected).length > 0 ? t("taskDetail.selected") : t("taskDetail.notSelected")}
              </div>
            </div>
          </div>

          {/* Initiator */}
          <div className="text-xs">
            <span className="text-[#5f5a52]">{t("taskDetail.initiator") + ":"} </span>
            <button
              onClick={() => onSelectAgent(task.initiator_id)}
              className="text-teal-600 hover:underline font-medium"
            >
              {agentName(task.initiator_id)}
            </button>
          </div>

          {/* Domains */}
          <div>
            <div className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-1">{t("detail.domains")}</div>
            <div className="flex flex-wrap gap-1">
              {task.domains.map((d) => (
                <span key={d} className="pill">{d}</span>
              ))}
            </div>
          </div>

          {/* Description */}
          <div>
            <div className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-1">{t("taskDetail.description")}</div>
            <div className="metric-card !p-3 text-xs text-[#171717] whitespace-pre-wrap max-h-60 overflow-y-auto font-mono">
              {desc}
            </div>
          </div>

          {/* Parent / Children */}
          {(task.parent_id || task.child_ids.length > 0) && (
            <div>
              <div className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-1">{t("taskDetail.taskTree")}</div>
              <div className="space-y-1">
                {task.parent_id && (
                  <button
                    onClick={() => onSelectTask(task.parent_id!)}
                    className="text-xs text-teal-600 hover:underline font-medium"
                  >
                    ↑ {t("taskDetail.parentTask") + ":"} {shortId(task.parent_id)}
                  </button>
                )}
                {task.child_ids.map((cid) => {
                  const child = tasks.find((t) => t.id === cid);
                  return (
                    <button
                      key={cid}
                      onClick={() => onSelectTask(cid)}
                      className="w-full flex items-center gap-2 text-xs p-2 rounded-xl hover:bg-[rgba(23,23,23,0.04)] text-left transition-colors"
                    >
                      <span>↓</span>
                      {child && <span className={`w-2 h-2 rounded-full ${statusColor(child.status)}`} />}
                      <span className="text-[#5f5a52] font-mono truncate">{shortId(cid)}</span>
                      {child && <span className="text-[#5f5a52]/60 ml-auto">{statusLabel(child.status, locale)}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Bids */}
          {task.bids.length > 0 && (
            <div>
              <div className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-1">{t("taskDetail.bidList")}</div>
              <div className="space-y-1">
                {task.bids.map((b) => (
                  <div key={b.agent_id} className="flex items-center gap-2 metric-card !rounded-xl !p-2.5 text-xs">
                    <span className={`${bidStatusColor(b.status)} text-sm`}>●</span>
                    <button
                      onClick={() => onSelectAgent(b.agent_id)}
                      className="text-teal-600 hover:underline truncate font-medium"
                    >
                      {agentName(b.agent_id)}
                    </button>
                    <span className="text-[#5f5a52] ml-auto font-mono">
                      {t("taskDetail.confidence") + ":"} {b.confidence.toFixed(2)} | {t("taskDetail.price") + ":"} {b.price}
                    </span>
                    <span className={`${bidStatusColor(b.status)} text-[10px] font-medium`}>
                      {bidStatusLabel(b.status, locale)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Results */}
          {task.results.length > 0 && (
            <div>
              <div className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-1">{t("taskDetail.results")}</div>
              <div className="space-y-2">
                {task.results.map((r) => (
                  <div key={r.agent_id} className={`metric-card !rounded-xl !p-3 text-xs ${r.selected ? "!border-emerald-500 ring-1 ring-emerald-500/20" : ""}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <button
                        onClick={() => onSelectAgent(r.agent_id)}
                        className="text-teal-600 hover:underline font-medium"
                      >
                        {agentName(r.agent_id)}
                      </button>
                      {r.selected && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-emerald-600 text-white rounded-full">{t("taskDetail.selected")}</span>
                      )}
                    </div>
                    <div className="text-[#171717] whitespace-pre-wrap max-h-40 overflow-y-auto bg-[rgba(23,23,23,0.04)] rounded-lg p-2 font-mono text-[11px]">
                      {typeof r.content === "string" ? r.content : JSON.stringify(r.content, null, 2)}
                    </div>
                    {r.adjudications.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <div className="text-[#5f5a52] font-medium">{t("taskDetail.adjudication") + ":"}</div>
                        {r.adjudications.map((adj, i) => (
                          <div key={i} className="text-[#5f5a52] pl-2 font-mono">
                            {adj.adjudicator_id}: {adj.verdict} ({t("taskDetail.score") + ":"} {adj.score})
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Discussions */}
          {discussions.length > 0 && (
            <div>
              <div className="text-xs font-mono text-[#0f766e] tracking-[0.1em] uppercase mb-1">{t("taskDetail.discussions")}</div>
              <div className="space-y-1">
                {(discussions as Array<{ message: string; author: string; timestamp: string }>).map((d, i) => (
                  <div key={i} className="metric-card !rounded-xl !p-2.5 text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[#171717] font-medium">{shortId(d.author)}</span>
                      <span className="text-[#5f5a52]/60 text-[10px] font-mono">{d.timestamp}</span>
                    </div>
                    <div className="text-[#171717]">{d.message}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
