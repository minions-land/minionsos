import React from "react";
import {
  Crown,
  Eye,
  CodeBlock,
  Flask,
  PenNib,
  MagnifyingGlass,
  Scales,
} from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";
import { getRoleIdentity } from "../../utils/roleIdentity";

const ICON_MAP: Record<string, React.ComponentType<IconProps>> = {
  Crown,
  Eye,
  CodeBlock,
  Flask,
  PenNib,
  MagnifyingGlass,
  Scales,
};

interface Props {
  roleKey: string;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  state: "active" | "sleeping" | "dismissed";
  hovered: boolean;
  bufferCount: number;
  nodeAlpha: number;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export const PlanetNode = React.memo(function PlanetNode({
  roleKey,
  x,
  y,
  scale,
  opacity,
  state,
  hovered,
  bufferCount,
  nodeAlpha,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: Props) {
  const role = getRoleIdentity(roleKey);
  const Icon = ICON_MAP[role.icon] ?? Eye;
  const baseSize = 48;
  const size = baseSize * scale;
  const half = size / 2;
  const hoverScale = hovered ? 1.15 : 1;
  const finalOpacity = opacity * nodeAlpha;

  const isDismissed = state === "dismissed";
  const isSleeping = state === "sleeping";

  // Glow intensity
  let glowSpread: string;
  if (isDismissed) {
    glowSpread = "none";
  } else if (hovered) {
    glowSpread = `0 0 24px 8px rgba(${role.colorRgb},0.55), 0 0 48px 12px rgba(${role.colorRgb},0.2)`;
  } else if (isSleeping) {
    glowSpread = `0 0 10px 3px rgba(${role.colorRgb},0.2)`;
  } else {
    glowSpread = `0 0 16px 5px rgba(${role.colorRgb},0.35), 0 0 32px 8px rgba(${role.colorRgb},0.12)`;
  }

  return (
    <div
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        position: "absolute",
        left: x - half,
        top: y - half,
        width: size,
        height: size,
        pointerEvents: "auto",
        cursor: "pointer",
        opacity: finalOpacity,
        transform: `scale(${hoverScale})`,
        transition: "transform 0.2s ease, opacity 0.4s ease, box-shadow 0.4s ease",
      }}
    >
      {/* Planet body */}
      <div
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: isDismissed
            ? "transparent"
            : `radial-gradient(circle, rgba(${role.colorRgb},0.2) 0%, rgba(${role.colorRgb},0.05) 70%, transparent 100%)`,
          border: isDismissed
            ? `1.5px dashed rgba(${role.colorRgb},0.2)`
            : `1.5px solid rgba(${role.colorRgb},0.3)`,
          boxShadow: glowSpread,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          animation: isSleeping ? "pulse-slow 4s ease-in-out infinite" : undefined,
          transition: "box-shadow 0.4s ease, border 0.3s ease, background 0.3s ease",
        }}
      >
        <Icon
          size={Math.round(size * 0.45)}
          weight={isDismissed ? "thin" : "regular"}
          color={role.color}
          style={{ opacity: isDismissed ? 0.3 : 1 }}
        />
      </div>

      {/* Buffer count badge */}
      {bufferCount > 0 && (
        <div
          style={{
            position: "absolute",
            top: -2,
            right: -2,
            minWidth: 16,
            height: 16,
            borderRadius: 8,
            background: `rgba(${role.colorRgb},0.85)`,
            color: "#000",
            fontSize: 9,
            fontFamily: "var(--font-mono)",
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 4px",
            lineHeight: 1,
          }}
        >
          {bufferCount}
        </div>
      )}

      {/* Role label */}
      <div
        style={{
          position: "absolute",
          top: size + 3,
          left: "50%",
          transform: "translateX(-50%)",
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 9,
            color: isDismissed ? "var(--muted)" : role.color,
            opacity: isDismissed ? 0.4 : 0.85,
            transition: "color 0.3s ease, opacity 0.3s ease",
          }}
        >
          {role.label}
        </span>
      </div>
    </div>
  );
});
