import { useMemo } from "react";
import type { NetworkSnapshot } from "@shared/types";
import { statusLabel, statusColor, timeAgo, logColor, shortId, tierBadge } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  store: NetworkSnapshot;
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
}

export default function Dashboard({ store, onSelectAgent, onSelectTask }: Props) {
  const { t, locale } = useI18n();
  const { tasks, agents, cluster, logs } = store;

  const statuses = ["unclaimed", "bidding", "awaiting_retrieval", "completed", "no_one_able"] as const;

  const counts: Record<string, number> = {};
  for (const t of tasks) counts[t.status] = (counts[t.status] || 0) + 1;
  const total = tasks.length;

  const economy = useMemo(() => {
    let totalBudget = 0, totalAvailable = 0, totalFrozen = 0;
    let avgReputation = 0, totalBids = 0, totalResults = 0;
    for (const t of tasks) {
      totalBudget += t.budget;
      totalBids += t.bids.length;
      totalResults += t.results.length;
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
    for (const t of tasks) {
      for (const d of t.domains) map.set(d, (map.get(d) || 0) + 1);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [tasks]);

  const depthCounts = useMemo(() => {
    const map = new Map<number, number>();
    for (const t of tasks) map.set(t.depth, (map.get(t.depth) || 0) + 1);
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  }, [tasks]);

  const topAgents = useMemo(() => {
    return [...agents].sort((a, b) => b.reputation - a.reputation).slice(0, 8);
  }, [agents]);

  const maxDomainCount = domainCounts.length > 0 ? domainCounts[0][1] : 1;

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {statuses.map((s) => (
          <div key={s} className="metric-card">
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2.5 h-2.5 rounded-full ${statusColor(s)}`} />
              <span className="text-xs text-[#5f5a52] font-medium">{statusLabel(s, locale)}</span>
            </div>
            <div className="text-2xl font-bold text-[#171717] tracking-tight">{counts[s] || 0}</div>
          </div>
        ))}
      </div>

      {total > 0 && (
        <div className="panel-card p-4">
          <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-2">{t("dash.statusDist")}</h3>
          <div className="flex h-4 rounded-full overflow-hidden">
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
          <div className="flex gap-4 mt-2 text-[10px] text-[#5f5a52]">
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

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {[
          { label: t("dash.totalBudget"), value: economy.totalBudget.toFixed(0), color: "text-teal-600" },
          { label: t("dash.totalAvailable"), value: economy.totalAvailable.toFixed(0), color: "text-emerald-600" },
          { label: t("dash.totalFrozen"), value: economy.totalFrozen.toFixed(0), color: "text-[#df6d2d]" },
          { label: t("dash.avgReputation"), value: economy.avgReputation.toFixed(3), color: "text-[#df6d2d]" },
          { label: t("dash.totalBids"), value: String(economy.totalBids), color: "text-[#174066]" },
          { label: t("dash.totalResults"), value: String(economy.totalResults), color: "text-purple-700" },
        ].map((item) => (
          <div key={item.label} className="metric-card">
            <div className="text-[10px] text-[#5f5a52] mb-1 font-mono uppercase tracking-wider">{item.label}</div>
            <div className={`text-lg font-bold ${item.color}`}>{item.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="panel-card p-5">
          <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">{t("dash.domainDist")}</h3>
          <div className="space-y-2">
            {domainCounts.map(([domain, count]) => (
              <div key={domain}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-[#171717] truncate">{domain}</span>
                  <span className="text-[#5f5a52] shrink-0 ml-2 font-mono">{count}</span>
                </div>
                <div className="h-1.5 bg-[rgba(23,23,23,0.06)] rounded-full">
                  <div
                    className="h-full bg-gradient-to-r from-teal-600 to-teal-400 rounded-full transition-all"
                    style={{ width: `${(count / maxDomainCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {domainCounts.length === 0 && (
              <div className="text-xs text-[#5f5a52]/50">{t("dash.noDomains")}</div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          {cluster && (
            <div className="panel-card p-5">
              <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">{t("dash.clusterStatus")}</h3>
              <div className="space-y-2 text-sm">
                {[
                  { label: t("dash.mode"), value: cluster.mode },
                  { label: t("dash.nodeId"), value: cluster.local.node_id, mono: true },
                  { label: t("dash.onlineMembers"), value: `${cluster.online_count} / ${cluster.member_count}` },
                  { label: t("dash.version"), value: cluster.local.version },
                  { label: t("dash.domainCount"), value: String(cluster.local.domains.length) },
                ].map((item) => (
                  <div key={item.label} className="flex justify-between">
                    <span className="text-[#5f5a52]">{item.label}</span>
                    <span className={`text-[#171717] ${item.mono ? "font-mono text-xs" : ""}`}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {depthCounts.length > 1 && (
            <div className="panel-card p-5">
              <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">{t("dash.depthDist")}</h3>
              <div className="flex items-end gap-1 h-16">
                {depthCounts.map(([depth, count]) => {
                  const maxCount = Math.max(...depthCounts.map(([, c]) => c));
                  const h = (count / maxCount) * 100;
                  return (
                    <div key={depth} className="flex-1 flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-[#5f5a52] font-mono">{count}</span>
                      <div
                        className="w-full bg-gradient-to-t from-[#174066] to-[#1e5a8f] rounded-t transition-all min-h-[2px]"
                        style={{ height: `${h}%` }}
                      />
                      <span className="text-[9px] text-[#5f5a52] font-mono">L{depth}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="panel-card p-5">
          <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">{t("dash.activeAgents")}</h3>
          <div className="space-y-1.5">
            {topAgents.map((a) => (
              <button
                key={a.agent_id}
                onClick={() => onSelectAgent(a.agent_id)}
                className="w-full flex items-center gap-2 p-2.5 rounded-xl hover:bg-[rgba(23,23,23,0.04)] transition-colors text-left"
              >
                <span className="w-2 h-2 rounded-full bg-teal-600 shrink-0" style={{ boxShadow: "0 0 0 3px rgba(15,118,110,0.12)" }} />
                <span className="text-sm text-[#171717] truncate flex-1">{a.name}</span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${tierBadge(a.tier)} text-white`}>
                  {a.tier}
                </span>
                <span className="text-xs text-[#df6d2d] font-mono w-10 text-right">
                  {a.reputation.toFixed(2)}
                </span>
              </button>
            ))}
            {agents.length === 0 && (
              <div className="text-xs text-[#5f5a52]/50">{t("dash.noAgents")}</div>
            )}
          </div>
        </div>
      </div>

      <div className="panel-card p-5">
        <h3 className="text-xs font-mono text-[#0f766e] tracking-[0.12em] uppercase mb-3">{t("dash.recentActivity")}</h3>
        <div className="space-y-1 max-h-[300px] overflow-y-auto">
          {logs.slice(0, 30).map((log, i) => (
            <div key={i} className="flex items-center gap-2 text-xs py-1">
              <span className="text-[#5f5a52]/60 w-16 shrink-0 font-mono">
                {timeAgo(log.timestamp, locale)}
              </span>
              <span className={`font-medium ${logColor(log.fn_name)}`}>
                {log.fn_name}
              </span>
              {log.task_id && (
                <button
                  onClick={() => onSelectTask(log.task_id!)}
                  className="text-[#5f5a52] hover:text-teal-600 font-mono truncate"
                >
                  {shortId(log.task_id)}
                </button>
              )}
              {log.agent_id && (
                <button
                  onClick={() => onSelectAgent(log.agent_id!)}
                  className="text-[#5f5a52] hover:text-[#174066] font-mono truncate"
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
          {logs.length === 0 && (
            <div className="text-xs text-[#5f5a52]/50">{t("dash.noActivity")}</div>
          )}
        </div>
      </div>
    </div>
  );
}
