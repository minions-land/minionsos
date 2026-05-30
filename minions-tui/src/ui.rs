//! All rendering. Immediate-mode: rebuild the frame each tick.

use crate::app::{App, Focus, Mode};
use crate::vt;
use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::Frame;

const GOLD: Color = Color::Rgb(255, 199, 26);
const LIVE: Color = Color::Rgb(80, 200, 120);
const DEAD: Color = Color::Rgb(120, 120, 120);
const WARN: Color = Color::Rgb(220, 160, 60);
const TEXT: Color = Color::Rgb(242, 237, 220);
const SELBG: Color = Color::Rgb(40, 38, 28);

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(4), Constraint::Length(1)])
        .split(area);

    draw_header(f, app, chunks[0]);
    draw_body(f, app, chunks[1]);
    draw_footer(f, app, chunks[2]);

    match &app.mode {
        Mode::Help => draw_help(f, area),
        Mode::Confirm(label) => draw_confirm(f, area, label),
        Mode::Steer => draw_steer(f, area, app),
        Mode::Haiku { input, reply, busy, since, .. } => {
            let elapsed = since.elapsed().as_secs();
            draw_haiku(f, area, input, reply, *busy, app.spinner(), elapsed);
        }
        Mode::Toast(msg) => draw_toast(f, area, msg),
        Mode::Settings { high, medium, window, sel, dirty, loaded } => {
            draw_settings(f, area, *high, *medium, *window, *sel, *dirty, *loaded);
        }
        Mode::Normal => {}
    }
}

fn draw_header(f: &mut Frame, app: &App, area: Rect) {
    // Breadcrumb reflects the strict hierarchy: Gru ▸ Project ▸ Role.
    // Gru is the top-level frame and is NEVER a row inside the project list.
    let mut crumbs: Vec<Span> = vec![
        Span::styled(" gru:", Style::default().fg(Color::Black).bg(GOLD)),
        Span::styled(
            format!("{} ", app.ctx.label),
            Style::default().fg(Color::Black).bg(GOLD).add_modifier(Modifier::BOLD),
        ),
    ];
    let sep = Span::styled(" ▸ ", Style::default().fg(Color::Black).bg(GOLD));
    if app.gru_mode {
        crumbs.push(sep);
        crumbs.push(Span::styled(
            "Gru cockpit ",
            Style::default().fg(Color::Black).bg(GOLD).add_modifier(Modifier::BOLD),
        ));
    } else {
        match app.focus {
        Focus::GruPicker => {
            crumbs.push(Span::styled(" select install ", Style::default().fg(Color::Black).bg(GOLD)));
        }
        Focus::Projects => {
            let n = app.snapshot.projects.len();
            crumbs.push(sep);
            crumbs.push(Span::styled(
                format!("projects ({n}) ",),
                Style::default().fg(Color::Black).bg(GOLD),
            ));
        }
        Focus::Roles | Focus::Cockpit => {
            if let Some(p) = app.current_project() {
                crumbs.push(sep.clone());
                crumbs.push(Span::styled(
                    format!("{} ", p.name),
                    Style::default().fg(Color::Black).bg(GOLD).add_modifier(Modifier::BOLD),
                ));
            }
            if app.focus == Focus::Cockpit {
                if let Some(r) = app.current_role() {
                    crumbs.push(sep);
                    crumbs.push(Span::styled(
                        format!("{} ", r.name),
                        Style::default().fg(Color::Black).bg(GOLD).add_modifier(Modifier::BOLD),
                    ));
                }
            }
        }
        }
    }
    // Right-aligned activity tag: a spinner whenever any background job
    // (haiku / steer / gru-send) is in flight, so the operator always knows
    // the system is doing something rather than wedged.
    let activity: String = if app.is_busy() {
        format!(" {} working ", app.spinner())
    } else {
        String::new()
    };
    let used: usize = crumbs.iter().map(|s| s.content.chars().count()).sum();
    let tag_w = activity.chars().count();
    let total = area.width as usize;
    if used + tag_w < total {
        crumbs.push(Span::styled(
            " ".repeat(total - used - tag_w),
            Style::default().bg(GOLD),
        ));
    }
    if !activity.is_empty() {
        crumbs.push(Span::styled(
            activity,
            Style::default()
                .fg(Color::Black)
                .bg(GOLD)
                .add_modifier(Modifier::BOLD),
        ));
    }
    f.render_widget(Paragraph::new(Line::from(crumbs)), area);
}

fn draw_footer(f: &mut Frame, app: &App, area: Rect) {
    let hint = match app.focus {
        Focus::GruPicker => "↑↓ pick · Enter open · g Gru cockpit · q quit · ? help",
        Focus::Projects => "↑↓ select · →/Enter roles · g Gru cockpit · ? help · q quit",
        Focus::Roles => "↑↓ select · →/Enter open session · ← back · g Gru · ? help",
        Focus::Cockpit => "i steer · l live/logs/health · a attach · d drive · h ask · ← back",
    };
    let err = app.last_error.as_deref().unwrap_or("");
    let line = if err.is_empty() {
        Line::from(Span::styled(format!(" {hint} "), Style::default().fg(DEAD)))
    } else {
        Line::from(Span::styled(format!(" ⚠ {err} "), Style::default().fg(WARN)))
    };
    f.render_widget(Paragraph::new(line), area);
}

fn draw_body(f: &mut Frame, app: &App, area: Rect) {
    // Full-width drill-down — one view per level, the terminal is king.
    // No permanent multi-column split.
    match app.focus {
        Focus::GruPicker => draw_gru_picker(f, app, area),
        Focus::Projects => draw_projects(f, app, area),
        Focus::Roles => draw_roles(f, app, area),
        Focus::Cockpit => draw_cockpit(f, app, area),
    }
}

fn block(title: &str, focused: bool) -> Block<'static> {
    let style = if focused {
        Style::default().fg(GOLD).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(DEAD)
    };
    Block::default()
        .borders(Borders::ALL)
        .border_style(style)
        .title(format!(" {title} "))
}

fn draw_gru_picker(f: &mut Frame, app: &App, area: Rect) {
    let items: Vec<ListItem> = app
        .grus
        .iter()
        .map(|g| {
            ListItem::new(Line::from(vec![
                Span::styled(format!("{:<10}", g.label), Style::default().fg(GOLD)),
                Span::raw(g.root_path.display().to_string()),
            ]))
        })
        .collect();
    let mut st = ListState::default();
    st.select(Some(app.gru_sel));
    let list = List::new(items)
        .block(block("Select Gru install", true))
        .highlight_style(Style::default().bg(GOLD).fg(Color::Black));
    f.render_stateful_widget(list, area, &mut st);
}

fn draw_projects(f: &mut Frame, app: &App, area: Rect) {
    if app.snapshot.projects.is_empty() {
        let msg = Paragraph::new(
            "\n  No projects yet.\n\n  Press g to open the Gru cockpit and create one.",
        )
        .style(Style::default().fg(DEAD));
        f.render_widget(msg, area);
        return;
    }
    let sel = app.project_sel;
    let items: Vec<ListItem> = app
        .snapshot
        .projects
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let marker = if i == sel {
                Span::styled("▸ ", Style::default().fg(GOLD).add_modifier(Modifier::BOLD))
            } else {
                Span::raw("  ")
            };
            let dot = match p.status.as_str() {
                "active" => Span::styled("● ", Style::default().fg(LIVE)),
                "dormant" => Span::styled("◐ ", Style::default().fg(WARN)),
                _ => Span::styled("○ ", Style::default().fg(DEAD)),
            };
            let live = p.roles.iter().filter(|r| r.alive).count();
            let name_style = if i == sel {
                Style::default().fg(TEXT).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(TEXT)
            };
            let phase = p.phase.as_deref().filter(|s| !s.is_empty());
            let mut spans = vec![
                marker,
                dot,
                Span::styled(format!("{:<6}", p.port), Style::default().fg(GOLD)),
                Span::styled(format!("{:<28}", truncate(&p.name, 27)), name_style),
                Span::styled(
                    format!("{live}/{} roles", p.roles.len()),
                    Style::default().fg(if live > 0 { LIVE } else { DEAD }),
                ),
            ];
            if let Some(ph) = phase {
                spans.push(Span::styled(format!("  ▪ {ph}"), Style::default().fg(DEAD)));
            }
            ListItem::new(Line::from(spans))
        })
        .collect();
    let mut st = ListState::default();
    st.select(Some(sel));
    let list = List::new(items)
        .highlight_style(Style::default().bg(SELBG))
        .highlight_spacing(ratatui::widgets::HighlightSpacing::Always);
    f.render_stateful_widget(list, pad(area), &mut st);
}

fn draw_roles(f: &mut Frame, app: &App, area: Rect) {
    let Some(project) = app.current_project() else {
        f.render_widget(Paragraph::new("  (no project selected)").style(Style::default().fg(DEAD)), area);
        return;
    };
    if project.roles.is_empty() {
        f.render_widget(
            Paragraph::new("\n  No roles in this project yet.").style(Style::default().fg(DEAD)),
            area,
        );
        return;
    }
    let sel = app.role_sel;
    let items: Vec<ListItem> = project
        .roles
        .iter()
        .enumerate()
        .map(|(i, r)| {
            let marker = if i == sel {
                Span::styled("▸ ", Style::default().fg(GOLD).add_modifier(Modifier::BOLD))
            } else {
                Span::raw("  ")
            };
            let dot = if r.alive {
                Span::styled("● ", Style::default().fg(LIVE))
            } else {
                Span::styled("○ ", Style::default().fg(DEAD))
            };
            let name_style = if i == sel {
                Style::default().fg(GOLD).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(TEXT)
            };
            let task = r.current_task.as_deref().unwrap_or("");
            let mut spans = vec![
                marker,
                dot,
                Span::styled(format!("{:<12}", r.name), name_style),
            ];
            if r.blocked_reason.is_some() {
                spans.push(Span::styled("⚠ blocked ", Style::default().fg(WARN)));
            }
            if !task.is_empty() {
                spans.push(Span::styled(
                    truncate(task, area.width.saturating_sub(20) as usize),
                    Style::default().fg(Color::Rgb(180, 175, 150)),
                ));
            } else if r.alive {
                spans.push(Span::styled("idle", Style::default().fg(DEAD)));
            }
            ListItem::new(Line::from(spans))
        })
        .collect();
    let mut st = ListState::default();
    st.select(Some(sel));
    let list = List::new(items)
        .highlight_style(Style::default().bg(SELBG))
        .highlight_spacing(ratatui::widgets::HighlightSpacing::Always);
    f.render_stateful_widget(list, pad(area), &mut st);
}

/// Inset a rect by one column on each side so list rows have breathing room.
fn pad(area: Rect) -> Rect {
    Rect {
        x: area.x + 1,
        y: area.y,
        width: area.width.saturating_sub(2),
        height: area.height,
    }
}

fn draw_cockpit(f: &mut Frame, app: &App, area: Rect) {
    let view = app.cockpit_view;
    let (alive, sess, task) = if app.gru_mode {
        (app.gru_alive(), "Gru · mos-gru".to_string(), None)
    } else {
        match app.current_role() {
            Some(r) => (r.alive, r.session_name.clone(), r.current_task.clone()),
            None => (false, String::new(), None),
        }
    };

    // Status strip (1 row) + optional goal bar (1 row) + terminal surface.
    let has_goal = task.as_deref().map(|t| !t.is_empty()).unwrap_or(false);
    let constraints = if has_goal {
        vec![Constraint::Length(1), Constraint::Length(1), Constraint::Min(1)]
    } else {
        vec![Constraint::Length(1), Constraint::Min(1)]
    };
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints(constraints)
        .split(area);

    // Status strip: liveness pulse, session name, view, freshness.
    // The pulse dot animates while captures are arriving (proves the live feed
    // is flowing, not frozen); it dims if the feed stalls.
    let cap_age = app.last_capture_at.elapsed();
    let feed_fresh = alive && cap_age.as_millis() < 1500;
    let dot = if !alive {
        Span::styled("○ dead ", Style::default().fg(DEAD))
    } else if feed_fresh {
        // Animate the live glyph so the operator can see the feed pulsing.
        let glyph = if app.spin % 2 == 0 { "●" } else { "◉" };
        Span::styled(
            format!("{glyph} live "),
            Style::default().fg(LIVE).add_modifier(Modifier::BOLD),
        )
    } else {
        Span::styled("◌ live ", Style::default().fg(WARN))
    };
    let mut status_spans = vec![
        dot,
        Span::styled(format!("{sess}  "), Style::default().fg(TEXT)),
        Span::styled(
            format!("[{}]", view.label()),
            Style::default().fg(GOLD).add_modifier(Modifier::BOLD),
        ),
        Span::styled("  ·  l cycles view", Style::default().fg(DEAD)),
    ];
    // For non-Live views, show how stale the underlying data is.
    if !matches!(view, crate::app::CockpitView::Live) {
        status_spans.push(Span::styled(
            format!("  ·  refreshed {}", ago(app.last_snapshot_at.elapsed())),
            Style::default().fg(DEAD),
        ));
    }
    let status = Line::from(status_spans);
    f.render_widget(Paragraph::new(status), rows[0]);

    let surface = if has_goal {
        // Goal bar (MinionsCode "target" prompt bar).
        let goal = Line::from(vec![
            Span::styled("◎ ", Style::default().fg(GOLD)),
            Span::styled(
                truncate(task.as_deref().unwrap_or(""), area.width.saturating_sub(3) as usize),
                Style::default().fg(Color::Rgb(220, 210, 180)),
            ),
        ]);
        f.render_widget(Paragraph::new(goal), rows[1]);
        rows[2]
    } else {
        rows[1]
    };

    match view {
        crate::app::CockpitView::Live => {
            if !alive {
                let msg = Paragraph::new(
                    "No live session.\n\n  l → logs / health    d → drive (takeover)    ← back",
                )
                .style(Style::default().fg(DEAD))
                .wrap(Wrap { trim: true });
                f.render_widget(msg, surface);
                return;
            }
            // Render the captured *visible screen* full-width on a dark surface.
            // We do NOT force-wrap: each captured line maps to one row, so the
            // real terminal layout is preserved (no scrollback mangling).
            let raw = app.cockpit_lines.join("\n");
            let lines = vt::ansi_to_lines(&raw, surface.height, surface.width);
            f.render_widget(
                Paragraph::new(lines).style(Style::default().bg(Color::Rgb(12, 12, 14))),
                surface,
            );
        }
        crate::app::CockpitView::Logs => {
            let (port, role) = match (app.current_project(), app.current_role()) {
                (Some(p), Some(r)) => (p.port, r.name.clone()),
                _ => return,
            };
            let text = crate::logs::tail_role_log(&app.ctx, port, &role, 16 * 1024);
            let body = if text.is_empty() {
                "(no log file yet)".to_string()
            } else {
                tail_lines(&text, surface.height as usize)
            };
            f.render_widget(
                Paragraph::new(body)
                    .wrap(Wrap { trim: false })
                    .style(Style::default().bg(Color::Rgb(12, 12, 14)).fg(TEXT)),
                surface,
            );
        }
        crate::app::CockpitView::Health => {
            let port = match app.current_project() {
                Some(p) => p.port,
                None => return,
            };
            let events = crate::logs::recent_health(&app.ctx, port, surface.height as usize);
            let lines: Vec<Line> = if events.is_empty() {
                vec![Line::from(Span::styled("(no health events)", Style::default().fg(DEAD)))]
            } else {
                events
                    .iter()
                    .map(|e| {
                        let sev = match e.severity.as_str() {
                            "error" | "critical" => Style::default().fg(Color::Rgb(220, 80, 80)),
                            "warning" => Style::default().fg(WARN),
                            _ => Style::default().fg(DEAD),
                        };
                        Line::from(vec![
                            Span::styled(format!("{:<5} ", e.severity), sev),
                            Span::styled(format!("{} ", e.kind), Style::default().fg(GOLD)),
                            Span::raw(truncate(&e.message, surface.width.saturating_sub(14) as usize)),
                        ])
                    })
                    .collect()
            };
            f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), surface);
        }
    }
}

/// Keep only the last `n` lines of a blob (for log tailing in a fixed pane).
fn tail_lines(s: &str, n: usize) -> String {
    let lines: Vec<&str> = s.lines().collect();
    let start = lines.len().saturating_sub(n);
    lines[start..].join("\n")
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let t: String = s.chars().take(max.saturating_sub(1)).collect();
        format!("{t}…")
    }
}

/// Compact "Ns ago" / "Nm ago" for a freshness indicator.
fn ago(d: std::time::Duration) -> String {
    let secs = d.as_secs();
    if secs < 1 {
        "just now".to_string()
    } else if secs < 60 {
        format!("{secs}s ago")
    } else {
        format!("{}m ago", secs / 60)
    }
}

fn centered(area: Rect, pct_x: u16, pct_y: u16) -> Rect {
    let v = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - pct_y) / 2),
            Constraint::Percentage(pct_y),
            Constraint::Percentage((100 - pct_y) / 2),
        ])
        .split(area);
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - pct_x) / 2),
            Constraint::Percentage(pct_x),
            Constraint::Percentage((100 - pct_x) / 2),
        ])
        .split(v[1])[1]
}

fn draw_help(f: &mut Frame, area: Rect) {
    let r = centered(area, 60, 70);
    f.render_widget(Clear, r);
    let text = vec![
        Line::from(Span::styled("MinionsOS TUI — keys", Style::default().fg(GOLD).add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from("  ↑/↓ or j/k   move selection"),
        Line::from("  →/Enter      descend (project→roles→cockpit)"),
        Line::from("  ←/Esc        back up a level"),
        Line::from("  i            steer: type text, Enter sends into the role pane"),
        Line::from("  a            attach (read-mostly, Ctrl-b d to detach)"),
        Line::from("  d            drive (TAKEOVER — kills autonomy, confirm first)"),
        Line::from("  h            ask haiku (transient, read-only chat box)"),
        Line::from("  l            cockpit view: cycle live / logs / health"),
        Line::from("  g            open the Gru cockpit (starts mos-gru if needed)"),
        Line::from("  S            settings: context-pressure / compaction thresholds"),
        Line::from("  r            force refresh"),
        Line::from("  ?            toggle this help"),
        Line::from("  q            quit"),
        Line::from(""),
        Line::from(Span::styled("  Steering & attach reuse `mos role kick/attach/drive`.", Style::default().fg(DEAD))),
    ];
    let p = Paragraph::new(text).block(block("Help", true)).wrap(Wrap { trim: false });
    f.render_widget(p, r);
}

#[allow(clippy::too_many_arguments)]
fn draw_settings(
    f: &mut Frame,
    area: Rect,
    high: u64,
    medium: u64,
    window: u64,
    sel: u8,
    dirty: bool,
    loaded: bool,
) {
    let r = centered(area, 64, 50);
    f.render_widget(Clear, r);

    let row = |label: &str, val: u64, active: bool| -> Line {
        let marker = if active { "▸ " } else { "  " };
        let style = if active {
            Style::default().fg(GOLD).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(Color::White)
        };
        Line::from(vec![
            Span::styled(format!("  {marker}{label:<26}"), style),
            Span::styled(format!("{:>9}", fmt_k(val)), style),
        ])
    };

    let status = if !loaded {
        Line::from(Span::styled("  loading current values…", Style::default().fg(DEAD)))
    } else if dirty {
        Line::from(Span::styled("  ● unsaved — Enter to save", Style::default().fg(WARN)))
    } else {
        Line::from(Span::styled("  saved values (live)", Style::default().fg(DEAD)))
    };

    let mut text = vec![
        Line::from(Span::styled(
            "Context-pressure thresholds",
            Style::default().fg(GOLD).add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(
            "  when to ADVISE compaction (cache_read tokens/turn)",
            Style::default().fg(DEAD),
        )),
        Line::from(""),
        row("compact-now (high)", high, sel == 0),
        row("soft hint (medium)", medium, sel == 1),
        Line::from(""),
        Line::from(vec![
            Span::styled("  context window: ", Style::default().fg(DEAD)),
            Span::styled(fmt_k(window), Style::default().fg(Color::White)),
            Span::styled("  (full 1M preserved)", Style::default().fg(DEAD)),
        ]),
        Line::from(""),
        status,
    ];
    if medium >= high {
        text.push(Line::from(Span::styled(
            "  ! medium must be < high",
            Style::default().fg(Color::Rgb(220, 80, 80)),
        )));
    }
    text.push(Line::from(""));
    text.push(Line::from(Span::styled(
        "  ↑/↓ pick   ←/→ or -/+ adjust 25K   Enter save   Esc cancel",
        Style::default().fg(DEAD),
    )));

    let p = Paragraph::new(text)
        .block(block("Settings", true))
        .wrap(Wrap { trim: false });
    f.render_widget(p, r);
}

/// Format a token count compactly, e.g. 200000 -> "200K", 1000000 -> "1.0M".
fn fmt_k(n: u64) -> String {
    if n >= 1_000_000 {
        format!("{:.1}M", n as f64 / 1_000_000.0)
    } else if n >= 1_000 {
        format!("{}K", n / 1_000)
    } else {
        n.to_string()
    }
}

fn draw_confirm(f: &mut Frame, area: Rect, label: &str) {
    let r = centered(area, 50, 22);
    f.render_widget(Clear, r);
    let text = vec![
        Line::from(Span::styled(label.to_string(), Style::default().fg(WARN).add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from("  y = confirm    n/Esc = cancel"),
    ];
    let p = Paragraph::new(text)
        .block(block("Confirm", true).border_style(Style::default().fg(WARN)))
        .wrap(Wrap { trim: true });
    f.render_widget(p, r);
}

fn draw_steer(f: &mut Frame, area: Rect, app: &App) {
    let r = centered(area, 70, 20);
    f.render_widget(Clear, r);
    let sess = app.current_session().unwrap_or_default();
    let text = vec![
        Line::from(Span::styled(format!("Steer → {sess}"), Style::default().fg(GOLD))),
        Line::from(""),
        Line::from(Span::styled(format!("> {}", app.steer_buf), Style::default().fg(Color::White))),
        Line::from(""),
        Line::from(Span::styled("  Enter sends (send-keys -l) · Esc cancels", Style::default().fg(DEAD))),
    ];
    let p = Paragraph::new(text).block(block("Steer", true)).wrap(Wrap { trim: false });
    f.render_widget(p, r);
}

fn draw_toast(f: &mut Frame, area: Rect, msg: &str) {
    let r = centered(area, 60, 30);
    f.render_widget(Clear, r);
    let p = Paragraph::new(msg.to_string())
        .block(block("Result", true))
        .wrap(Wrap { trim: false });
    f.render_widget(p, r);
}

/// Transient, project-free haiku chat box. Type a question, Enter asks
/// (off-thread — the box stays responsive), the reply renders below. While the
/// request is in flight an animated spinner + elapsed seconds make it obvious
/// the system is working, not stuck. Esc closes. Read-only — writes nothing.
fn draw_haiku(
    f: &mut Frame,
    area: Rect,
    input: &str,
    reply: &str,
    busy: bool,
    spin: &str,
    elapsed: u64,
) {
    let r = centered(area, 78, 72);
    f.render_widget(Clear, r);
    let title = if busy { "haiku · asking" } else { "haiku" };
    let mut lines = vec![
        Line::from(Span::styled(
            "✦ Ask haiku  (read-only · whole-Gru context)",
            Style::default().fg(GOLD).add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(
            "sees every project, role & memory · Enter asks · Esc closes",
            Style::default().fg(DEAD),
        )),
        Line::from(""),
        Line::from(vec![
            Span::styled("> ", Style::default().fg(GOLD)),
            Span::styled(input.to_string(), Style::default().fg(TEXT)),
            // Hide the input caret while busy (input is locked until the reply).
            Span::styled(if busy { "" } else { "▏" }, Style::default().fg(GOLD)),
        ]),
        Line::from(""),
    ];
    if busy {
        // Animated, with a live elapsed counter so a slow call never looks hung.
        lines.push(Line::from(vec![
            Span::styled(format!("  {spin} "), Style::default().fg(GOLD).add_modifier(Modifier::BOLD)),
            Span::styled(
                format!("thinking… {elapsed}s"),
                Style::default().fg(WARN).add_modifier(Modifier::BOLD),
            ),
            Span::styled("   (Esc cancels)", Style::default().fg(DEAD)),
        ]));
    } else if !reply.is_empty() {
        lines.push(Line::from(Span::styled(
            "────────────────────────",
            Style::default().fg(DEAD),
        )));
        for l in reply.lines() {
            lines.push(Line::from(Span::styled(
                l.to_string(),
                Style::default().fg(Color::Rgb(210, 205, 180)),
            )));
        }
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            "  ask again, or Esc to close",
            Style::default().fg(DEAD),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            "  e.g. “who's doing what right now?” · “any role blocked?”",
            Style::default().fg(DEAD),
        )));
        lines.push(Line::from(Span::styled(
            "       “summarize project 41001's progress” · “draft an issue about X”",
            Style::default().fg(DEAD),
        )));
    }
    let style = if busy {
        Style::default().fg(WARN).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(GOLD).add_modifier(Modifier::BOLD)
    };
    let p = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(style)
                .title(format!(" {title} ")),
        )
        .wrap(Wrap { trim: false });
    f.render_widget(p, r);
}


