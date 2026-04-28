import { useEffect, useRef, useCallback } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";
import { getRoleIdentity } from "../../utils/roleIdentity";
import { ArrowDown } from "@phosphor-icons/react";

interface Props {
  port: number;
  gruId: string;
  roles: string[];
  mode: "single" | "split" | "grid";
}

interface TermPane {
  term: Terminal;
  fit: FitAddon;
  container: HTMLDivElement;
  lineCount: number;
}

export default function TerminalViewport({ port, gruId, roles, mode }: Props) {
  const panesRef = useRef<Map<string, TermPane>>(new Map());
  const wrapperRef = useRef<HTMLDivElement>(null);

  const mountTerminal = useCallback(
    (role: string, el: HTMLDivElement | null) => {
      const panes = panesRef.current;
      if (!el) {
        const existing = panes.get(role);
        if (existing) {
          existing.term.dispose();
          panes.delete(role);
        }
        return;
      }
      if (panes.has(role)) return;

      const identity = getRoleIdentity(role);
      const term = new Terminal({
        theme: {
          background: "#0A0E1A",
          foreground: "#CBD5E1",
          cursor: identity.color,
        },
        fontSize: 12,
        fontFamily: "var(--font-mono), monospace",
        disableStdin: true,
        cursorBlink: false,
        scrollback: 5000,
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(el);
      fit.fit();

      const pane: TermPane = { term, fit, container: el, lineCount: 0 };
      panes.set(role, pane);

      fetch(`/api/mos/project/${port}/role-log/${role}?gru=${gruId}&tail=500`)
        .then((r) => {
          if (!r.ok) throw new Error(`${r.status}`);
          return r.text();
        })
        .then((text) => {
          if (!panes.has(role)) return;
          const lines = text.split("\n");
          pane.lineCount = lines.length;
          term.write(text.replace(/\n/g, "\r\n"));
        })
        .catch(() => {
          if (!panes.has(role)) return;
          term.write("\x1b[90mNo log available\x1b[0m\r\n");
        });
    },
    [port, gruId],
  );

  // Resize observer
  useEffect(() => {
    const ro = new ResizeObserver(() => {
      panesRef.current.forEach((p) => {
        try { p.fit.fit(); } catch {}
      });
    });
    if (wrapperRef.current) ro.observe(wrapperRef.current);
    return () => ro.disconnect();
  }, []);

  // Cleanup all on unmount
  useEffect(() => {
    return () => {
      panesRef.current.forEach((p) => p.term.dispose());
      panesRef.current.clear();
    };
  }, []);

  const gridStyle = (): React.CSSProperties => {
    if (mode === "single") return { display: "flex", flexDirection: "column", height: "100%" };
    if (mode === "split")
      return {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 8,
        height: "100%",
      };
    return {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
      gap: 8,
      height: "100%",
    };
  };

  return (
    <div ref={wrapperRef} style={{ flex: 1, overflow: "hidden", padding: 8, ...gridStyle() }}>
      {roles.map((role) => (
        <TerminalPane
          key={`${role}-${port}-${gruId}`}
          role={role}
          mountTerminal={mountTerminal}
          panesRef={panesRef}
        />
      ))}
    </div>
  );
}

function TerminalPane({
  role,
  mountTerminal,
  panesRef,
}: {
  role: string;
  mountTerminal: (role: string, el: HTMLDivElement | null) => void;
  panesRef: React.RefObject<Map<string, TermPane>>;
}) {
  const identity = getRoleIdentity(role);

  const scrollToBottom = () => {
    const pane = panesRef.current?.get(role);
    if (pane) pane.term.scrollToBottom();
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        flex: 1,
        borderRadius: 6,
        overflow: "hidden",
        border: "1px solid var(--line)",
        background: "#0A0E1A",
      }}
    >
      {/* Header bar */}
      <div
        style={{
          borderTop: `2px solid ${identity.color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "4px 10px",
          background: "var(--panel-bg)",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontSize: 11,
              fontFamily: "var(--font-mono)",
              color: identity.color,
              fontWeight: 600,
            }}
          >
            {identity.label}
          </span>
          <span
            style={{
              fontSize: 9,
              fontFamily: "var(--font-mono)",
              color: "var(--muted)",
              background: "rgba(255,255,255,0.05)",
              padding: "1px 6px",
              borderRadius: 3,
            }}
          >
            READ-ONLY
          </span>
        </div>
        <button
          onClick={scrollToBottom}
          title="Scroll to bottom"
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 2,
            display: "flex",
            alignItems: "center",
          }}
        >
          <ArrowDown size={14} color="var(--muted)" />
        </button>
      </div>
      {/* Terminal container */}
      <div
        ref={(el) => mountTerminal(role, el)}
        style={{ flex: 1, minHeight: 0, padding: "4px 0" }}
      />
    </div>
  );
}
