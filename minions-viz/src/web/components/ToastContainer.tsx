import { useEffect, useRef, useState } from "react";

export interface Toast {
  id: number;
  message: string;
  type: "info" | "success" | "warning" | "error";
  timestamp: number;
}

const STYLES: Record<Toast["type"], { border: string; bg: string; text: string; icon: string }> = {
  info:    { border: "var(--accent-3)",       bg: "rgba(23,64,102,0.08)",   text: "var(--accent-3)",       icon: "ℹ" },
  success: { border: "var(--status-completed)", bg: "rgba(5,150,105,0.08)",  text: "var(--status-completed)", icon: "✓" },
  warning: { border: "var(--accent-2)",        bg: "rgba(223,109,45,0.08)", text: "var(--accent-2)",        icon: "!" },
  error:   { border: "var(--status-error)",    bg: "rgba(220,38,38,0.08)",  text: "var(--status-error)",    icon: "✕" },
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
      setToasts((prev) => [...prev.slice(-4), { id, message, type, timestamp: Date.now() }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    };
    return () => { _addToast = null; };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((t) => {
        const s = STYLES[t.type];
        return (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto border-l-4 rounded-xl px-4 py-2.5 text-xs font-medium shadow-lg backdrop-blur-sm animate-slide-in flex items-center gap-2"
            style={{
              borderLeftColor: s.border,
              background: s.bg,
              color: s.text,
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <span className="font-mono text-[11px] shrink-0" aria-hidden="true">{s.icon}</span>
            {t.message}
          </div>
        );
      })}
    </div>
  );
}
