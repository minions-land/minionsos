import { useRef, useEffect, useState } from "react";
import { Planet, ChartBar, Terminal } from "@phosphor-icons/react";

export type Page = "solar" | "dashboard" | "terminal";

interface Props {
  page: Page;
  onNavigate: (p: Page) => void;
}

const ITEMS: { key: Page; label: string; Icon: typeof Planet }[] = [
  { key: "solar",     label: "Solar System", Icon: Planet },
  { key: "dashboard", label: "Dashboard",    Icon: ChartBar },
  { key: "terminal",  label: "Terminal",     Icon: Terminal },
];

export default function BottomDock({ page, onNavigate }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [indicatorX, setIndicatorX] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;
    const idx = ITEMS.findIndex((i) => i.key === page);
    const buttons = containerRef.current.querySelectorAll<HTMLButtonElement>("[data-dock-btn]");
    const btn = buttons[idx];
    if (btn) {
      const containerRect = containerRef.current.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      setIndicatorX(btnRect.left - containerRect.left + btnRect.width / 2 - 16);
    }
  }, [page]);

  return (
    <nav
      ref={containerRef}
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        height: 56,
        background: "rgba(10,14,26,0.92)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderTop: "1px solid var(--line)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 48,
        zIndex: "var(--z-sticky)",
      }}
      aria-label="Main navigation"
    >
      {/* Sliding active indicator */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: indicatorX,
          width: 32,
          height: 2,
          borderRadius: 1,
          background: "var(--role-gru)",
          boxShadow: "0 0 8px var(--role-gru)",
          transition: `left 300ms var(--ease-out)`,
        }}
        aria-hidden="true"
      />

      {ITEMS.map(({ key, label, Icon }) => {
        const active = page === key;
        return (
          <button
            key={key}
            data-dock-btn
            onClick={() => onNavigate(key)}
            aria-current={active ? "page" : undefined}
            aria-label={label}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 3,
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "4px 12px",
              opacity: active ? 1 : 0.4,
              transition: `opacity 200ms var(--ease-out)`,
            }}
            onMouseEnter={(e) => {
              if (!active) (e.currentTarget as HTMLElement).style.opacity = "0.7";
            }}
            onMouseLeave={(e) => {
              if (!active) (e.currentTarget as HTMLElement).style.opacity = "0.4";
            }}
          >
            <Icon
              size={24}
              weight={active ? "fill" : "regular"}
              style={{
                color: active ? "var(--role-gru)" : "var(--text-2)",
                filter: active ? "drop-shadow(0 0 6px var(--role-gru))" : "none",
                transition: `color 200ms var(--ease-out), filter 200ms var(--ease-out)`,
              }}
            />
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color: active ? "var(--text)" : "var(--muted)",
                transition: `color 200ms var(--ease-out)`,
              }}
            >
              {label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
