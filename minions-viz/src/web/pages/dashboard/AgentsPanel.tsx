import { Robot } from "@phosphor-icons/react";
import { getRoleIdentity } from "../../utils/roleIdentity";
import { shortId } from "../../utils/format";
import EmptyState from "../../components/EmptyState";
import type { AgentInfo } from "@shared/types";

interface Props {
  agents: AgentInfo[];
  onSelect: (id: string) => void;
}

export default function AgentsPanel({ agents, onSelect }: Props) {
  const sorted = [...agents].sort((a, b) => {
    const ra = getRoleIdentity(a.name);
    const rb = getRoleIdentity(b.name);
    if (ra.orbitIndex !== rb.orbitIndex) return ra.orbitIndex - rb.orbitIndex;
    return a.name.localeCompare(b.name);
  });

  return (
    <div>
      <div className="section-label">Agents</div>
      {sorted.length === 0 ? (
        <EmptyState icon={Robot} message="No agents registered" />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
          {sorted.map((agent) => {
            const role = getRoleIdentity(agent.name);
            return (
              <button
                key={agent.agent_id}
                onClick={() => onSelect(agent.agent_id)}
                className="surface-card animate-fade-in"
                style={{
                  borderLeft: `3px solid ${role.color}`,
                  textAlign: "left",
                  cursor: "pointer",
                  padding: "10px 12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  width: "100%",
                  background: "var(--surface)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      color: "var(--text)",
                      fontWeight: 500,
                    }}
                  >
                    {agent.name}
                  </span>
                  <span
                    className="badge"
                    style={{
                      fontSize: 9,
                      backgroundColor: `${role.color}22`,
                      color: role.color,
                    }}
                  >
                    {role.label}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                    {shortId(agent.agent_id)}
                  </span>
                  {agent.domains.slice(0, 3).map((d) => (
                    <span key={d} className="pill" style={{ fontSize: 9 }}>
                      {d}
                    </span>
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
