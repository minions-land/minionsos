# Phase 3: Dashboard + Terminal + Assembly (Tasks 9–12)

### Task 9: Dashboard Page

**Files:**
- Create: `minions-viz-v2/src/web/pages/dashboard/MetricBar.tsx`
- Create: `minions-viz-v2/src/web/pages/dashboard/AgentsPanel.tsx`
- Create: `minions-viz-v2/src/web/pages/dashboard/TasksPanel.tsx`
- Create: `minions-viz-v2/src/web/pages/dashboard/TaskTree.tsx`
- Create: `minions-viz-v2/src/web/pages/dashboard/MessagesPanel.tsx`
- Create: `minions-viz-v2/src/web/pages/dashboard/DashboardPage.tsx`

Reference: `docs/superpowers/specs/2026-04-28-minionsviz-v2/page-dashboard.md`

- [ ] **Step 1: Create MetricBar.tsx**

Horizontal strip of metric cards. Each card: role-colored Phosphor icon left, large mono value, small muted label. Staggered fade-in (50ms delay per card).

```tsx
import { Users, ListChecks, CheckCircle, CircleDashed, ChatDots, Plugs } from "@phosphor-icons/react";
import type { AgentInfo, Task } from "@shared/types";

interface Props { agents: AgentInfo[]; tasks: Task[]; messageCount: number; connected: boolean; }

export default function MetricBar({ agents, tasks, messageCount, connected }: Props) {
  const metrics = [
    { icon: Users, label: "Agents Online", value: agents.filter(a => a.status !== "dismissed").length, color: "var(--role-gru)" },
    { icon: ListChecks, label: "Total Tasks", value: tasks.length, color: "var(--role-coder)" },
    { icon: CheckCircle, label: "Completed", value: tasks.filter(t => t.status === "completed").length, color: "var(--status-completed)" },
    { icon: CircleDashed, label: "Open", value: tasks.filter(t => t.status === "unclaimed" || t.status === "bidding").length, color: "var(--status-unclaimed)" },
    { icon: ChatDots, label: "Messages", value: messageCount, color: "var(--role-writer)" },
    { icon: Plugs, label: "Backend", value: connected ? "UP" : "DOWN", color: connected ? "var(--status-completed)" : "var(--status-error)" },
  ];

  return (
    <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
      {metrics.map((m, i) => (
        <div key={m.label} className="metric-card animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
          <div className="flex items-center gap-2.5">
            <m.icon size={20} weight="duotone" color={m.color} />
            <div>
              <div className="font-mono text-lg font-semibold" style={{ color: "var(--text)" }}>{m.value}</div>
              <div className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{m.label}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create AgentsPanel.tsx**

Grid of agent cards (2-3 columns). Each card: role avatar (28px) + role-color left border, agent ID (mono), state badge, buffer count with mini ring indicator, last seen. Sorted: active → sleeping → dismissed. Card positions animate on reorder (350ms).

Click card → calls `onSelectAgent(agentId)` which opens the SlideOutPanel.

Use `getRoleIdentity()` from `roleIdentity.ts` for colors and icons. Buffer indicator: small colored dot matching `bufferRingStyle()` scale.

- [ ] **Step 3: Create TasksPanel.tsx**

Segmented control toggle: "Board" | "Tree".

Board view: 4 kanban columns (Unclaimed, Bidding, In Progress, Completed). Each column: header with count badge, scrollable card list. Cards show: `shortId(t.id)` mono, status pill, initiator avatar (tiny), description truncated 80 chars, domain tag pills. Newest-first within columns. Density control (10/20/50) via `useLimitPref`.

Click card → calls `onSelectTask(taskId)`.

- [ ] **Step 4: Create TaskTree.tsx**

Adapt from `minions-viz/src/web/components/TaskTree.tsx`. Uses `@xyflow/react` for hierarchical task tree. Restyle nodes with dark theme: node background `var(--surface)`, border color reflects task status, text `var(--text)`. Edge color `var(--line)`.

Click node → calls `onSelectTask(taskId)`.

- [ ] **Step 5: Create MessagesPanel.tsx**

Tabbed panel: "Messages" | "Event Log".

Messages tab: reverse-chronological list. Each row: timestamp (mono 10px), sender avatar (16px) + name colored by role, "→" arrow, receiver avatar + name, message preview truncated 120 chars. New messages animate in from top (slide-down + fade-in). Density: 20/50/100.

Event Log tab: adapt from `minions-viz/src/web/components/EventLog.tsx`. Restyle with dark theme. Mono font, compact rows, color-coded by event type. Auto-scroll with pause-on-hover. Density: 50/100/200.

- [ ] **Step 6: Create DashboardPage.tsx**

Page wrapper composing all panels:

```tsx
import { useStore } from "../../hooks/useStore";
import MetricBar from "./MetricBar";
import AgentsPanel from "./AgentsPanel";
import TasksPanel from "./TasksPanel";
import MessagesPanel from "./MessagesPanel";

interface Props {
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
}

export default function DashboardPage({ onSelectAgent, onSelectTask }: Props) {
  const store = useStore();
  return (
    <div className="page-container">
      <div className="max-w-[1600px] mx-auto space-y-5">
        <MetricBar agents={store.agents} tasks={store.tasks} messageCount={store.messages.length} connected={store.connected} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="panel-card"><AgentsPanel agents={store.agents} onSelect={onSelectAgent} /></div>
          <div className="panel-card"><TasksPanel tasks={store.tasks} agents={store.agents} onSelect={onSelectTask} /></div>
        </div>
        <div className="panel-card"><MessagesPanel messages={store.messages} logs={store.logs} agents={store.agents} /></div>
      </div>
    </div>
  );
}
```

Panels stagger in from bottom (100ms delay between panels).

- [ ] **Step 7: Commit**

```bash
git add minions-viz-v2/src/web/pages/dashboard/
git commit -m "feat(viz-v2): add EACN dashboard page with metrics, agents, tasks, messages"
```

---

### Task 10: Terminal Hub Page

**Files:**
- Create: `minions-viz-v2/src/web/pages/terminal/RoleSidebar.tsx`
- Create: `minions-viz-v2/src/web/pages/terminal/TerminalViewport.tsx`
- Create: `minions-viz-v2/src/web/pages/terminal/TerminalPage.tsx`

Reference: `docs/superpowers/specs/2026-04-28-minionsviz-v2/page-terminal-hub.md`

- [ ] **Step 1: Create RoleSidebar.tsx**

Narrow left panel (~180px). Lists all roles with: avatar (24px) + glow ring, role name (mono), state dot (pulsing if active), buffer badge. Click selects role for terminal display. Active selection has brighter bg + left border in role color. Sorted: active → sleeping → dismissed, animated reorder.

```tsx
import { getRoleIdentity, bufferRingStyle } from "../../utils/roleIdentity";
import * as Icons from "@phosphor-icons/react";
import type { AgentInfo } from "@shared/types";

interface Props {
  agents: AgentInfo[];
  selectedRole: string | null;
  onSelect: (role: string) => void;
}
```

- [ ] **Step 2: Create TerminalViewport.tsx**

Renders xterm.js terminal instances. Each terminal:
- Fetches initial content: `GET /api/mos/project/${port}/role-log/${role}?gru=${gruId}&tail=500`
- Subscribes to WebSocket `role-log` messages for live tail
- xterm.js theme: bg `#0A0E1A`, fg `#CBD5E1`, cursor role-color
- Top border 2px in role color, corner badge with role avatar + "READ-ONLY"
- Toolbar: role name, state badge, "Scroll to bottom" button, line count

View modes via prop `mode: "single" | "split" | "grid"`:
- Single: one terminal fills viewport
- Split: two terminals side-by-side (selected + one more)
- Grid: all active roles in auto-sized grid

```tsx
import { useEffect, useRef } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";
import { getRoleIdentity } from "../../utils/roleIdentity";

interface Props {
  port: number;
  gruId: string;
  roles: string[];
  mode: "single" | "split" | "grid";
}
```

On mount: create `Terminal` instance, attach `FitAddon`, open in container div, fetch initial log, write to terminal. On WebSocket `role-log` message matching this role: write new data to terminal.

On unmount: dispose terminal instance.

- [ ] **Step 3: Create TerminalPage.tsx**

Page wrapper:
- Left: `RoleSidebar`
- Right: `TerminalViewport`
- Toolbar above viewport: mode toggle (segmented control: Single/Split/Grid)
- Uses `useStore()` for agents list and connection state
- Empty states: no agents → EmptyState, backend down → EmptyState

```tsx
export default function TerminalPage() {
  const store = useStore();
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [mode, setMode] = useState<"single" | "split" | "grid">("single");
  const port = store.selectedPort;
  const gruId = store.selectedGruId ?? "";

  // Auto-select first active role if none selected
  useEffect(() => {
    if (!selectedRole && store.agents.length > 0) {
      setSelectedRole(store.agents[0].agent_id);
    }
  }, [store.agents, selectedRole]);

  // ...render sidebar + viewport
}
```

Page enter: sidebar slides in from left (300ms), viewport fades in (350ms).

- [ ] **Step 4: Commit**

```bash
git add minions-viz-v2/src/web/pages/terminal/
git commit -m "feat(viz-v2): add terminal hub page with xterm.js log viewer"
```

---

### Task 11: App Assembly + Routing

**Files:**
- Create: `minions-viz-v2/src/web/App.tsx`
- Modify: `minions-viz-v2/src/web/main.tsx`

- [ ] **Step 1: Create App.tsx**

Main app shell composing all pages:

```tsx
import { useState, useEffect, useCallback } from "react";
import { useStore, gruById, projectByPort, selectProject, selectGru } from "./hooks/useStore";
import type { Page } from "./components/BottomDock";
import TopBar from "./components/TopBar";
import BottomDock from "./components/BottomDock";
import GruPicker from "./components/GruPicker";
import ProjectPicker from "./components/ProjectPicker";
import SlideOutPanel from "./components/SlideOutPanel";
import TaskDetailModal from "./components/TaskDetailModal";
import GlobalSearch from "./components/GlobalSearch";
import ToastContainer from "./components/ToastContainer";
import SolarSystemPage from "./pages/solar-system/SolarSystemPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import TerminalPage from "./pages/terminal/TerminalPage";

export default function App() {
  const store = useStore();
  const [page, setPage] = useState<Page>("solar");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [showSearch, setShowSearch] = useState(false);

  const currentGru = gruById(store.grus, store.selectedGruId);
  const currentProject = currentGru ? projectByPort(currentGru.projects, store.selectedPort) : null;

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "Escape") {
        if (showSearch) { setShowSearch(false); return; }
        if (selectedTask) { setSelectedTask(null); return; }
        if (selectedAgent) { setSelectedAgent(null); return; }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setShowSearch(v => !v); }
      if (e.key === "1") setPage("solar");
      if (e.key === "2") setPage("dashboard");
      if (e.key === "3") setPage("terminal");
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showSearch, selectedTask, selectedAgent]);

  // Export snapshot
  const exportSnapshot = useCallback(() => {
    const blob = new Blob([JSON.stringify(store, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `mos-v2-snapshot-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`;
    a.click();
  }, [store]);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: "var(--bg-space)" }}>
      <TopBar
        grus={store.grus} selectedGruId={store.selectedGruId} selectedPort={store.selectedPort}
        connected={store.connected} agentCount={store.agents.length} taskCount={store.tasks.length}
        onSearch={() => setShowSearch(true)} onExport={exportSnapshot}
      />

      <main className="flex-1 overflow-hidden relative">
        {/* Gru/Project selection flow */}
        {!currentGru && <GruPicker grus={store.grus} />}
        {currentGru && !currentProject && store.selectedPort == null && <ProjectPicker gru={currentGru} />}
        {currentGru && !currentProject && store.selectedPort != null && (
          <div className="page-container flex items-center justify-center">
            <div className="surface-card p-8 max-w-md">
              <div className="empty-state">
                <p className="font-semibold" style={{ color: "var(--text)" }}>Project unavailable</p>
                <p style={{ color: "var(--muted)" }}>project_{store.selectedPort} is closed or no longer registered.</p>
                <button onClick={() => selectProject(null)} className="mt-3 text-xs px-4 py-2 rounded-full" style={{ background: "var(--surface)", border: "1px solid var(--line)", color: "var(--muted)" }}>
                  ← Back to projects
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Page content with crossfade transition */}
        {currentProject && (
          <div className="absolute inset-0">
            <div style={{ display: page === "solar" ? "contents" : "none" }}>
              <SolarSystemPage onSelectAgent={setSelectedAgent} />
            </div>
            <div style={{ display: page === "dashboard" ? "contents" : "none" }}>
              <DashboardPage onSelectAgent={setSelectedAgent} onSelectTask={setSelectedTask} />
            </div>
            <div style={{ display: page === "terminal" ? "contents" : "none" }}>
              <TerminalPage />
            </div>
          </div>
        )}
      </main>

      {currentProject && <BottomDock page={page} onNavigate={setPage} />}

      {/* Overlays */}
      <SlideOutPanel open={!!selectedAgent} onClose={() => setSelectedAgent(null)} accentColor={selectedAgent ? getRoleIdentity(selectedAgent).color : undefined}>
        {/* Role detail content */}
      </SlideOutPanel>
      <TaskDetailModal open={!!selectedTask} taskId={selectedTask} tasks={store.tasks} agents={store.agents} onClose={() => setSelectedTask(null)} onSelectAgent={setSelectedAgent} />
      {showSearch && <GlobalSearch tasks={store.tasks} agents={store.agents} logs={store.logs} onSelectAgent={id => { setSelectedAgent(id); setShowSearch(false); }} onSelectTask={id => { setSelectedTask(id); setShowSearch(false); }} onClose={() => setShowSearch(false)} />}
      <ToastContainer />
    </div>
  );
}
```

- [ ] **Step 2: Update main.tsx**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
```

- [ ] **Step 3: Commit**

```bash
git add minions-viz-v2/src/web/App.tsx minions-viz-v2/src/web/main.tsx
git commit -m "feat(viz-v2): assemble app with routing, keyboard shortcuts, overlays"
```

---

### Task 12: Build Verification

- [ ] **Step 1: Full build**

```bash
cd minions-viz-v2 && npm install && npx vite build
```

Expected: build succeeds, 0 TypeScript errors.

- [ ] **Step 2: Check bundle size**

```bash
cd minions-viz-v2 && du -sh dist/
```

Flag if > 5MB (xterm.js + xyflow are heavy; consider lazy loading if needed).

- [ ] **Step 3: Start dev server and verify**

User should run manually:
```bash
cd minions-viz-v2 && npm run dev
```

Verify in browser:
1. GruPicker renders on dark background
2. If a Gru is live, project picker shows projects
3. Solar system page renders with canvas + star node
4. Dashboard page shows metric cards
5. Terminal page shows role sidebar
6. Bottom dock navigation works
7. Keyboard shortcuts (1/2/3, Cmd+K, Escape) work

- [ ] **Step 4: Final commit**

```bash
git add minions-viz-v2/
git commit -m "feat(viz-v2): complete MinionsVIZ V2 initial build"
```
