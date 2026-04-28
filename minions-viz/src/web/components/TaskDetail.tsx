import type { Task, AgentInfo } from "@shared/types";
import { statusColor, statusBadge, statusLabel, bidStatusColor, bidStatusLabel, shortId } from "../utils/format";
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
  const task = tasks.find((tk) => tk.id === taskId);
  if (!task) return null;

  const agentName = (id: string) => {
    const a = agents.find((a) => a.agent_id === id);
    return a?.name || shortId(id);
  };

  const desc = typeof task.content.description === "string"
    ? task.content.description
    : JSON.stringify(task.content, null, 2);

  const discussions = Array.isArray(task.content.discussions)
    ? [...(task.content.discussions as Array<{ message: string; author: string; timestamp: string }>)].reverse()
    : [];

  // newest-first bids
  const bids = [...task.bids].reverse();

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl bg-[var(--bg-soft)] border-l border-[var(--line)] h-full overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[rgba(249,244,234,0.97)] backdrop-blur-sm border-b border-[var(--line)] p-4 z-10">
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)] w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[rgba(23,23,23,0.06)] transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`w-2.5 h-2.5 rounded-full ${statusColor(task.status)}`} />
                <span className="text-sm font-medium text-[var(--text)]">{statusLabel(task.status, locale)}</span>
                {task.type === "adjudication" && (
                  <span className="text-[9px] px-1.5 py-0.5 bg-[#df6d2d] text-white rounded-full">{t("node.adjudication")}</span>
                )}
                <span className="text-[10px] text-[var(--muted)] font-mono">L{task.depth}</span>
              </div>
              <div className="text-[10px] text-[var(--muted)] font-mono mt-0.5 truncate">{task.id}</div>
            </div>
          </div>
        </div>

        <div className="p-4 space-y-5">
          {/* Meta */}
          <div className="grid grid-cols-3 gap-3">
            <div className="metric-card">
              <div className="text-[10px] text-[var(--muted)] mb-1">{t("taskDetail.budget")}</div>
              <div className="text-lg font-bold text-teal-600 tabular-nums">{task.budget}</div>
              {task.remaining_budget !== null && (
                <div className="text-[10px] text-[var(--muted)]">{t("taskDetail.remaining")}: {task.remaining_budget.toFixed(1)}</div>
              )}
            </div>
            <div className="metric-card">
              <div className="text-[10px] text-[var(--muted)] mb-1">{t("taskDetail.bidsLabel")}</div>
              <div className="text-lg font-bold text-[#174066] tabular-nums">{task.bids.length}</div>
              <div className="text-[10px] text-[var(--muted)]">{t("taskDetail.maxConcurrent")}: {task.max_concurrent_bidders}</div>
            </div>
            <div className="metric-card">
              <div className="text-[10px] text-[var(--muted)] mb-1">{t("taskDetail.results")}</div>
              <div className="text-lg font-bold text-purple-700 tabular-nums">{task.results.length}</div>
              <div className="text-[10px] text-[var(--muted)]">
                {task.results.filter((r) => r.selected).length > 0 ? t("taskDetail.selected") : t("taskDetail.notSelected")}
              </div>
            </div>
          </div>

          {/* Initiator */}
          <div className="text-xs">
            <span className="text-[var(--muted)]">{t("taskDetail.initiator")}: </span>
            <button
              onClick={() => onSelectAgent(task.initiator_id)}
              className="text-teal-600 hover:underline font-medium"
            >
              {agentName(task.initiator_id)}
            </button>
          </div>

          {/* Domains */}
          <div>
            <div className="section-label mb-1.5">{t("detail.domains")}</div>
            <div className="flex flex-wrap gap-1">
              {task.domains.map((d) => (
                <span key={d} className="pill">{d}</span>
              ))}
              {task.domains.length === 0 && (
                <span className="text-[10px] text-[var(--muted-2)]">No domains</span>
              )}
            </div>
          </div>

          {/* Description */}
          <div>
            <div className="section-label mb-1.5">{t("taskDetail.description")}</div>
            <div className="metric-card text-xs text-[var(--text)] whitespace-pre-wrap max-h-60 overflow-y-auto font-mono text-[11px]">
              {desc}
            </div>
          </div>

          {/* Parent / Children */}
          {(task.parent_id || task.child_ids.length > 0) && (
            <div>
              <div className="section-label mb-1.5">{t("taskDetail.taskTree")}</div>
              <div className="space-y-1">
                {task.parent_id && (
                  <button
                    onClick={() => onSelectTask(task.parent_id!)}
                    className="text-xs text-teal-600 hover:underline font-medium"
                  >
                    ↑ {t("taskDetail.parentTask")}: {shortId(task.parent_id)}
                  </button>
                )}
                {task.child_ids.map((cid) => {
                  const child = tasks.find((tk) => tk.id === cid);
                  return (
                    <button
                      key={cid}
                      onClick={() => onSelectTask(cid)}
                      className="w-full flex items-center gap-2 text-xs p-2 rounded-xl hover:bg-[rgba(23,23,23,0.04)] text-left transition-colors"
                    >
                      <span className="text-[var(--muted)]">↓</span>
                      {child && <span className={`w-2 h-2 rounded-full ${statusColor(child.status)}`} />}
                      <span className="text-[var(--muted)] font-mono truncate">{shortId(cid)}</span>
                      {child && <span className="text-[var(--muted-2)] ml-auto text-[10px]">{statusLabel(child.status, locale)}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Bids — newest first */}
          {task.bids.length > 0 && (
            <div>
              <div className="section-label mb-1.5">{t("taskDetail.bidList")}</div>
              <div className="space-y-1">
                {bids.map((b) => (
                  <div key={b.agent_id} className="flex items-center gap-2 metric-card rounded-xl text-xs">
                    <span className={`${bidStatusColor(b.status)} text-sm`}>●</span>
                    <button
                      onClick={() => onSelectAgent(b.agent_id)}
                      className="text-teal-600 hover:underline truncate font-medium"
                    >
                      {agentName(b.agent_id)}
                    </button>
                    <span className="text-[var(--muted)] ml-auto font-mono text-[10px]">
                      {t("taskDetail.confidence")}: {b.confidence.toFixed(2)} | {t("taskDetail.price")}: {b.price}
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
              <div className="section-label mb-1.5">{t("taskDetail.results")}</div>
              <div className="space-y-2">
                {task.results.map((r) => (
                  <div key={r.agent_id} className={`metric-card rounded-xl text-xs ${r.selected ? "border-emerald-500 ring-1 ring-emerald-500/20" : ""}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <button
                        onClick={() => onSelectAgent(r.agent_id)}
                        className="text-teal-600 hover:underline font-medium"
                      >
                        {agentName(r.agent_id)}
                      </button>
                      {r.selected && (
                        <span className="text-[9px] px-1.5 py-0.5 bg-emerald-600 text-white rounded-full">{t("taskDetail.selected")}</span>
                      )}
                    </div>
                    <div className="text-[var(--text)] whitespace-pre-wrap max-h-40 overflow-y-auto bg-[rgba(23,23,23,0.04)] rounded-lg p-2 font-mono text-[11px]">
                      {typeof r.content === "string" ? r.content : JSON.stringify(r.content, null, 2)}
                    </div>
                    {r.adjudications.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <div className="text-[var(--muted)] font-medium text-[10px]">{t("taskDetail.adjudication")}:</div>
                        {r.adjudications.map((adj, i) => (
                          <div key={i} className="text-[var(--muted)] pl-2 font-mono text-[10px]">
                            {adj.adjudicator_id}: {adj.verdict} ({t("taskDetail.score")}: {adj.score})
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Discussions — newest first */}
          {discussions.length > 0 && (
            <div>
              <div className="section-label mb-1.5">{t("taskDetail.discussions")}</div>
              <div className="space-y-1">
                {discussions.map((d, i) => (
                  <div key={i} className="metric-card rounded-xl text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[var(--text)] font-medium">{shortId(d.author)}</span>
                      <span className="text-[var(--muted-2)] text-[10px] font-mono">{d.timestamp}</span>
                    </div>
                    <div className="text-[var(--text)]">{d.message}</div>
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
