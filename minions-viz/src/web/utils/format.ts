import type { TaskStatus, BidStatus } from "@shared/types";
import type { Locale } from "../i18n";

const STATUS_LABELS: Record<TaskStatus, Record<Locale, string>> = {
  unclaimed: { en: "Unclaimed", zh: "待认领" },
  bidding: { en: "Bidding", zh: "竞标中" },
  awaiting_retrieval: { en: "Awaiting", zh: "待取回" },
  completed: { en: "Completed", zh: "已完成" },
  no_one_able: { en: "No One Able", zh: "无人可做" },
};

const BID_LABELS: Record<BidStatus, Record<Locale, string>> = {
  pending: { en: "Pending", zh: "待定" },
  executing: { en: "Executing", zh: "执行中" },
  accepted: { en: "Accepted", zh: "已接受" },
  rejected: { en: "Rejected", zh: "已拒绝" },
  waiting: { en: "Queued", zh: "排队中" },
};

export function statusColor(s: TaskStatus): string {
  const map: Record<TaskStatus, string> = {
    unclaimed: "bg-stone-400",
    bidding: "bg-teal-600",
    awaiting_retrieval: "bg-amber-500",
    completed: "bg-emerald-600",
    no_one_able: "bg-red-500",
  };
  return map[s] ?? "bg-stone-400";
}

export function statusLabel(s: TaskStatus, locale: Locale = "en"): string {
  return STATUS_LABELS[s]?.[locale] ?? s;
}

export function bidStatusColor(s: BidStatus): string {
  const map: Record<BidStatus, string> = {
    pending: "text-amber-600",
    executing: "text-teal-600",
    accepted: "text-emerald-600",
    rejected: "text-red-500",
    waiting: "text-stone-400",
  };
  return map[s] ?? "text-stone-400";
}

export function bidStatusLabel(s: BidStatus, locale: Locale = "en"): string {
  return BID_LABELS[s]?.[locale] ?? s;
}

export function tierBadge(tier: string): string {
  const map: Record<string, string> = {
    general: "bg-stone-500",
    expert: "bg-[#174066]",
    expert_general: "bg-[#1e5a8f]",
    tool: "bg-teal-600",
  };
  return map[tier] ?? "bg-stone-500";
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export function timeAgo(iso: string, locale: Locale = "en"): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return locale === "en" ? `${s}s ago` : `${s}秒前`;
  const m = Math.floor(s / 60);
  if (m < 60) return locale === "en" ? `${m}m ago` : `${m}分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return locale === "en" ? `${h}h ago` : `${h}小时前`;
  const d = Math.floor(h / 24);
  return locale === "en" ? `${d}d ago` : `${d}天前`;
}

export function logColor(fn: string): string {
  if (fn.includes("create_task")) return "text-teal-600";
  if (fn.includes("submit_bid")) return "text-[#174066]";
  if (fn.includes("submit_result")) return "text-purple-700";
  if (fn.includes("select_result")) return "text-emerald-600";
  if (fn.includes("reject") || fn.includes("timeout")) return "text-red-500";
  if (fn.includes("close")) return "text-[#df6d2d]";
  return "text-stone-500";
}

export function shortId(id: string): string {
  if (id.length <= 16) return id;
  return id.slice(0, 12) + "…";
}
