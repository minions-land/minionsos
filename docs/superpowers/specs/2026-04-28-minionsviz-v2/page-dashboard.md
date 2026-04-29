# Page: EACN Dashboard

Comprehensive view of all EACN activity for the selected project. Combines agents, tasks (board + tree), messages, and event log into a single dense but organized page.

## Layout

Full-height scrollable page with stacked panels. Each panel is a frosted glass card (`panel-bg` + backdrop blur).

```
┌─────────────────────────────────────────────────┐
│  Metric Bar (horizontal strip)                  │
├────────────────────────┬────────────────────────┤
│  Agents Panel          │  Tasks Panel           │
│  (card grid)           │  (board or tree toggle)│
├────────────────────────┴────────────────────────┤
│  Messages & Event Log (tabbed)                  │
└─────────────────────────────────────────────────┘
```

On screens < 1024px, panels stack vertically.

## Metric Bar

Horizontal strip of 4-6 compact metric cards at the top:

| Metric | Source |
|--------|--------|
| Agents Online | count of active agents |
| Total Tasks | store.tasks.length |
| Completed Tasks | tasks with status=completed |
| Open Tasks | unclaimed + bidding |
| Messages (24h) | recent message count |
| Backend Status | UP/DOWN indicator with pulse |

Each metric card: role-colored icon left, value large mono font, label small muted text below. Appear with staggered fade-in (50ms delay between each).

## Agents Panel

Grid of agent cards (2-3 columns depending on width).

Each card:
- Role avatar (small, 28px) + role color left border
- Agent ID (mono, truncated)
- State badge (active/sleeping/dismissed) with role-appropriate color
- Buffer count with mini ring indicator (same visual language as solar system)
- Last seen timestamp (relative, e.g. "2m ago")

Cards sorted: active first, then sleeping, then dismissed. Sort transitions are animated (cards slide to new positions over 350ms).

Click card → same slide-out panel as solar system planet click.

## Tasks Panel

Toggle between two views via segmented control at panel top:

### Board View
Kanban columns: Unclaimed → Bidding → In Progress → Completed
- Each column has a count badge
- Task cards show: short ID (mono), status pill, initiator avatar (small), first 80 chars of description, domain tags
- Cards sorted newest-first within each column
- Density control: show 10/20/50 per column (limit-select)
- Drag is NOT supported (read-only dashboard)

### Tree View
Hierarchical task tree using @xyflow/react (retained from current codebase):
- Parent tasks → subtasks as tree nodes
- Node color reflects status
- Click node → task detail modal

Click any task card/node → task detail modal (see Shared Components).

## Messages & Event Log

Tabbed panel with two tabs:

### Messages Tab
Reverse-chronological message list:
- Each row: timestamp (mono), sender avatar (tiny) + name, → receiver avatar + name, message preview (truncated 120 chars)
- Sender/receiver colored by their role color
- New messages animate in from top (slide-down + fade-in)
- Density control: 20/50/100

### Event Log Tab
Raw EACN event stream (same as current EventLog component, restyled):
- Mono font, compact rows
- Color-coded by event type
- Auto-scroll with pause-on-hover
- Density control: 50/100/200

## Data Sources

All data from WebSocket store — no direct EACN3 fetches:
- `store.agents` → Agents panel
- `store.tasks` → Tasks panel
- `store.messages` → Messages tab
- `store.logs` → Event log tab
- `store.connected` → Backend status metric

## Transitions

- Page enter: panels stagger in from bottom (100ms delay between panels)
- Data updates: cards/rows animate to new positions, new items slide in from top
- Tab switch: crossfade 250ms
- View toggle (board↔tree): crossfade 300ms
