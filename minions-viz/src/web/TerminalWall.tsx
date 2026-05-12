import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentInfo } from "@shared/types";
import { roleBucket, ROLE_BUCKETS, agentShortTag } from "./roleIdentity";
import { subscribeRoleLog, unsubscribeRoleLog, useRoleLog } from "./store";

/**
 * Terminal grid, grouped by role bucket: each role bucket occupies one row,
 * with its instances laid out as equal-size panes.
 */
interface Props {
  agents: AgentInfo[];
}

export default function TerminalWall({ agents }: Props) {
  const rows = useMemo(() => {
    const m = new Map<string, AgentInfo[]>();
    for (const a of agents) {
      const k = roleBucket(a.agent_id).key;
      const arr = m.get(k) ?? [];
      arr.push(a);
      m.set(k, arr);
    }
    const keys = Array.from(m.keys()).sort(
      (a, b) =>
        (ROLE_BUCKETS[a]?.orbitIndex ?? 99) -
        (ROLE_BUCKETS[b]?.orbitIndex ?? 99),
    );
    return keys.map((k) => ({
      key: k,
      bucket: ROLE_BUCKETS[k] ?? ROLE_BUCKETS.other,
      items: m.get(k)!.sort((a, b) => a.agent_id.localeCompare(b.agent_id)),
    }));
  }, [agents]);

  if (agents.length === 0) {
    return (
      <div className="terminal-wall empty-wall">
        <div className="empty">No agent instances registered yet.</div>
      </div>
    );
  }

  return (
    <div className="terminal-wall">
      {rows.map((row) => (
        <div key={row.key} className="term-row">
          <div className="term-row-label" style={{ color: row.bucket.color }}>
            <span className="tint" style={{ background: row.bucket.color }} />
            {row.bucket.label}
            <span style={{ color: "var(--muted)", marginLeft: 8 }}>× {row.items.length}</span>
          </div>
          <div
            className="term-row-grid"
            style={{
              gridTemplateColumns: `repeat(${Math.min(row.items.length, 4)}, minmax(0, 1fr))`,
            }}
          >
            {row.items.map((a) => (
              <TerminalPane key={a.agent_id} agent={a} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TerminalPane({ agent }: { agent: AgentInfo }) {
  const bucket = useMemo(() => roleBucket(agent.agent_id), [agent.agent_id]);
  const role = bucket.key;
  const [paused, setPaused] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const buffer = useRoleLog(role);

  useEffect(() => {
    subscribeRoleLog(role);
    return () => {
      unsubscribeRoleLog(role);
    };
  }, [role]);

  useEffect(() => {
    if (paused || !bodyRef.current) return;
    const frame = requestAnimationFrame(() => {
      if (bodyRef.current) {
        bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [buffer, paused]);

  const lineCount = useMemo(
    () => (buffer.match(/\n/g)?.length ?? 0) + (buffer.length > 0 ? 1 : 0),
    [buffer],
  );

  return (
    <div className="term-pane">
      <header>
        <span className="swatch" style={{ background: bucket.color, color: bucket.color }} />
        <span className="title">
          <span style={{ color: bucket.color }}>{bucket.label}</span>
          <span style={{ color: "var(--muted)" }}> · {agent.name || agent.agent_id}</span>
        </span>
        <span className="meta">{agentShortTag(agent.agent_id)}</span>
        <span className="meta">{lineCount} ln</span>
        <button
          className="chip"
          style={{ height: 22, padding: "0 10px", fontSize: 10 }}
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
        >
          {paused ? "follow" : "pause"}
        </button>
      </header>
      <div className="term-body" ref={bodyRef}>
        {buffer || "(no log yet — will stream when role runs)"}
      </div>
    </div>
  );
}
