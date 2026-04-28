import type { ReactNode, ComponentType } from "react";
import type { IconProps } from "@phosphor-icons/react";

interface Props {
  icon: ComponentType<IconProps>;
  message: string;
  children?: ReactNode;
}

export default function EmptyState({ icon: Icon, message, children }: Props) {
  return (
    <div
      className="animate-fade-in"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        padding: "40px 16px",
        textAlign: "center",
      }}
    >
      <Icon size={40} weight="thin" style={{ color: "var(--muted)", opacity: 0.4 }} />
      <p style={{ color: "var(--muted)", fontSize: 12, fontFamily: "var(--font-mono)" }}>
        {message}
      </p>
      {children}
    </div>
  );
}
