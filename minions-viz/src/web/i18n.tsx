import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export type Locale = "en" | "zh";

const translations = {
  // Tabs
  "tab.dashboard": { en: "Overview", zh: "总览" },
  "tab.agents": { en: "Agents", zh: "智能体" },
  "tab.tasks": { en: "Task Board", zh: "任务看板" },
  "tab.tree": { en: "Task Tree", zh: "任务树" },
  "tab.network": { en: "Network", zh: "网络图" },
  "tab.logs": { en: "Event Log", zh: "事件日志" },

  // TopBar
  "topbar.search": { en: "Search", zh: "搜索" },
  "topbar.searchTitle": { en: "Global Search (⌘K)", zh: "全局搜索 (⌘K)" },
  "topbar.exportTitle": { en: "Export Snapshot JSON", zh: "导出快照 JSON" },
  "topbar.agents": { en: "Agents", zh: "智能体" },
  "topbar.tasks": { en: "Tasks", zh: "任务" },
  "topbar.lastUpdate": { en: "Last update", zh: "最后更新" },
  "topbar.connected": { en: "Connected", zh: "已连接" },
  "topbar.disconnected": { en: "Disconnected", zh: "断开" },
  "topbar.justNow": { en: "just now", zh: "刚刚" },
  "topbar.secsAgo": { en: "s ago", zh: "秒前" },
  "topbar.minsAgo": { en: "m ago", zh: "分钟前" },

  // Status labels
  "status.unclaimed": { en: "Unclaimed", zh: "待认领" },
  "status.bidding": { en: "Bidding", zh: "竞标中" },
  "status.awaiting_retrieval": { en: "Awaiting", zh: "待取回" },
  "status.completed": { en: "Completed", zh: "已完成" },
  "status.no_one_able": { en: "No One Able", zh: "无人可做" },

  // Bid status
  "bid.pending": { en: "Pending", zh: "待定" },
  "bid.executing": { en: "Executing", zh: "执行中" },
  "bid.accepted": { en: "Accepted", zh: "已接受" },
  "bid.rejected": { en: "Rejected", zh: "已拒绝" },
  "bid.waiting": { en: "Queued", zh: "排队中" },

  // Time ago
  "time.secsAgo": { en: "s ago", zh: "秒前" },
  "time.minsAgo": { en: "m ago", zh: "分钟前" },
  "time.hoursAgo": { en: "h ago", zh: "小时前" },
  "time.daysAgo": { en: "d ago", zh: "天前" },

  // Dashboard
  "dash.statusDist": { en: "Task Status Distribution", zh: "任务状态分布" },
  "dash.totalBudget": { en: "Total Budget", zh: "总预算" },
  "dash.totalAvailable": { en: "Available Balance", zh: "总可用余额" },
  "dash.totalFrozen": { en: "Frozen Balance", zh: "总冻结余额" },
  "dash.avgReputation": { en: "Avg Reputation", zh: "平均信誉" },
  "dash.totalBids": { en: "Total Bids", zh: "总竞标数" },
  "dash.totalResults": { en: "Total Results", zh: "总结果数" },
  "dash.domainDist": { en: "Domain Distribution", zh: "领域分布" },
  "dash.noDomains": { en: "No domain data", zh: "暂无领域数据" },
  "dash.clusterStatus": { en: "Cluster Status", zh: "集群状态" },
  "dash.mode": { en: "Mode", zh: "模式" },
  "dash.nodeId": { en: "Node ID", zh: "节点ID" },
  "dash.onlineMembers": { en: "Online Members", zh: "在线成员" },
  "dash.version": { en: "Version", zh: "版本" },
  "dash.domainCount": { en: "Domain Count", zh: "领域数" },
  "dash.depthDist": { en: "Task Depth Distribution", zh: "任务深度分布" },
  "dash.activeAgents": { en: "Active Agents", zh: "活跃智能体" },
  "dash.noAgents": { en: "No agent data", zh: "暂无智能体数据" },
  "dash.recentActivity": { en: "Recent Activity", zh: "最近活动" },
  "dash.noActivity": { en: "No activity records", zh: "暂无活动记录" },

  // Agents view
  "agents.searchPlaceholder": { en: "Search agents (name, domain, ID)", zh: "搜索智能体（名称、领域、ID）" },
  "agents.reputation": { en: "Reputation", zh: "信誉" },
  "agents.balance": { en: "Balance", zh: "余额" },
  "agents.initiated": { en: "Initiated", zh: "发起" },
  "agents.bidsLabel": { en: "Bids", zh: "竞标" },

  // Tasks board
  "tasks.filterDomain": { en: "Filter by domain", zh: "按领域过滤" },
  "tasks.hideAdj": { en: "Hide adjudication", zh: "隐藏仲裁任务" },

  // Event log
  "log.eventType": { en: "Event type", zh: "事件类型" },
  "log.entries": { en: "entries", zh: "条" },
  "log.time": { en: "Time", zh: "时间" },
  "log.event": { en: "Event", zh: "事件" },
  "log.details": { en: "Details", zh: "详情" },

  // Network graph
  "net.hideCompleted": { en: "Hide completed", zh: "隐藏已完成" },
  "net.hideAdj": { en: "Hide adjudication", zh: "隐藏仲裁" },
  "net.connections": { en: "connections", zh: "连接" },
  "net.truncated": { en: "showing first {n} active tasks", zh: "仅显示前 {n} 个活跃任务" },
  "net.initiate": { en: "Initiate", zh: "发起" },
  "net.bid": { en: "Bid", zh: "竞标" },
  "net.result": { en: "Result", zh: "结果" },
  "net.noData": { en: "No network data", zh: "暂无网络关系数据" },

  // Task tree
  "tree.nodes": { en: "nodes", zh: "节点" },
  "tree.edges": { en: "edges", zh: "边" },
  "tree.noData": { en: "No task tree (no parent/child relationships)", zh: "暂无任务树（没有 parent/child 关系的任务）" },

  // Task node
  "node.adjudication": { en: "Adj", zh: "仲裁" },

  // Agent detail
  "detail.basicInfo": { en: "Basic Info", zh: "基本信息" },
  "detail.repEcon": { en: "Reputation & Economy", zh: "信誉 & 经济" },
  "detail.repScore": { en: "Reputation", zh: "信誉分" },
  "detail.balanceLabel": { en: "Balance", zh: "余额" },
  "detail.frozen": { en: "Frozen", zh: "冻结" },
  "detail.domains": { en: "Domains", zh: "领域" },
  "detail.skills": { en: "Skills", zh: "技能" },
  "detail.tasksInitiated": { en: "Tasks Initiated", zh: "发起的任务" },
  "detail.tasksBidOn": { en: "Bids Placed", zh: "参与竞标" },
  "detail.recentActivity": { en: "Recent Activity", zh: "最近活动" },
  "detail.noActivity": { en: "No activity records", zh: "暂无活动记录" },

  // Task detail
  "taskDetail.budget": { en: "Budget", zh: "预算" },
  "taskDetail.remaining": { en: "Remaining", zh: "剩余" },
  "taskDetail.bidsLabel": { en: "Bids", zh: "竞标" },
  "taskDetail.maxConcurrent": { en: "Max concurrent", zh: "最大并发" },
  "taskDetail.results": { en: "Results", zh: "结果" },
  "taskDetail.selected": { en: "Selected", zh: "已选定" },
  "taskDetail.notSelected": { en: "Not selected", zh: "未选定" },
  "taskDetail.initiator": { en: "Initiator", zh: "发起者" },
  "taskDetail.description": { en: "Description", zh: "描述" },
  "taskDetail.taskTree": { en: "Task Tree", zh: "任务树" },
  "taskDetail.parentTask": { en: "Parent task", zh: "父任务" },
  "taskDetail.bidList": { en: "Bid List", zh: "竞标列表" },
  "taskDetail.confidence": { en: "Conf", zh: "信心" },
  "taskDetail.price": { en: "Price", zh: "报价" },
  "taskDetail.adjudication": { en: "Adjudication", zh: "仲裁" },
  "taskDetail.score": { en: "Score", zh: "分数" },
  "taskDetail.discussions": { en: "Discussions", zh: "讨论" },

  // Global search
  "search.placeholder": { en: "Search agents, tasks, logs... (ID, name, domain, description)", zh: "搜索智能体、任务、日志...（ID、名称、领域、描述）" },
  "search.noResults": { en: "No matching results", zh: "没有找到匹配的结果" },
  "search.resultsFooter": { en: "results · click to select · ESC to close", zh: "条结果 · 点击选择 · ESC 关闭" },

  // Toast messages
  "toast.newTasks": { en: " new task(s)", zh: " 个新任务" },
  "toast.newAgents": { en: " new agent(s) online", zh: " 个新智能体上线" },
  "toast.disconnected": { en: "EACN node disconnected", zh: "EACN 节点连接断开" },
  "toast.reconnected": { en: "EACN node reconnected", zh: "EACN 节点已重新连接" },
  "toast.exported": { en: "Snapshot exported", zh: "快照已导出" },

  // Setup overlay
  "setup.title": { en: "Connect to EACN Network", zh: "连接 EACN 网络" },
  "setup.desc": { en: "Enter your EACN proxy endpoint (HTTPS required for browser access).", zh: "输入 EACN 代理端点（浏览器访问需要 HTTPS）。" },
  "setup.placeholder": { en: "https://your-proxy.workers.dev", zh: "https://your-proxy.workers.dev" },
  "setup.connect": { en: "Connect", zh: "连接" },
  "setup.hint": { en: "The EACN API must be accessible via HTTPS with CORS enabled. Deploy the included Cloudflare Worker proxy if your node only supports HTTP.", zh: "EACN API 需要通过 HTTPS 访问并启用 CORS。如果节点只支持 HTTP，请部署项目内附带的 Cloudflare Worker 代理。" },
  "setup.loading": { en: "Connecting...", zh: "正在连接..." },
} as const;

type TranslationKey = keyof typeof translations;

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  toggleLocale: () => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue>(null!);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("en");

  const toggleLocale = useCallback(() => {
    setLocale((l) => (l === "en" ? "zh" : "en"));
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>): string => {
      const entry = translations[key];
      if (!entry) return key;
      let text: string = entry[locale];
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          text = text.replace(`{${k}}`, String(v));
        }
      }
      return text;
    },
    [locale],
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, toggleLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
