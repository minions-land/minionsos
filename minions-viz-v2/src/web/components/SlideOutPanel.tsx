import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";

interface Props {
  open: boolean;
  onClose: () => void;
  accentColor?: string;
  children: React.ReactNode;
}

export default function SlideOutPanel({ open, onClose, accentColor = "var(--role-noter)", children }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: "var(--z-modal)",
        display: "flex",
        justifyContent: "flex-end",
      }}
    >
      {/* Scrim */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.4)",
          animation: "fade-in 200ms var(--ease-out)",
        }}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "relative",
          width: "min(420px, 90vw)",
          height: "100%",
          background: "var(--panel-bg)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          borderLeft: `2px solid ${accentColor}`,
          overflowY: "auto",
          animation: "slide-in 350ms var(--ease-out)",
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close panel"
          style={{
            position: "sticky",
            top: 12,
            float: "right",
            marginRight: 12,
            width: 28,
            height: 28,
            display: "grid",
            placeItems: "center",
            borderRadius: "var(--radius-xs)",
            border: "1px solid var(--line)",
            background: "var(--surface)",
            color: "var(--muted)",
            cursor: "pointer",
            zIndex: 2,
            transition: `color 150ms var(--ease-out)`,
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--text)"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--muted)"; }}
        >
          <X size={14} />
        </button>
        {children}
      </div>
    </div>
  );
}
