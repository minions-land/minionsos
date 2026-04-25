import { useEffect, useRef, useState } from "react";

export interface Toast {
  id: number;
  message: string;
  type: "info" | "success" | "warning" | "error";
  timestamp: number;
}

const COLORS = {
  info: "border-[#174066] bg-[rgba(23,64,102,0.08)] text-[#174066]",
  success: "border-teal-600 bg-[rgba(15,118,110,0.08)] text-teal-700",
  warning: "border-[#df6d2d] bg-[rgba(223,109,45,0.08)] text-[#df6d2d]",
  error: "border-red-500 bg-red-50 text-red-600",
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
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto border-l-4 rounded-xl px-4 py-2.5 text-xs font-medium shadow-lg backdrop-blur-sm animate-slide-in ${COLORS[t.type]}`}
          style={{ boxShadow: "0 20px 60px rgba(32,24,12,0.08)" }}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
