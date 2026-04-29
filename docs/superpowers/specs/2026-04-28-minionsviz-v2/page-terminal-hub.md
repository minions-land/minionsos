# Page: Terminal Hub

Read-only integrated terminal view for all agents in the current project. Each agent's log is rendered as a live-tailing terminal.

## Layout

```
┌──────────┬──────────────────────────────────────┐
│ Role     │                                      │
│ Sidebar  │  Terminal Viewport                   │
│          │  (single / split / tabbed)           │
│ ┌──────┐ │                                      │
│ │ Gru  │ │                                      │
│ │ Noter│ │                                      │
│ │ Coder│ │                                      │
│ │ ...  │ │                                      │
│ └──────┘ │                                      │
└──────────┴──────────────────────────────────────┘
```

## Role Sidebar

Narrow left panel (~180px), frosted glass background.

Each role entry:
- Role avatar (24px) with role-color glow ring
- Role name (mono font)
- State indicator dot (active=role color pulse, sleeping=dim, dismissed=grey)
- Buffer count badge (if > 0, uses ring color scale from design system)

Click a role → its terminal appears in the viewport.
Active/selected role has a brighter background highlight + left border in role color.

Roles sorted: active first, sleeping second, dismissed last. Reordering is animated (slide 350ms).

## Terminal Viewport

Uses `xterm.js` to render terminal output.

### Data Source
- Streams `project_{port}/logs/role-{name}.log` via viz server endpoint
- Server endpoint: `GET /api/mos/project/:port/role-log/:role?gru=<id>&tail=500`
- Server uses `fs.watch` + read to stream new lines over WebSocket channel
- Initial load: last 500 lines, then live tail

### View Modes (toggle in viewport toolbar)

| Mode | Description |
|------|-------------|
| Single | One terminal fills the viewport |
| Split | 2 terminals side-by-side (user picks which two) |
| Grid | All active role terminals in a grid (auto-sized) |

Mode toggle: segmented control in viewport toolbar. Transitions between modes use crossfade 300ms.

### Terminal Theming

Each terminal instance:
- Background: `#0A0E1A` (matches page bg)
- Foreground: `#CBD5E1`
- Cursor: role color (blinking disabled since read-only)
- Top border: 2px solid role-color
- Corner badge: role avatar (tiny, 16px) + "READ-ONLY" label in muted text
- Font: JetBrains Mono 12px
- Scrollback: 5000 lines

### Toolbar (per terminal)

Small toolbar above each terminal instance:
- Role name + avatar
- State badge
- "Scroll to bottom" button (appears when user has scrolled up)
- "Clear" button (clears local display only, not the log file)
- Line count indicator

## Empty States

- No roles registered: centered empty state with message "No agents registered on EACN3"
- Backend down: "Backend is down — terminal data unavailable"
- Role has no log yet: "Waiting for first output..."

All empty states use the standard empty-state component with role-appropriate icon.

## Server Extension Required

New endpoint on viz server:

```typescript
// GET /api/mos/project/:port/role-log/:role?gru=<gruId>&tail=<lines>
// Returns last N lines of role log file
// WebSocket channel: subscribe to live tail updates
```

Implementation: read `project_{port}/logs/role-{name}.log` from filesystem. Use `fs.watch` for live updates. Broadcast new lines to subscribed WebSocket clients.

## Transitions

- Page enter: sidebar slides in from left (300ms), viewport fades in (350ms)
- Role switch: terminal crossfade 250ms
- Mode switch (single→split→grid): crossfade 300ms with scale adjustment
- New log lines: appear instantly (terminal scroll behavior, no artificial delay)
