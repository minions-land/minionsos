/**
 * Agent identity derivation. Each AgentCard renders as its own instance.
 * `roleKey(id)` returns the visual bucket for color/icon/lane, and
 * `agentDisplayName` returns the instance's human label.
 */

export interface RoleBucket {
  key: string;
  label: string;
  color: string;
  colorRgb: string;
  accent: string;
  orbitIndex: number;
  baseOrbitPeriod: number;
}

export const ROLE_BUCKETS: Record<string, RoleBucket> = {
  gru: {
    key: "gru",
    label: "Gru",
    color: "#F59E0B",
    colorRgb: "245,158,11",
    accent: "var(--role-gru)",
    orbitIndex: 0,
    baseOrbitPeriod: 0,
  },
  review: {
    key: "review",
    label: "Review",
    color: "#3B82F6",
    colorRgb: "59,130,246",
    accent: "var(--role-review)",
    orbitIndex: 1,
    baseOrbitPeriod: 18,
  },
  expert: {
    key: "expert",
    label: "Expert",
    color: "#EAB308",
    colorRgb: "234,179,8",
    accent: "var(--role-gru)",
    orbitIndex: 2,
    baseOrbitPeriod: 22,
  },
  ethics: {
    key: "ethics",
    label: "Ethics",
    color: "#F43F5E",
    colorRgb: "244,63,94",
    accent: "var(--role-ethics)",
    orbitIndex: 3,
    baseOrbitPeriod: 26,
  },
  other: {
    key: "other",
    label: "Agent",
    color: "#64748B",
    colorRgb: "100,116,139",
    accent: "var(--role-other)",
    orbitIndex: 4,
    baseOrbitPeriod: 30,
  },
};

const LOOKUP: [string, string][] = [
  ["expert", "expert"],
  ["ethics", "ethics"],
  ["gru", "gru"],
  ["review", "review"],
];

export function roleKey(agentId: string): string {
  const s = agentId.toLowerCase();
  for (const [needle, key] of LOOKUP) {
    if (s.includes(needle)) return key;
  }
  return "other";
}

export function roleBucket(agentId: string): RoleBucket {
  return ROLE_BUCKETS[roleKey(agentId)] ?? ROLE_BUCKETS.other;
}

export function agentDisplayName(agentId: string, fallback?: string): string {
  // EACN agent ids are often already human-readable (e.g. "expert-math").
  // Fall back to the card's `name` if present, else id.
  if (fallback && fallback.trim().length > 0) return fallback;
  return agentId;
}

/** Short tag (e.g. `R-1`, `E-math`) for badge display when name is the full id. */
export function agentShortTag(agentId: string): string {
  const bucket = roleBucket(agentId);
  const letter = bucket.label[0];
  // Suffix after the role token if present.
  const s = agentId.toLowerCase();
  const idx = s.indexOf(bucket.key);
  let rest = idx >= 0 ? agentId.slice(idx + bucket.key.length) : "";
  rest = rest.replace(/^[-_:\s]+/, "");
  return rest ? `${letter}·${rest}` : letter;
}

export function bufferGlow(pending: number): { halo: number; speed: number } {
  if (pending <= 0) return { halo: 0, speed: 0 };
  if (pending <= 3) return { halo: 0.35, speed: 1.4 };
  if (pending <= 10) return { halo: 0.6, speed: 2.2 };
  if (pending <= 20) return { halo: 0.85, speed: 3.4 };
  return { halo: 1.1, speed: 4.8 };
}
