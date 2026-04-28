import { useMemo } from "react";
import type { NetworkSnapshot } from "@shared/types";
import { statusLabel, statusColor, statusBadge, timeAgo, logColor, shortId, tierBadge } from "../utils/format";
import { useI18n } from "../i18n";
import { useLimitPref } from "../hooks/useLimitPref";

interface Props {
  store: NetworkSnapshot;
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
}

const ACTIVITY_OPTIONS = [20, 50, 100];

export default function Dashboard({ store, onSelectAgent, onSelectTask }: Props) {
  const { t, locale } = useI18n();
  const { tasks, agents, cluster, logs } = store;
  const [activityLimit, setActivityLimit] = useLimitPref("viz.limit.dash.activity", 50, ACTIVITY_OPTIONS);

  const statuses = ["unclaimed", "bidding", "awaiting_retrieval", "completed", "no_one_able"] as const;

  const counts: Record<string, number> = {};
  for (const tk of tasks) counts[tk.status] = (counts[tk.status] || 0) + 1;
  const total = tasks.length;

  const economy = useMemo(() => {
    let totalBudget = 0, totalAvailable = 0, totalFrozen = 0;
    let avgReputation = 0, totalBids = 0, totalResults = 0;
    for (const tk of tasks) {
      totalBudget += tk.budget;
      totalBids += tk.bids.length;
      totalResults += tk.results.length;
    }
    for (const a of agents) {
      totalAvailable += a.balance.available;
      totalFrozen += a.balance.frozen;
      avgReputation += a.reputation;
    }
    if (agents.length > 0) avgReputation /= agents.length;
    return { totalBudget, totalAvailable, totalFrozen, avgReputation, totalBids, totalResults };
  }, [tasks, agents]);

  const domainCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const tk of tasks) {
      for (const d of tk.domains) map.set(d, (map.get(d) || 0) + 1);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [tasks]);

  const depthCounts = useMemo(() => {
    const map = new Map<number, number>();
    for (const tk of tasks) map.set(tk.depth, (map.get(tk.depth) || 0) + 1);
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  }, [tasks]);

  const topAgents = useMemo(() => {
    return [...agents].sort((a, b) => b.reputation - a.reputation).slice(0, 8);
  }, [agents]);

  const maxDomainCount = domainCounts.length > 0 ? domainCounts[0][1] : 1;

  // newest-first activity
  const recentActivity = useMemo(() => {
    return [...logs].reverse().slice(0, activityLimit);
  }, [logs, activityLimit]);

  return (
    <div className="h-full overflow-y-auto p-5 space-y-5">
      {/* Status counts */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {statuses.map((s) => (
          <div key={s} className="metric-card">
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`w-2 h-2 rounded-full ${statusColor(s)}`} />
              <span className="text-[10px] text-[var(--muted)] font-medium">{statusLabel(s, locale)}</span>
            </div>
            <div className="text-2xl font-bold text-[var(--text)] tracking-tight tabular-nums">{counts[s] || 0}</div>
          </div>
        ))}
      </div>

      {/* Status distribution bar */}
      {total > 0 && (
        <div className="panel-card p-4">
          <h3 className="section-label mb-2">{t("dash.statusDist")}</h3>
          <div className="flex h-3 rounded-full overflow-hidden gap-px">
            {statuses.map((s) => {
              const pct = ((counts[s] || 0) / total) * 100;
              if (pct === 0) return null;
              return (
                <div
                  key={s}
                  className={`${statusColor(s)} transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${statusLabel(s, locale)}: ${counts[s] || 0} (${pct.toFixed(1)}%)`}
                />
              );
            })}
          </div>
          <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-[var(--muted)]">
            {statuses.map((s) => {
              const c = counts[s] || 0;
              if (c === 0) return null;
              return (
                <span key={s} className="flex items-center gap-1">
                  <span className={`w-1.5 h-1.5 rounded-full ${statusColor(s)}`} />
                  {statusLabel(s, locale)} {c} ({((c / total) * 100).toFixed(0)}%)
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Economy metrics */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {[
          { label: t("dash.totalBudget"),    value: economy.totalBudget.toFixed(0),    color: "text-teal-600" },
          { label: t("dash.totalAvailable"), value: economy.totalAvailable.toFixed(0), color: "text-emerald-600" },
          { label: t("dash.totalFrozen"),    value: economy.totalFrozen.toFixed(0),    color: "text-[#df6d2d]" },
          { label: t("dash.avgReputation"),  value: economy.avgReputation.toFixed(3),  color: "text-[#df6d2d]" },
          { label: t("dash.totalBids"),      value: String(economy.totalBids),         color: "text-[#174066]" },
          { label: t("dash.totalResults"),   value: String(economy.totalResults),      color: "text-purple-700" },
        ].map((item) => (
          <div key={item.label} className="metric-card">
            <div className="text-[10px] text-[var(--muted)] mb-1 font-mono uppercase tracking-wider">{item.label}</div>
            <div className={`text-lg font-bold tabular-nums ${item.color}`}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* Three-column detail row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Domain distribution */}
        <div className="panel-card p-4">
          <h3 className="section-label mb-3">{t("dash.domainDist")}</h3>
          {domainCounts.length === 0 ? (
            <div className="empty-state py-6">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              <span>{t("dash.noDomains")}</span>
            </div>
          ) : (
            <div className="space-y-2">
              {domainCounts.map(([domain, count]) => (
                <div key={domain}>
                  <div className="flex justify-between text-[11px] mb-0.5">
                    <span className="text-[var(--text)] truncate">{domain}</span>
                    <span className="text-[var(--muted)] shrink-0 ml-2 font-mono">{count}</span>
                  </div>
                  <div className="h-1.5 bg-[rgba(23,23,23,0.06)] rounded-full">
                    <div
                      className="h-full bg-gradient-to-r from-teal-600 to-teal-400 rounded-full transition-all"
                      style={{ width: `${(count / maxDomainCount) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Cluster + depth */}
        <div className="space-y-4">
          {cluster && (
            <div className="panel-card p-4">
              <h3 className="section-label mb-3">{t("dash.clusterStatus")}</h3>
              <div className="space-y-1.5 text-xs">
                {[
                  { label: t("dash.mode"),          value: cluster.mode },
                  { label: t("dash.nodeId"),         value: cluster.local.node_id, mono: true },
                  { label: t("dash.onlineMembers"),  value: `${cluster.online_count} / ${cluster.member_count}` },
                  { label: t("dash.version"),        value: cluster.local.version },
                  { label: t("dash.domainCount"),    value: String(cluster.local.domains.length) },
                ].map((item) => (
                  <div key={item.label} className="flex justify-between">
                    <span className="text-[var(--muted)]">{item.label}</span>
                    <span className={`text-[var(--text)] ${item.mono ? "font-mono text-[10px]" : ""}`}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {depthCounts.length > 1 && (
            <div className="panel-card p-4">
              <h3 className="section-label mb-3">{t("dash.depthDist")}</h3>
              <div className="flex items-end gap-1 h-14">
                {depthCounts.map(([depth, count]) => {
                  const maxCount = Math.max(...depthCounts.map(([, c]) => c));
                  const h = (count / maxCount) * 100;
                  return (
                    <div key={depth} className="flex-1 flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-[var(--muted)] font-mono">{count}</span>
                      <div
                        className="w-full bg-gradient-to-t from-[#174066] to-[#1e5a8f] rounded-t transition-all min-h-[2px]"
                        style={{ height: `${h}%` }}
                      />
                      <span className="text-[9px] text-[var(--muted)] font-mono">L{depth}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Top agents */}
        <div className="panel-card p-4">
          <h3 className="section-label mb-3">{t("dash.activeAgents")}</h3>
          {agents.length === 0 ? (
            <div className="empty-state py-6">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>{t("dash.noAgents")}</span>
            </div>
          ) : (
            <div className="space-y-1">
              {topAgents.map((a) => (
                <button
                  key={a.agent_id}
                  onClick={() => onSelectAgent(a.agent_id)}
                  className="w-full flex items-center gap-2 p-2 rounded-xl hover:bg-[rgba(23,23,23,0.04)] transition-colors text-left"
                >
                  <span className="w-2 h-2 rounded-full bg-teal-600 shrink-0" style={{ boxShadow: "0 0 0 3px rgba(15,118,110,0.12)" }} />
                  <span className="text-xs text-[var(--text)] truncate flex-1">{a.name}</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${tierBadge(a.tier)} text-white`}>
                    {a.tier}
                  </span>
                  <span className="text-[10px] text-[#df6d2d] font-mono w-10 text-right tabular-nums">
                    {a.reputation.toFixed(2)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent activity — newest first */}
      <div className="panel-card p-4">
        <div className="flex items-center gap-3 mb-3">
          <h3 className="section-label flex-1">{t("dash.recentActivity")}</h3>
          <label className="flex items-center gap-1.5 text-[10px] text-[var(--muted)]">
            Show
            <select
              value={activityLimit}
              onChange={(e) => setActivityLimit(Number(e.target.value))}
              className="limit-select"
            >
              {ACTIVITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
        </div>
        {recentActivity.length === 0 ? (
          <div className="empty-state py-4">
            <span>{t("dash.noActivity")}</span>
          </div>
        ) : (
          <div className="space-y-0.5 max-h-64 overflow-y-auto">
            {recentActivity.map((log, i) => (
              <div key={i} className="flex items-center gap-2 text-[11px] py-1 border-b border-[var(--line-soft)] last:border-0">
                <span className="text-[var(--muted-2)] w-14 shrink-0 font-mono text-[10px]">
                  {timeAgo(log.timestamp, locale)}
                </span>
                <span className={`font-medium font-mono text-[10px] ${logColor(log.fn_name)}`}>
                  {log.fn_name}
                </span>
                {log.task_id && (
                  <button
                    onClick={() => onSelectTask(log.task_id!)}
                    className="text-[var(--muted)] hover:text-teal-600 font-mono text-[10px] truncate"
                  >
                    {shortId(log.task_id)}
                  </button>
                )}
                {log.agent_id && (
                  <button
                    onClick={() => onSelectAgent(log.agent_id!)}
                    className="text-[var(--muted)] hover:text-[#174066] font-mono text-[10px] truncate"
                  >
                    {shortId(log.agent_id)}
                  </button>
                )}
                {log.error && (
                  <span className="text-red-500 truncate text-[10px] ml-auto max-w-[200px]">
                    {log.error}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
