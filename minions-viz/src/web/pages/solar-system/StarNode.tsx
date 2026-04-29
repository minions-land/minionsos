import React from "react";
import { Crown } from "@phosphor-icons/react";
import { ROLES } from "../../utils/roleIdentity";

interface Props {
  x: number;
  y: number;
  projectName: string;
  active: boolean;
  onClick?: () => void;
}

const gru = ROLES.gru;

export const StarNode = React.memo(function StarNode({
  x,
  y,
  projectName,
  active,
  onClick,
}: Props) {
  const size = 80;
  const half = size / 2;

  return (
    <div
      onClick={onClick}
      style={{
        position: "absolute",
        left: x - half,
        top: y - half,
        width: size,
        height: size,
        pointerEvents: "auto",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {/* Glow ring + icon */}
      <div
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(${gru.colorRgb},0.25) 0%, rgba(${gru.colorRgb},0.05) 60%, transparent 80%)`,
          boxShadow: active
            ? `0 0 28px 8px rgba(${gru.colorRgb},0.5), 0 0 60px 16px rgba(${gru.colorRgb},0.2)`
            : `0 0 16px 4px rgba(${gru.colorRgb},0.25), 0 0 32px 8px rgba(${gru.colorRgb},0.1)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "box-shadow 0.6s ease",
        }}
      >
        <Crown size={32} weight="fill" color={gru.color} />
      </div>

      {/* Labels below */}
      <div
        style={{
          position: "absolute",
          top: size + 4,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 1,
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: gru.color,
            lineHeight: 1.2,
          }}
        >
          {projectName}
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 9,
            color: "var(--muted)",
            lineHeight: 1.2,
          }}
        >
          GRU
        </span>
      </div>
    </div>
  );
});
