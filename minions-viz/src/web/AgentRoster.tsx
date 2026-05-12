import { useMemo } from "react";
import type { AgentInfo, MosProject, Task, Message } from "@shared/types";
import { roleBucket, ROLE_BUCKETS, agentShortTag } from "./roleIdentity";
import { isGruAgent } from "./store";
import { computeActivity } from "./activity";

interface Props {
  agents: AgentInfo[];
  project: MosProject | null;
  tasks: Task[];
  messages: Message[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onHover: (id: string | null) => void;
}

export default function AgentRoster({
  agents,
  project,
  tasks,
  messages,
  selectedId,
  onSelect,
  onHover,
}: Props) {
  const groups = useMemo(() => {
    const m = new Map<string, AgentInfo[]>();
    for (const a of agents) {
      const k = isGruAgent(a.agent_id, a.name) ? "gru" : roleBucket(a.agent_id).key;
      const arr = m.get(k) ?? [];
      arr.push(a);
      m.set(k, arr);
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => a.agent_id.localeCompare(b.agent_id));
    }
    const keys = Array.from(m.keys()).sort(
      (a, b) =>
        (ROLE_BUCKETS[a]?.orbitIndex ?? 99) -
        (ROLE_BUCKETS[b]?.orbitIndex ?? 99),
    );
    return keys.map((k) => ({
      key: k,
      bucket: ROLE_BUCKETS[k],
      items: m.get(k)!,
    }));
  }, [agents]);

  const activity = useMemo(
    () => computeActivity(agents, tasks, messages, project),
    [agents, tasks, messages, project],
  );

  return (
    <aside className="roster float-panel">
      <h4>
        <span className="accent" />
        Agents <span style={{ color: "var(--muted)" }}>· {agents.length}</span>
      </h4>
      <div className="list">
        {groups.length === 0 && (
          <div className="empty">No agents registered yet</div>
        )}
        {groups.map((g) => (
          <div key={g.key}>
            <div className="group" style={{ color: g.bucket.color }}>
              {g.bucket.label}
              <span style={{ color: "var(--muted)", marginLeft: 6 }}>× {g.items.length}</span>
            </div>
            {g.items.map((a) => {
              const act = activity.get(a.agent_id) ?? { state: "idle" as const, pending: 0, executing: 0, busyOn: null };
              const selected = selectedId === a.agent_id;
              return (
                <div
                  key={a.agent_id}
                  className={"row" + (selected ? " active" : "")}
                  onClick={() => onSelect(a.agent_id)}
                  onMouseEnter={() => onHover(a.agent_id)}
                  onMouseLeave={() => onHover(null)}
                >
                  <span
                    className="role-swatch"
                    style={{ background: g.bucket.color, color: g.bucket.color }}
                  />
                  <div style={{ overflow: "hidden" }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        overflow: "hidden",
                      }}
                    >
                      <span
                        style={{
                          color: g.bucket.color,
                          fontFamily: "var(--font-mono)",
                          fontSize: 10,
                        }}
                      >
                        {agentShortTag(a.agent_id)}
                      </span>
                      <span
                        style={{
                          overflow: "hidden",
                          whiteSpace: "nowrap",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {a.name || a.agent_id}
                      </span>
                    </div>
                    <div className="id">{a.agent_id}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                    {act.pending > 0 && (
                      <span
                        className="badge"
                        style={{
                          background: "rgba(251,191,36,0.18)",
                          color: "#fcd34d",
                          fontSize: 9,
                          padding: "1px 6px",
                        }}
                        title={`${act.pending} pending events`}
                      >
                        ● {act.pending}
                      </span>
                    )}
                    <span
                      className={`badge ${act.state}`}
                      style={{ fontSize: 9 }}
                      title={act.state === "active" ? "handling work" : "idle — waiting for events"}
                    >
                      {act.state}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </aside>
  );
}
