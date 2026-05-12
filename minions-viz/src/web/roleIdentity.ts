/**
 * Role identity derivation — the key fix.
 *
 * Prior versions keyed agents by role bucket, which collapsed multiple
 * instances (e.g. expert-math, expert-bio, reviewer-1, reviewer-2) into one
 * entity. We NEVER dedupe by role; each AgentCard is a first-class instance.
 *
 * `roleKey(id)` returns the role *bucket* (for color/icon/lane), and
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
  noter: {
    key: "noter",
    label: "Noter",
    color: "#06B6D4",
    colorRgb: "6,182,212",
    accent: "var(--role-noter)",
    orbitIndex: 1,
    baseOrbitPeriod: 14,
  },
  coder: {
    key: "coder",
    label: "Coder",
    color: "#10B981",
    colorRgb: "16,185,129",
    accent: "var(--role-coder)",
    orbitIndex: 2,
    baseOrbitPeriod: 18,
  },
  experimenter: {
    key: "experimenter",
    label: "Experimenter",
    color: "#F97316",
    colorRgb: "249,115,22",
    accent: "var(--role-exp)",
    orbitIndex: 3,
    baseOrbitPeriod: 22,
  },
  writer: {
    key: "writer",
    label: "Writer",
    color: "#A855F7",
    colorRgb: "168,85,247",
    accent: "var(--role-writer)",
    orbitIndex: 4,
    baseOrbitPeriod: 26,
  },
  reviewer: {
    key: "reviewer",
    label: "Reviewer",
    color: "#3B82F6",
    colorRgb: "59,130,246",
    accent: "var(--role-reviewer)",
    orbitIndex: 5,
    baseOrbitPeriod: 30,
  },
  expert: {
    key: "expert",
    label: "Expert",
    color: "#EAB308",
    colorRgb: "234,179,8",
    accent: "var(--role-gru)",
    orbitIndex: 6,
    baseOrbitPeriod: 34,
  },
  ethics: {
    key: "ethics",
    label: "Ethics",
    color: "#F43F5E",
    colorRgb: "244,63,94",
    accent: "var(--role-ethics)",
    orbitIndex: 7,
    baseOrbitPeriod: 38,
  },
  other: {
    key: "other",
    label: "Agent",
    color: "#64748B",
    colorRgb: "100,116,139",
    accent: "var(--role-other)",
    orbitIndex: 8,
    baseOrbitPeriod: 42,
  },
};

const LOOKUP: [string, string][] = [
  ["noter", "noter"],
  ["coder", "coder"],
  ["experimenter", "experimenter"],
  ["experiment", "experimenter"],
  ["exp-", "experimenter"],
  ["writer", "writer"],
  ["reviewer", "reviewer"],
  ["review", "reviewer"],
  ["expert", "expert"],
  ["ethics", "ethics"],
  ["gru", "gru"],
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
  // EACN agent ids are often already human-readable (e.g. "reviewer-1",
  // "expert-math"). Fall back to the card's `name` if present, else id.
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
