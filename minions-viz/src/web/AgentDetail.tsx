import type { AgentInfo, MosProject, Task } from "@shared/types";
import { roleBucket, agentShortTag } from "./roleIdentity";
import type { AgentActivity } from "./activity";

interface Props {
  agent: AgentInfo | null;
  project: MosProject | null;
  tasks: Task[];
  activity: Map<string, AgentActivity>;
  onClose: () => void;
}

export default function AgentDetail({ agent, project, tasks, activity, onClose }: Props) {
  if (!agent) return null;
  const bucket = roleBucket(agent.agent_id);
  const roleEntry = project?.active_roles.find(
    (r) =>
      agent.agent_id.toLowerCase().includes(r.name.toLowerCase()) ||
      (r.eacn_agent_id &&
        agent.agent_id.toLowerCase().includes(r.eacn_agent_id.toLowerCase())),
  );
  const act = activity.get(agent.agent_id);
  const myTasks = tasks.filter(
    (t) =>
      t.initiator_id === agent.agent_id ||
      t.results?.some((r) => r.agent_id === agent.agent_id) ||
      t.bids?.some((b) => b.agent_id === agent.agent_id),
  );

  return (
    <aside className="detail float-panel">
      <h4>
        <span className="accent" style={{ background: bucket.color, color: bucket.color }} />
        <span style={{ color: bucket.color }}>{bucket.label}</span>
        <span style={{ color: "var(--text)", marginLeft: 6 }}>
          · {agent.name || agent.agent_id}
        </span>
        <div className="spacer" style={{ flex: 1 }} />
        <button
          className="chip"
          onClick={onClose}
          aria-label="Close detail"
          style={{ height: 22, padding: "0 8px" }}
        >
          ✕
        </button>
      </h4>
      <div className="body">
        <dl>
          <dt>Tag</dt>
          <dd style={{ color: bucket.color }}>{agentShortTag(agent.agent_id)}</dd>
          <dt>Agent id</dt>
          <dd style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{agent.agent_id}</dd>
          <dt>State</dt>
          <dd>
            <span className={`badge ${act?.state ?? "idle"}`}>{act?.state ?? "idle"}</span>
            {act && act.pending > 0 && (
              <span
                className="badge"
                style={{
                  marginLeft: 6,
                  background: "rgba(251,191,36,0.18)",
                  color: "#fcd34d",
                }}
              >
                ● {act.pending} pending
              </span>
            )}
            {act && act.executing > 0 && (
              <span
                className="badge"
                style={{
                  marginLeft: 6,
                  background: "rgba(192,132,252,0.18)",
                  color: "#e9d5ff",
                }}
              >
                ▶ executing {act.executing}
              </span>
            )}
          </dd>
          <dt>Server</dt>
          <dd style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{agent.server_id}</dd>
          <dt>Reputation</dt>
          <dd>{(agent.reputation ?? 0).toFixed(3)}</dd>
          <dt>Balance</dt>
          <dd>
            {agent.balance?.available ?? 0} avail · {agent.balance?.frozen ?? 0} frozen
          </dd>
          <dt>Domains</dt>
          <dd>
            {agent.domains.length === 0 && <span style={{ color: "var(--muted)" }}>—</span>}
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {agent.domains.map((d) => (
                <span key={d} className="tag">{d}</span>
              ))}
            </div>
          </dd>
          {roleEntry && (
            <>
              <dt>Project</dt>
              <dd>
                <span className={`badge ${roleEntry.state}`}>{roleEntry.state}</span>
                {roleEntry.poll_interval && (
                  <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: 11 }}>
                    poll {roleEntry.poll_interval}
                  </span>
                )}
              </dd>
              {roleEntry.last_seen && (
                <>
                  <dt>Last seen</dt>
                  <dd style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    {roleEntry.last_seen}
                  </dd>
                </>
              )}
              {roleEntry.current_task && (
                <>
                  <dt>Current task</dt>
                  <dd style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    {roleEntry.current_task}
                  </dd>
                </>
              )}
            </>
          )}
          <dt>Tasks</dt>
          <dd>
            {myTasks.length} touched · {myTasks.filter((t) => t.status === "completed").length}{" "}
            completed
          </dd>
        </dl>
        {agent.description && (
          <p style={{ marginTop: 14, color: "var(--text-2)" }}>{agent.description}</p>
        )}
      </div>
    </aside>
  );
}
