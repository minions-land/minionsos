export interface RoleIdentity {
  key: string;
  label: string;
  color: string;
  colorRgb: string;
  icon: string;
  avatarPath: string;
  orbitIndex: number;
  baseOrbitPeriod: number;
  activeAnimation: string;
}

export const ROLES: Record<string, RoleIdentity> = {
  gru:          { key: "gru",          label: "Gru",          color: "#F59E0B", colorRgb: "245,158,11",  icon: "Crown",           avatarPath: "M12 2l3 6 3-2v8l-3 2-3-2-3 2-3-2V6l3 2z",                                                                    orbitIndex: 0, baseOrbitPeriod: 0,  activeAnimation: "corona-pulse" },
  noter:        { key: "noter",        label: "Noter",        color: "#06B6D4", colorRgb: "6,182,212",   icon: "Eye",             avatarPath: "M12 4C7 4 2.7 8.7 2 12c.7 3.3 5 8 10 8s9.3-4.7 10-8c-.7-3.3-5-8-10-8zm0 13a5 5 0 110-10 5 5 0 010 10z",       orbitIndex: 1, baseOrbitPeriod: 12, activeAnimation: "scan-ripple" },
  coder:        { key: "coder",        label: "Coder",        color: "#10B981", colorRgb: "16,185,129",  icon: "CodeBlock",       avatarPath: "M8 5l-5 7 5 7M16 5l5 7-5 7",                                                                                    orbitIndex: 2, baseOrbitPeriod: 18, activeAnimation: "code-orbit" },
  experimenter: { key: "experimenter", label: "Experimenter", color: "#F97316", colorRgb: "249,115,22",  icon: "Flask",           avatarPath: "M9 3h6v5l4 9H5l4-9V3z",                                                                                         orbitIndex: 3, baseOrbitPeriod: 24, activeAnimation: "bubble-rise" },
  writer:       { key: "writer",       label: "Writer",       color: "#A855F7", colorRgb: "168,85,247",  icon: "PenNib",          avatarPath: "M3 21l1.5-4.5L17.3 3.8a1.5 1.5 0 012.1 0l.8.8a1.5 1.5 0 010 2.1L7.5 19.5z",                                    orbitIndex: 4, baseOrbitPeriod: 30, activeAnimation: "ink-flow" },
  reviewer:     { key: "reviewer",     label: "Reviewer",     color: "#3B82F6", colorRgb: "59,130,246",  icon: "MagnifyingGlass", avatarPath: "M10 2a8 8 0 105.3 14l4.4 4.3 1.4-1.4-4.3-4.4A8 8 0 0010 2zm0 2a6 6 0 110 12 6 6 0 010-12z",                    orbitIndex: 5, baseOrbitPeriod: 36, activeAnimation: "sweep-scan" },
  ethics:       { key: "ethics",       label: "Ethics",       color: "#F43F5E", colorRgb: "244,63,94",   icon: "Scales",          avatarPath: "M12 2v4m0 12v4M5 12H2m20 0h-3M7.5 7.5l-2-2m13 13l-2-2M7.5 16.5l-2 2m13-13l-2 2",                               orbitIndex: 6, baseOrbitPeriod: 42, activeAnimation: "scale-oscillate" },
};

export function getRoleIdentity(agentId: string): RoleIdentity {
  const key = agentId.toLowerCase().replace(/[^a-z]/g, "");
  return ROLES[key] ?? {
    key: agentId, label: agentId, color: "#64748B", colorRgb: "100,116,139",
    icon: "Robot", avatarPath: "", orbitIndex: -1, baseOrbitPeriod: 20, activeAnimation: "none",
  };
}

export function bufferRingStyle(bufferCount: number): { thickness: number; color: string; speed: number } {
  if (bufferCount <= 0) return { thickness: 0, color: "transparent", speed: 0 };
  if (bufferCount <= 3) return { thickness: 3, color: "rgba(251,191,36,0.35)", speed: 8 };
  if (bufferCount <= 10) return { thickness: 6, color: "rgba(245,158,11,0.55)", speed: 5 };
  if (bufferCount <= 20) return { thickness: 10, color: "rgba(239,68,68,0.65)", speed: 3 };
  return { thickness: 14, color: "rgba(220,38,38,0.8)", speed: 1.5 };
}
