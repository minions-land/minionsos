import { useState, useMemo } from "react";
import type { LogEntry } from "@shared/types";
import { logColor, timeAgo, shortId } from "../utils/format";
import { useI18n } from "../i18n";
import { useLimitPref } from "../hooks/useLimitPref";

interface Props { logs: LogEntry[]; }

const LIMIT_OPTIONS = [50, 100, 200, 500];

export default function EventLog({ logs }: Props) {
  const { t, locale } = useI18n();
  const [fnFilter, setFnFilter]       = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [taskFilter, setTaskFilter]   = useState("");
  const [limit, setLimit]             = useLimitPref("viz.limit.eventlog", 100, LIMIT_OPTIONS);

  // newest-first, filtered, then limited
  const filtered = useMemo(() => {
    const reversed = [...logs].reverse();
    return reversed.filter((l) => {
      if (fnFilter    && !l.fn_name.toLowerCase().includes(fnFilter.toLowerCase()))    return false;
      if (agentFilter && l.agent_id !== agentFilter && !l.agent_id?.includes(agentFilter)) return false;
      if (taskFilter  && l.task_id  !== taskFilter  && !l.task_id?.includes(taskFilter))   return false;
      return true;
    }).slice(0, limit);
  }, [logs, fnFilter, agentFilter, taskFilter, limit]);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="toolbar shrink-0">
        <input
          type="text"
          placeholder={t("log.eventType")}
          value={fnFilter}
          onChange={(e) => setFnFilter(e.target.value)}
          className="eacn-input w-32"
        />
        <input
          type="text"
          placeholder="Agent ID"
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="eacn-input w-32"
        />
        <input
          type="text"
          placeholder="Task ID"
          value={taskFilter}
          onChange={(e) => setTaskFilter(e.target.value)}
          className="eacn-input w-32"
        />
        <div className="flex-1" />
        <span className="text-[10px] text-[var(--muted)] font-mono">{filtered.length} {t("log.entries")}</span>
        <label className="flex items-center gap-1.5 text-[10px] text-[var(--muted)]">
          Show
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="limit-select"
          >
            {LIMIT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
      </div>

      {/* Log table — scrollable body, sticky header */}
      <div className="flex-1 overflow-hidden">
        {filtered.length === 0 ? (
          <div className="empty-state h-full">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span>No events match your filters</span>
          </div>
        ) : (
          <div className="h-full overflow-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-20">{t("log.time")}</th>
                  <th className="w-44">{t("log.event")}</th>
                  <th className="w-32">Task</th>
                  <th className="w-32">Agent</th>
                  <th>{t("log.details")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((log, i) => (
                  <tr key={i}>
                    <td className="text-[var(--muted-2)] whitespace-nowrap font-mono text-[10px]">
                      {timeAgo(log.timestamp, locale)}
                    </td>
                    <td className={`font-medium font-mono text-[10px] ${logColor(log.fn_name)}`}>
                      {log.fn_name}
                    </td>
                    <td className="text-[var(--muted)] font-mono text-[10px]">
                      {log.task_id ? shortId(log.task_id) : <span className="opacity-30">—</span>}
                    </td>
                    <td className="text-[var(--muted)] font-mono text-[10px]">
                      {log.agent_id ? shortId(log.agent_id) : <span className="opacity-30">—</span>}
                    </td>
                    <td className="text-[var(--muted-2)] truncate max-w-xs text-[10px]">
                      {log.error ? (
                        <span className="text-red-500">{log.error}</span>
                      ) : Object.keys(log.args).length > 0 ? (
                        JSON.stringify(log.args)
                      ) : (
                        <span className="opacity-30">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
