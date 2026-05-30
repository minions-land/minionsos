//! MinionsOS TUI — `mtui` entry point.
//!
//! A keyboard-driven control plane for MinionsOS. Reads state files + tmux
//! capture-pane for display; every mutation shells out to `mos`.

// The crate is built in phases: Phase 1 ships the session cockpit, and several
// data-layer / action helpers (e.g. `mos status --json` ingest, `send_key`,
// `attach_argv`, role-state rendering fields) are wired by the later panels.
// Allow dead_code crate-wide so the phased surface doesn't spam warnings;
// remove once the panels land.
#![allow(dead_code)]

mod actions;
mod app;
mod config;
mod digest;
mod gru;
mod haiku;
mod logs;
mod model;
mod scanner;
mod tmux;
mod ui;
mod vt;

use anyhow::Result;
use app::{App, CaptureMsg, ExitRequest, Focus, JobMsg, Mode};
use crossterm::event::{self, Event, KeyCode, KeyEventKind, KeyModifiers};
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::execute;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use std::io::{stdout, Stdout};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

type Term = Terminal<CrosstermBackend<Stdout>>;

/// Non-interactive read-path validation. Proves the data layer works against
/// the live state files without needing a TTY. Also a scriptable health check.
fn probe(ctx: &config::GruContext, grus: &[config::GruEntry]) -> Result<()> {
    println!("gru: {} ({})", ctx.label, ctx.id);
    println!("root: {}", ctx.root.display());
    println!("projects.json: {}", ctx.projects_json().display());
    println!("registered grus: {}", grus.len());
    let snap = scanner::scan(ctx);
    if let Some(e) = &snap.error {
        println!("scan error: {e}");
        std::process::exit(1);
    }
    let total = snap.projects.len();
    let active = snap.projects.iter().filter(|p| p.status == "active").count();
    let live_roles: usize = snap
        .projects
        .iter()
        .flat_map(|p| p.roles.iter())
        .filter(|r| r.alive)
        .count();
    println!("projects: {total} ({active} active)  live role sessions: {live_roles}");
    for p in snap.projects.iter().filter(|p| p.status == "active").take(8) {
        let live = p.roles.iter().filter(|r| r.alive).count();
        println!(
            "  {} {} [{}/{} live] phase={}",
            p.port,
            p.name,
            live,
            p.roles.len(),
            p.phase.as_deref().unwrap_or("-")
        );
    }
    Ok(())
}


fn enter_tui() -> Result<Term> {
    enable_raw_mode()?;
    let mut out = stdout();
    execute!(out, EnterAlternateScreen)?;
    let term = Terminal::new(CrosstermBackend::new(out))?;
    Ok(term)
}

fn leave_tui(term: &mut Term) -> Result<()> {
    disable_raw_mode()?;
    execute!(term.backend_mut(), LeaveAlternateScreen)?;
    term.show_cursor()?;
    Ok(())
}

fn main() -> Result<()> {
    let grus = config::read_registry().unwrap_or_default();
    let ctx = config::resolve_context(&grus)?;

    // `--probe`: non-interactive read-path validation / scriptable health check.
    if std::env::args().any(|a| a == "--probe") {
        return probe(&ctx, &grus);
    }

    // Shared "which session is the cockpit watching" cell, read by the capture
    // poller thread so it only captures the focused role (cheap, no fan-out).
    let watch: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));

    // Shared current-Gru context, so a picker switch re-targets the scanner
    // without respawning it.
    let scan_ctx: Arc<Mutex<config::GruContext>> = Arc::new(Mutex::new(ctx.clone()));

    let (scan_tx, scan_rx) = mpsc::channel();
    let (cap_tx, cap_rx) = mpsc::channel();

    spawn_scanner(scan_ctx.clone(), scan_tx);
    spawn_capture_poller(watch.clone(), cap_tx);

    let mut app = App::new(ctx, scan_ctx, grus, scan_rx, cap_rx);

    // `--gru`: open straight into the Gru cockpit (the blueprint default — the
    // whole MinionsOS surface behind one keyboard cockpit, Gru front and center).
    if std::env::args().any(|a| a == "--gru") {
        let _ = open_gru(&mut app);
    }

    let mut term = enter_tui()?;
    let res = run(&mut term, &mut app, &watch);
    leave_tui(&mut term)?;
    res
}

/// Scanner thread: re-reads projects.json + tmux liveness on a cadence and
/// pushes a fresh Snapshot. Cheap full-scan every ~2s (state file is small;
/// liveness is one `tmux ls`).
fn spawn_scanner(scan_ctx: Arc<Mutex<config::GruContext>>, tx: Sender<scanner::Snapshot>) {
    std::thread::spawn(move || loop {
        let ctx = match scan_ctx.lock() {
            Ok(g) => g.clone(),
            Err(_) => return,
        };
        let snap = scanner::scan(&ctx);
        if tx.send(snap).is_err() {
            return; // UI gone
        }
        std::thread::sleep(Duration::from_millis(2000));
    });
}

/// Capture poller thread: ~200ms, captures only the session the cockpit is
/// watching (from the shared `watch` cell). Zero attach -> no resize reflow.
fn spawn_capture_poller(watch: Arc<Mutex<Option<String>>>, tx: Sender<CaptureMsg>) {
    std::thread::spawn(move || loop {
        let sess = watch.lock().ok().and_then(|g| g.clone());
        if let Some(session) = sess {
            // Visible screen only (no scrollback) — renders crisp full-width.
            if let Ok(raw) = tmux::capture_screen(&session) {
                if tx.send(CaptureMsg { session, raw }).is_err() {
                    return;
                }
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    });
}

/// The synchronous draw/poll loop.
fn run(term: &mut Term, app: &mut App, watch: &Arc<Mutex<Option<String>>>) -> Result<()> {
    let mut last_resized: Option<(String, u16, u16)> = None;
    // Toast timing is transition-based: whenever the mode *becomes* a Toast
    // (from a keypress OR from a background job landing in tick()), restart the
    // 4s dismissal clock. Tracking the boolean here avoids resetting the clock
    // on every redraw while a toast is still showing.
    let mut toast_since: Option<Instant> = None;
    loop {
        // Keep the capture poller pointed at the focused session only while in
        // the cockpit. When it changes, resize that tmux session to (roughly)
        // the cockpit surface so capture-pane returns full-width, unmangled
        // lines — this is what makes the live view crisp instead of wrapped.
        {
            let want = if app.focus == Focus::Cockpit {
                app.current_session()
            } else {
                None
            };
            if let (Focus::Cockpit, Some(sess)) = (app.focus, want.clone()) {
                let (tw, th) = crossterm::terminal::size().unwrap_or((120, 40));
                // Cockpit surface ≈ full width; height minus header/footer/status/goal.
                let cols = tw.max(20);
                let rows = th.saturating_sub(5).max(6);
                if last_resized.as_ref() != Some(&(sess.clone(), cols, rows)) {
                    tmux::resize_window(&sess, cols, rows);
                    last_resized = Some((sess, cols, rows));
                }
            } else {
                last_resized = None;
            }
            if let Ok(mut g) = watch.lock() {
                *g = want;
            }
        }

        app.tick();

        // Restart the toast clock on the transition INTO a toast (covers both
        // keypress- and job-sourced toasts), then auto-dismiss after 4s.
        match (&app.mode, toast_since) {
            (Mode::Toast(_), None) => toast_since = Some(Instant::now()),
            (Mode::Toast(_), Some(t)) if t.elapsed() > Duration::from_secs(4) => {
                app.mode = Mode::Normal;
                toast_since = None;
            }
            (Mode::Toast(_), Some(_)) => {}
            _ => toast_since = None,
        }

        term.draw(|f| ui::draw(f, app))?;

        // Poll faster while background work is in flight so the spinner stays
        // smooth and a finished job paints promptly; idle is a calm 120ms.
        let poll_ms = if app.is_busy() || matches!(app.mode, Mode::Haiku { busy: true, .. }) {
            80
        } else {
            120
        };
        if !event::poll(Duration::from_millis(poll_ms))? {
            continue;
        }
        let Event::Key(key) = event::read()? else {
            continue;
        };
        if key.kind != KeyEventKind::Press {
            continue;
        }

        // Global: Ctrl-C always quits.
        if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
            return Ok(());
        }

        match handle_key(app, key.code) {
            Some(ExitRequest::Quit) => return Ok(()),
            Some(ExitRequest::Noop) => {}
            Some(ExitRequest::Exec(argv)) => {
                run_foreground(term, app, &argv)?;
            }
            None => {}
        }
        // A keypress that just raised a toast restarts the clock immediately.
        if matches!(app.mode, Mode::Toast(_)) && toast_since.is_none() {
            toast_since = Some(Instant::now());
        }
        if app.should_quit {
            return Ok(());
        }
    }
}

/// Suspend the TUI, run a foreground child (attach/drive) that owns the real
/// terminal, then re-enter and force a rescan. ManageCode's pattern.
fn run_foreground(term: &mut Term, app: &mut App, argv: &[String]) -> Result<()> {
    if argv.is_empty() {
        return Ok(());
    }
    leave_tui(term)?;
    let status = std::process::Command::new(&argv[0]).args(&argv[1..]).status();
    *term = enter_tui()?;
    term.clear()?;
    match status {
        Ok(s) => app.mode = Mode::Toast(format!("session exited ({}). rescanning…", s)),
        Err(e) => app.mode = Mode::Toast(format!("failed to launch: {e}")),
    }
    Ok(())
}

/// Mode-based key dispatch. Returns an ExitRequest when main() must take the
/// terminal (quit / attach / drive) or None to keep looping.
fn handle_key(app: &mut App, code: KeyCode) -> Option<ExitRequest> {
    // Overlay modes intercept first.
    match app.mode.clone() {
        Mode::Help => {
            app.mode = Mode::Normal;
            return None;
        }
        Mode::Toast(_) => {
            app.mode = Mode::Normal;
            return None;
        }
        Mode::Confirm(label) => return handle_confirm(app, code, &label),
        Mode::Steer => return handle_steer(app, code),
        Mode::Haiku { .. } => return handle_haiku(app, code),
        Mode::Settings { .. } => return handle_settings(app, code),
        Mode::Normal => {}
    }

    match code {
        KeyCode::Char('q') => return Some(ExitRequest::Quit),
        KeyCode::Char('?') => app.mode = Mode::Help,
        KeyCode::Char('r') => app.last_error = None, // scanner pushes fresh soon
        KeyCode::Up | KeyCode::Char('k') => move_sel(app, -1),
        KeyCode::Down | KeyCode::Char('j') => move_sel(app, 1),
        KeyCode::Right | KeyCode::Enter => descend(app),
        KeyCode::Left | KeyCode::Esc => ascend(app),
        KeyCode::Char('i') => {
            // Steer works in the cockpit (any live session, incl. Gru) or on a
            // selected live role in the Roles list.
            let live = if app.gru_mode {
                app.gru_alive()
            } else {
                app.current_role().map(|r| r.alive) == Some(true)
            };
            if app.focus == Focus::Cockpit || app.focus == Focus::Roles {
                if live {
                    app.steer_buf.clear();
                    app.mode = Mode::Steer;
                } else {
                    app.mode = Mode::Toast("no live session to steer".into());
                }
            }
        }
        KeyCode::Char('a') => {
            if app.gru_mode {
                return Some(ExitRequest::Exec(gru::attach_argv()));
            }
            if let (Some(p), Some(r)) = (app.current_project(), app.current_role()) {
                return Some(ExitRequest::Exec(actions::attach_argv(&app.ctx, p.port, &r.name)));
            }
        }
        KeyCode::Char('d') => {
            if app.gru_mode {
                // "Driving" Gru is just attaching to its live frame — there is
                // no autonomy to kill (Gru is the operator's own agent).
                return Some(ExitRequest::Exec(gru::attach_argv()));
            }
            if let (Some(p), Some(r)) = (app.current_project(), app.current_role()) {
                app.mode = Mode::Confirm(format!(
                    "DRIVE {} on {} — this KILLS the role's autonomy. Take over?",
                    r.name, p.port
                ));
            }
        }
        KeyCode::Char('g') => return Some(open_gru(app)),
        KeyCode::Char('h') => {
            app.mode = Mode::Haiku {
                input: String::new(),
                reply: String::new(),
                busy: false,
                req: 0,
                since: Instant::now(),
            };
        }
        KeyCode::Char('l') if app.focus == Focus::Cockpit => {
            app.cockpit_view = app.cockpit_view.next();
        }
        KeyCode::Char('S') => open_settings(app),
        _ => {}
    }
    None
}

/// Open the context-pressure settings panel and kick off an off-thread
/// `mos config --json` load so the panel shows live values without blocking
/// the render loop. Defaults are shown until the load lands.
fn open_settings(app: &mut App) {
    app.mode = Mode::Settings {
        high: 200_000,
        medium: 150_000,
        window: 1_000_000,
        sel: 0,
        dirty: false,
        loaded: false,
    };
    let ctx = app.ctx.clone();
    let tx = app.jobs_tx.clone();
    app.inflight += 1;
    std::thread::spawn(move || {
        let msg = match actions::config_json(&ctx) {
            Ok(out) if out.ok => parse_config_json(&out.stdout)
                .map(|(high, medium, window)| JobMsg::Config { high, medium, window })
                .unwrap_or_else(|| JobMsg::Toast("config: could not parse mos output".into())),
            Ok(out) => JobMsg::Toast(format!("config load failed: {}", out.stderr.trim())),
            Err(e) => JobMsg::Toast(format!("config load error: {e}")),
        };
        let _ = tx.send(msg);
    });
}

/// Pull the three context-pressure tunables out of `mos config --json`.
fn parse_config_json(s: &str) -> Option<(u64, u64, u64)> {
    let v: serde_json::Value = serde_json::from_str(s).ok()?;
    let get = |k: &str| v.get(k).and_then(|x| x.as_u64());
    Some((
        get("CONTEXT_PRESSURE_HIGH_TOKENS")?,
        get("CONTEXT_PRESSURE_MEDIUM_TOKENS")?,
        get("MODEL_CONTEXT_WINDOW_TOKENS").unwrap_or(1_000_000),
    ))
}

/// Settings panel: ↑/↓ pick a field, +/-/←/→ adjust by 25K, Enter persists
/// via `mos config set` (off-thread), Esc cancels. The CLI enforces the
/// medium<high invariant + allowlist, so the panel only has to surface the
/// result.
fn handle_settings(app: &mut App, code: KeyCode) -> Option<ExitRequest> {
    const STEP: u64 = 25_000;
    const MIN: u64 = 25_000;
    const MAX: u64 = 2_000_000;
    match code {
        KeyCode::Esc | KeyCode::Char('q') => app.mode = Mode::Normal,
        KeyCode::Up | KeyCode::Char('k') => {
            if let Mode::Settings { sel, .. } = &mut app.mode {
                *sel = 0;
            }
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if let Mode::Settings { sel, .. } = &mut app.mode {
                *sel = 1;
            }
        }
        KeyCode::Right | KeyCode::Char('+') | KeyCode::Char('=') => {
            if let Mode::Settings { high, medium, sel, dirty, .. } = &mut app.mode {
                if *sel == 0 {
                    *high = (*high + STEP).min(MAX);
                } else {
                    *medium = (*medium + STEP).min(MAX);
                }
                *dirty = true;
            }
        }
        KeyCode::Left | KeyCode::Char('-') | KeyCode::Char('_') => {
            if let Mode::Settings { high, medium, sel, dirty, .. } = &mut app.mode {
                if *sel == 0 {
                    *high = high.saturating_sub(STEP).max(MIN);
                } else {
                    *medium = medium.saturating_sub(STEP).max(MIN);
                }
                *dirty = true;
            }
        }
        KeyCode::Enter => {
            let (high, medium) = if let Mode::Settings { high, medium, .. } = &app.mode {
                (*high, *medium)
            } else {
                return None;
            };
            if medium >= high {
                app.mode = Mode::Toast("medium must be < high — adjust before saving".into());
                return None;
            }
            let ctx = app.ctx.clone();
            let tx = app.jobs_tx.clone();
            app.inflight += 1;
            app.mode = Mode::Normal;
            std::thread::spawn(move || {
                // Write high first, then medium. The CLI guards the invariant on
                // each write; ordering high-up-first avoids a transient reject.
                let hi = actions::config_set(&ctx, "context_pressure_high_tokens", &high.to_string());
                let md =
                    actions::config_set(&ctx, "context_pressure_medium_tokens", &medium.to_string());
                let ok = matches!(&hi, Ok(o) if o.ok) && matches!(&md, Ok(o) if o.ok);
                let msg = if ok {
                    format!(
                        "saved: high={} medium={} (restart a role to apply)",
                        high, medium
                    )
                } else {
                    let err = [hi, md]
                        .iter()
                        .filter_map(|r| r.as_ref().ok())
                        .filter(|o| !o.ok)
                        .map(|o| o.stderr.trim().to_string())
                        .collect::<Vec<_>>()
                        .join("; ");
                    format!("save failed: {}", if err.is_empty() { "see logs" } else { &err })
                };
                let _ = tx.send(JobMsg::Toast(msg));
            });
        }
        _ => {}
    }
    None
}

/// Open the Gru cockpit: ensure the `mos-gru` session is up, then show it in
/// the cockpit as the top-level frame (gru_mode). Gru is NEVER a project row.
fn open_gru(app: &mut App) -> ExitRequest {
    match gru::ensure_gru(&app.ctx) {
        Ok(started) => {
            app.gru_mode = true;
            app.focus = Focus::Cockpit;
            app.cockpit_view = crate::app::CockpitView::Live;
            app.cockpit_lines.clear();
            if started {
                app.mode = Mode::Toast("started Gru (mos-gru) — give it a moment to wake".into());
            }
        }
        Err(e) => app.mode = Mode::Toast(format!("could not start Gru: {e}")),
    }
    ExitRequest::Noop
}

/// Build the read-only context fed to the haiku chat box. haiku always sees the
/// WHOLE Gru install (every project + role + task) plus the focused project's
/// persistent memory — so "who's doing what" and "check progress/memory" both
/// work regardless of which pane is on screen. The current focus is passed as
/// emphasis (`scope`) and, in a cockpit, the live screen is attached verbatim.
fn haiku_context(app: &App) -> haiku::AskContext {
    // Which project's memory to fold in: the one the operator is inside.
    let focus_port = if app.gru_mode {
        None
    } else {
        match app.focus {
            Focus::Roles | Focus::Cockpit => app.current_project().map(|p| p.port),
            _ => None,
        }
    };
    let dig = digest::build(&app.ctx, &app.snapshot, focus_port);

    let (scope, session) = if app.gru_mode {
        (
            "the Gru control-plane cockpit (mos-gru)".to_string(),
            Some(crate::gru::GRU_SESSION.to_string()),
        )
    } else {
        match (app.focus, app.current_project(), app.current_role()) {
            (Focus::Cockpit, Some(p), Some(r)) => (
                format!("project {} {}, role {} ({})", p.port, p.name, r.name,
                    if r.alive { "live" } else { "stopped" }),
                Some(r.session_name.clone()),
            ),
            (Focus::Roles, Some(p), _) => {
                (format!("project {} {} — the role list", p.port, p.name), None)
            }
            _ => (
                format!("the projects list ({} projects)", app.snapshot.projects.len()),
                None,
            ),
        }
    };

    haiku::AskContext {
        scope,
        session,
        extra: dig.into_extra(),
    }
}

/// Haiku chat box. Type a question, Enter dispatches the `claude` call on a
/// WORKER THREAD (the render loop keeps animating a spinner — it never freezes)
/// and the answer arrives over the jobs channel, matched by request id. Esc
/// closes. Strictly read-only — never writes to project state.
fn handle_haiku(app: &mut App, code: KeyCode) -> Option<ExitRequest> {
    // While a request is in flight, swallow text edits so the operator can't
    // mutate the question mid-answer; Esc still closes (and abandons the reply).
    let busy_now = matches!(app.mode, Mode::Haiku { busy: true, .. });
    match code {
        KeyCode::Esc => app.mode = Mode::Normal,
        KeyCode::Enter if !busy_now => {
            let question = if let Mode::Haiku { input, .. } = &app.mode {
                input.trim().to_string()
            } else {
                String::new()
            };
            if question.is_empty() {
                return None;
            }
            // Claim a request id, flip the box to busy, and dispatch off-thread.
            let req = app.claim_req();
            let ctx = haiku_context(app);
            let tx = app.jobs_tx.clone();
            app.inflight += 1;
            app.mode = Mode::Haiku {
                input: question.clone(),
                reply: String::new(),
                busy: true,
                req,
                since: Instant::now(),
            };
            std::thread::spawn(move || {
                let text = haiku::ask(&ctx, &question).map_err(|e| e.to_string());
                let _ = tx.send(JobMsg::Haiku { req, text });
            });
        }
        KeyCode::Backspace if !busy_now => {
            if let Mode::Haiku { input, .. } = &mut app.mode {
                input.pop();
            }
        }
        KeyCode::Char(c) if !busy_now => {
            if let Mode::Haiku { input, .. } = &mut app.mode {
                input.push(c);
            }
        }
        _ => {}
    }
    None
}

fn handle_confirm(app: &mut App, code: KeyCode, _label: &str) -> Option<ExitRequest> {
    match code {
        KeyCode::Char('y') => {
            app.mode = Mode::Normal;
            if let (Some(p), Some(r)) = (app.current_project(), app.current_role()) {
                let argv = actions::drive_argv(&app.ctx, p.port, &r.name);
                return Some(ExitRequest::Exec(argv));
            }
        }
        _ => app.mode = Mode::Normal,
    }
    None
}

fn handle_steer(app: &mut App, code: KeyCode) -> Option<ExitRequest> {
    match code {
        KeyCode::Esc => app.mode = Mode::Normal,
        KeyCode::Backspace => {
            app.steer_buf.pop();
        }
        KeyCode::Char(c) => app.steer_buf.push(c),
        KeyCode::Enter => {
            let text = std::mem::take(&mut app.steer_buf);
            if text.trim().is_empty() {
                app.mode = Mode::Normal;
                return None;
            }
            // Dispatch the send off-thread (send-keys + Enter retries sleep
            // ~600ms; we must not block the render loop). Show an immediate
            // "sending…" toast; the worker posts the real result back.
            let tx = app.jobs_tx.clone();
            app.inflight += 1;
            if app.gru_mode {
                app.mode = Mode::Toast(format!("sending to Gru: {}…", short(&text)));
                std::thread::spawn(move || {
                    let msg = match tmux::send_text(gru::GRU_SESSION, &text, 1, 600) {
                        Ok(()) => "sent to Gru".to_string(),
                        Err(e) => format!("steer error: {e}"),
                    };
                    let _ = tx.send(JobMsg::Toast(msg));
                });
            } else if let (Some(p), Some(r)) = (app.current_project(), app.current_role()) {
                let (port, role) = (p.port, r.name.clone());
                let ctx = app.ctx.clone();
                app.mode = Mode::Toast(format!("sending to {role}: {}…", short(&text)));
                std::thread::spawn(move || {
                    let msg = match actions::role_kick(&ctx, port, &role, &text) {
                        Ok(o) if o.ok => format!("sent to {role}"),
                        Ok(o) => format!("kick failed: {}", o.stderr.trim()),
                        Err(e) => format!("kick error: {e}"),
                    };
                    let _ = tx.send(JobMsg::Toast(msg));
                });
            } else {
                app.inflight = app.inflight.saturating_sub(1);
                app.mode = Mode::Normal;
            }
        }
        _ => {}
    }
    None
}

/// Truncate a steer string for the in-flight toast.
fn short(s: &str) -> String {
    let s = s.trim();
    if s.chars().count() <= 32 {
        s.to_string()
    } else {
        let h: String = s.chars().take(31).collect();
        format!("{h}…")
    }
}

fn move_sel(app: &mut App, delta: i32) {
    let len = match app.focus {
        Focus::GruPicker => app.grus.len(),
        Focus::Projects => app.snapshot.projects.len(),
        Focus::Roles | Focus::Cockpit => app.current_project().map(|p| p.roles.len()).unwrap_or(0),
    };
    if len == 0 {
        return;
    }
    let sel = match app.focus {
        Focus::GruPicker => &mut app.gru_sel,
        Focus::Projects => &mut app.project_sel,
        Focus::Roles | Focus::Cockpit => &mut app.role_sel,
    };
    let next = (*sel as i32 + delta).rem_euclid(len as i32) as usize;
    *sel = next;
    if matches!(app.focus, Focus::Projects) {
        app.role_sel = 0;
    }
}

fn descend(app: &mut App) {
    app.focus = match app.focus {
        Focus::GruPicker => {
            // Re-root onto the selected Gru install, then enter its projects.
            app.switch_gru(app.gru_sel);
            Focus::Projects
        }
        Focus::Projects => Focus::Roles,
        Focus::Roles => Focus::Cockpit,
        Focus::Cockpit => Focus::Cockpit,
    };
}

fn ascend(app: &mut App) {
    // Leaving the cockpit while in Gru mode returns to the project list
    // (Gru is the top-level frame, not a project layer).
    if app.focus == Focus::Cockpit && app.gru_mode {
        app.gru_mode = false;
        app.cockpit_lines.clear();
        app.focus = Focus::Projects;
        return;
    }
    app.focus = match app.focus {
        Focus::Cockpit => Focus::Roles,
        Focus::Roles => Focus::Projects,
        // Back out to the Gru picker only for an unpinned, multi-install launch.
        Focus::Projects if app.grus.len() > 1 && !app.pinned => Focus::GruPicker,
        Focus::Projects | Focus::GruPicker => Focus::Projects,
    };
}


