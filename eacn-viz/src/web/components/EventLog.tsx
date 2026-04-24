import { useState, useMemo } from "react";
import type { LogEntry } from "@shared/types";
import { logColor, timeAgo, shortId } from "../utils/format";
import { useI18n } from "../i18n";

interface Props {
  logs: LogEntry[];
}

export default function EventLog({ logs }: Props) {
  const { t, locale } = useI18n();
  const [fnFilter, setFnFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [taskFilter, setTaskFilter] = useState("");

  const filtered = useMemo(() => {
    return logs.filter((l) => {
      if (fnFilter && !l.fn_name.toLowerCase().includes(fnFilter.toLowerCase())) return false;
      if (agentFilter && l.agent_id !== agentFilter && !l.agent_id?.includes(agentFilter)) return false;
      if (taskFilter && l.task_id !== taskFilter && !l.task_id?.includes(taskFilter)) return false;
      return true;
    });
  }, [logs, fnFilter, agentFilter, taskFilter]);

  return (
    <div className="h-full flex flex-col">
      {/* Filters */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(23,23,23,0.08)] shrink-0 bg-[rgba(249,244,234,0.5)]">
        <input
          type="text"
          placeholder={t("log.eventType")}
          value={fnFilter}
          onChange={(e) => setFnFilter(e.target.value)}
          className="eacn-input w-36 text-xs !py-1.5 !px-3"
        />
        <input
          type="text"
          placeholder="Agent ID"
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="eacn-input w-36 text-xs !py-1.5 !px-3"
        />
        <input
          type="text"
          placeholder="Task ID"
          value={taskFilter}
          onChange={(e) => setTaskFilter(e.target.value)}
          className="eacn-input w-36 text-xs !py-1.5 !px-3"
        />
        <span className="text-xs text-[#5f5a52] ml-auto font-mono">{filtered.length} {t("log.entries")}</span>
      </div>

      {/* Log entries */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs">
        <table className="w-full">
          <thead>
            <tr className="text-[#5f5a52] text-left">
              <th className="pb-2 pr-3 w-20 font-medium">{t("log.time")}</th>
              <th className="pb-2 pr-3 w-44 font-medium">{t("log.event")}</th>
              <th className="pb-2 pr-3 w-36 font-medium">Task</th>
              <th className="pb-2 pr-3 w-36 font-medium">Agent</th>
              <th className="pb-2 font-medium">{t("log.details")}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((log, i) => (
              <tr key={i} className="border-t border-[rgba(23,23,23,0.06)] hover:bg-[rgba(23,23,23,0.03)]">
                <td className="py-1.5 pr-3 text-[#5f5a52]/60 whitespace-nowrap">
                  {timeAgo(log.timestamp, locale)}
                </td>
                <td className={`py-1.5 pr-3 font-medium ${logColor(log.fn_name)}`}>
                  {log.fn_name}
                </td>
                <td className="py-1.5 pr-3 text-[#5f5a52]">
                  {log.task_id ? shortId(log.task_id) : "—"}
                </td>
                <td className="py-1.5 pr-3 text-[#5f5a52]">
                  {log.agent_id ? shortId(log.agent_id) : "—"}
                </td>
                <td className="py-1.5 text-[#5f5a52]/60 truncate max-w-xs">
                  {log.error ? (
                    <span className="text-red-500">{log.error}</span>
                  ) : Object.keys(log.args).length > 0 ? (
                    JSON.stringify(log.args)
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
