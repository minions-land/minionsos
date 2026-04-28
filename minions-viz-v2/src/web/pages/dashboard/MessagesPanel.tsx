import { useState } from "react";
import { ChatCircle, ListBullets } from "@phosphor-icons/react";
import { useLimitPref } from "../../hooks/useLimitPref";
import { getRoleIdentity } from "../../utils/roleIdentity";
import { timeAgo, truncate, logColor, shortId } from "../../utils/format";
import EmptyState from "../../components/EmptyState";
import type { AgentInfo, LogEntry, Message } from "@shared/types";

interface Props {
  messages: Message[];
  logs: LogEntry[];
  agents: AgentInfo[];
}

type Tab = "messages" | "logs";

export default function MessagesPanel({ messages, logs, agents }: Props) {
  const [tab, setTab] = useState<Tab>("messages");
  const [msgLimit, setMsgLimit, msgOptions] = useLimitPref("viz.limit.msg", 20, [20, 50, 100]);
  const [logLimit, setLogLimit, logOptions] = useLimitPref("viz.limit.log", 50, [50, 100, 200]);

  const agentName = (id: string): string => {
    const agent = agents.find((a) => a.agent_id === id);
    return agent?.name ?? shortId(id);
  };

  const sorted = [...messages].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );
  const visibleMessages = sorted.slice(0, msgLimit);

  const sortedLogs = [...logs].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );
  const visibleLogs = sortedLogs.slice(0, logLimit);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => setTab("messages")}
            className={`pill ${tab === "messages" ? "pill-active" : ""}`}
            style={{
              cursor: "pointer",
              opacity: tab === "messages" ? 1 : 0.5,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <ChatCircle size={13} /> Messages
          </button>
          <button
            onClick={() => setTab("logs")}
            className={`pill ${tab === "logs" ? "pill-active" : ""}`}
            style={{
              cursor: "pointer",
              opacity: tab === "logs" ? 1 : 0.5,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <ListBullets size={13} /> Event Log
          </button>
        </div>

        {tab === "messages" ? (
          <select
            className="limit-select"
            value={msgLimit}
            onChange={(e) => setMsgLimit(Number(e.target.value))}
          >
            {msgOptions.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        ) : (
          <select
            className="limit-select"
            value={logLimit}
            onChange={(e) => setLogLimit(Number(e.target.value))}
          >
            {logOptions.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        )}
      </div>

      {tab === "messages" ? (
        <div className="scroll-region" style={{ maxHeight: 360 }}>
          {visibleMessages.length === 0 ? (
            <EmptyState icon={ChatCircle} message="No messages yet" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {visibleMessages.map((msg) => {
                const fromRole = getRoleIdentity(agentName(msg.from_agent_id));
                const toRole = getRoleIdentity(agentName(msg.to_agent_id));
                const preview = typeof msg.content === "string"
                  ? msg.content
                  : JSON.stringify(msg.content ?? "");
                return (
                  <div
                    key={msg.id}
                    className="animate-fade-in"
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      gap: 8,
                      padding: "4px 8px",
                      borderRadius: 4,
                    }}
                  >
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", flexShrink: 0 }}>
                      {timeAgo(msg.timestamp)}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: fromRole.color, fontWeight: 500, flexShrink: 0 }}>
                      {agentName(msg.from_agent_id)}
                    </span>
                    <span style={{ fontSize: 10, color: "var(--muted)", flexShrink: 0 }}>→</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: toRole.color, fontWeight: 500, flexShrink: 0 }}>
                      {agentName(msg.to_agent_id)}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text)", opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {truncate(preview, 120)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="scroll-region" style={{ maxHeight: 360 }}>
          {visibleLogs.length === 0 ? (
            <EmptyState icon={ListBullets} message="No events recorded" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {visibleLogs.map((entry, i) => (
                <div
                  key={`${entry.timestamp}-${i}`}
                  className="animate-fade-in"
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 8,
                    padding: "3px 8px",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                  }}
                >
                  <span style={{ fontSize: 10, color: "var(--muted)", flexShrink: 0 }}>
                    {timeAgo(entry.timestamp)}
                  </span>
                  <span className={logColor(entry.fn_name)} style={{ fontWeight: 500, flexShrink: 0 }}>
                    {entry.fn_name}
                  </span>
                  {entry.agent_id && (
                    <span style={{ color: getRoleIdentity(agentName(entry.agent_id)).color, flexShrink: 0 }}>
                      {agentName(entry.agent_id)}
                    </span>
                  )}
                  {entry.error && (
                    <span style={{ color: "var(--red)", opacity: 0.8 }}>
                      err: {truncate(entry.error, 60)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
