import { useEffect, useMemo, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import type { AgentInfo } from "@shared/types";
import { roleBucket, ROLE_BUCKETS, agentShortTag } from "./roleIdentity";
import { subscribeRoleLog, unsubscribeRoleLog, useRoleLog } from "./store";

/**
 * Terminal grid styled after Minions Code (SwiftTerm). All panes share the
 * same width regardless of how many panes a given role row has — so a single
 * Noter pane is the same width as a Coder pane in a four-coder row.
 *
 * We pick one global column count (= max instances in any one role) and lay
 * every row out on that grid. Rows with fewer panes leave the rightmost
 * columns empty rather than stretching their content.
 */
interface Props {
  agents: AgentInfo[];
}

const MAX_COLS = 3;

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

  const cols = useMemo(() => {
    const maxRow = rows.reduce((acc, r) => Math.max(acc, r.items.length), 1);
    return Math.min(MAX_COLS, Math.max(1, maxRow));
  }, [rows]);

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
            <span style={{ color: "var(--muted)", marginLeft: 8 }}>
              × {row.items.length}
            </span>
          </div>
          <div
            className="term-row-grid"
            style={{
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
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
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const writtenRef = useRef<number>(0);
  const buffer = useRoleLog(role);

  useEffect(() => {
    subscribeRoleLog(role);
    return () => {
      unsubscribeRoleLog(role);
    };
  }, [role]);

  useEffect(() => {
    if (!containerRef.current) return;
    const term = new Terminal({
      fontFamily:
        'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, "JetBrains Mono", "Liberation Mono", "Courier New", monospace',
      fontSize: 12,
      lineHeight: 1.3,
      letterSpacing: 0,
      cursorBlink: false,
      cursorStyle: "block",
      scrollback: 5000,
      convertEol: true,
      disableStdin: true,
      allowTransparency: false,
      theme: {
        background: "#0b0e15",
        foreground: "#d4d8e0",
        cursor: "#7a8aa8",
        selectionBackground: "rgba(125,146,180,0.35)",
        black: "#1a1f29",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#fbbf24",
        blue: "#60a5fa",
        magenta: "#c084fc",
        cyan: "#22d3ee",
        white: "#cbd5e1",
        brightBlack: "#475569",
        brightRed: "#fca5a5",
        brightGreen: "#86efac",
        brightYellow: "#fcd34d",
        brightBlue: "#93c5fd",
        brightMagenta: "#d8b4fe",
        brightCyan: "#67e8f9",
        brightWhite: "#f1f5f9",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    try {
      fit.fit();
    } catch {
      // first fit can throw if the container is 0x0; resize observer retries
    }
    termRef.current = term;
    fitRef.current = fit;

    const ro = new ResizeObserver(() => {
      try {
        fit.fit();
      } catch {
        // ignore intermediate resize hiccups
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
      writtenRef.current = 0;
    };
  }, []);

  useEffect(() => {
    const term = termRef.current;
    if (!term || paused) return;
    const written = writtenRef.current;
    if (buffer.length < written) {
      term.reset();
      term.write(buffer);
      writtenRef.current = buffer.length;
      return;
    }
    if (buffer.length > written) {
      term.write(buffer.slice(written));
      writtenRef.current = buffer.length;
    }
  }, [buffer, paused]);

  const lineCount = useMemo(
    () => (buffer.match(/\n/g)?.length ?? 0) + (buffer.length > 0 ? 1 : 0),
    [buffer],
  );

  return (
    <div className="term-pane" style={{ ["--pane-color" as string]: bucket.color }}>
      <header>
        <div className="term-traffic">
          <span className="dot dot-r" />
          <span className="dot dot-y" />
          <span className="dot dot-g" />
        </div>
        <span className="title">
          <span style={{ color: bucket.color, fontWeight: 600 }}>
            {bucket.label}
          </span>
          <span style={{ color: "var(--muted)" }}>
            {" "}· {agent.name || agent.agent_id}
          </span>
        </span>
        <span className="meta">{agentShortTag(agent.agent_id)}</span>
        <span className="meta">{lineCount} ln</span>
        <button
          className="term-action"
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
          title={paused ? "Resume tail" : "Pause tail"}
        >
          {paused ? "▶" : "❚❚"}
        </button>
      </header>
      <div className="term-body" ref={containerRef} />
    </div>
  );
}
