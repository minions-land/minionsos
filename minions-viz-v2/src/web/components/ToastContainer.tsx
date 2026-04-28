import { useEffect, useRef, useState } from "react";

export interface Toast {
  id: number;
  message: string;
  type: "info" | "success" | "warning" | "error";
  timestamp: number;
}

const TYPE_COLORS: Record<Toast["type"], { border: string; accent: string; icon: string }> = {
  info:    { border: "var(--role-noter)",       accent: "rgba(6,182,212,0.15)",   icon: "i" },
  success: { border: "var(--status-completed)", accent: "rgba(5,150,105,0.15)",   icon: "✓" },
  warning: { border: "var(--role-gru)",         accent: "rgba(245,158,11,0.15)",  icon: "!" },
  error:   { border: "var(--status-error)",     accent: "rgba(220,38,38,0.15)",   icon: "✕" },
};

let _addToast: ((msg: string, type?: Toast["type"]) => void) | null = null;

export function toast(msg: string, type: Toast["type"] = "info") {
  _addToast?.(msg, type);
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);

  useEffect(() => {
    _addToast = (message, type = "info") => {
      const id = ++idRef.current;
      setToasts((prev) => [...prev.slice(-2), { id, message, type, timestamp: Date.now() }]);
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
    };
    return () => { _addToast = null; };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-20 right-4 flex flex-col gap-2 pointer-events-none"
      style={{ zIndex: "var(--z-toast)" }}
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((t) => {
        const c = TYPE_COLORS[t.type];
        return (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto animate-slide-up"
            style={{
              background: "var(--panel-bg)",
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              borderLeft: `3px solid ${c.border}`,
              border: `1px solid var(--line)`,
              borderLeftColor: c.border,
              borderLeftWidth: 3,
              borderRadius: "var(--radius-xs)",
              padding: "10px 14px",
              fontSize: 12,
              fontFamily: "var(--font-mono)",
              color: "var(--text-2)",
              boxShadow: "var(--shadow-panel)",
              display: "flex",
              alignItems: "center",
              gap: 8,
              maxWidth: 340,
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                flexShrink: 0,
                width: 18,
                height: 18,
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                background: c.accent,
                color: c.border,
              }}
              aria-hidden="true"
            >
              {c.icon}
            </span>
            {t.message}
          </div>
        );
      })}
    </div>
  );
}
