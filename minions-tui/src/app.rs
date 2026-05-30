//! Application state + the keyboard mode machine.
//!
//! The render loop never blocks: background workers (scanner, capture poller)
//! send snapshots over mpsc; `App::tick` drains them with try_recv.

use crate::config::{GruContext, GruEntry};
use crate::scanner::Snapshot;
use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Instant;

/// Braille throbber frames — advanced once per render tick so any in-flight
/// async work (haiku, steer, gru) shows visible motion instead of a frozen UI.
pub const SPIN: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/// A result delivered from a background worker thread back to the render loop.
/// Workers never touch `App` directly; they post one of these over `jobs_tx`,
/// the loop drains them in `tick`. This is what keeps the UI from ever blocking
/// on a slow `claude`/`mos`/`tmux` subprocess.
#[derive(Debug, Clone)]
pub enum JobMsg {
    /// A haiku answer (or error) tagged with the request id that asked for it,
    /// so a reply for a since-closed/superseded box is discarded.
    Haiku { req: u64, text: Result<String, String> },
    /// A generic transient result (steer "sent", errors) -> a Toast.
    Toast(String),
    /// Loaded context-pressure config (high, medium, window tokens) from
    /// `mos config --json`, populating an open Settings panel.
    Config { high: u64, medium: u64, window: u64 },
}

/// Which screen / focus the operator is in.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Focus {
    /// Pick a Gru install (only shown when >1 registered).
    GruPicker,
    /// Project list (left) — the home view.
    Projects,
    /// Role list for the selected project.
    Roles,
    /// Session cockpit: live capture-pane view of the selected role.
    Cockpit,
}

/// Transient input mode layered on top of Focus.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Mode {
    Normal,
    /// Typing text to send into the focused role's pane (STEER).
    Steer,
    /// Confirming a destructive action; holds the pending action label.
    Confirm(String),
    /// Showing the help overlay.
    Help,
    /// Transient haiku chat box (summoned with `h`). The operator types a
    /// question and haiku answers with whole-Gru context — strictly read-only,
    /// no writes. `input` is the editable question, `reply` holds the last
    /// answer. While `busy`, an off-thread `claude` call is running and the box
    /// shows an animated "thinking" state (the render loop never blocks). `req`
    /// is the in-flight request id; a returning answer with a stale id is
    /// dropped. `since` marks when the current ask started (for elapsed time).
    Haiku {
        input: String,
        reply: String,
        busy: bool,
        req: u64,
        since: Instant,
    },
    /// A transient status/result toast.
    Toast(String),
    /// Context-pressure settings panel (summoned with `S`). Lets the operator
    /// view + adjust the compaction-advisory thresholds, then persist them via
    /// `mos config set` (which enforces the allowlist + medium<high invariant).
    /// `high`/`medium` are the live edit values in tokens; `window` is the
    /// (read-only here) 1M context window; `sel` is which field is selected;
    /// `dirty` marks unsaved edits; `loaded` is false until the first
    /// `mos config --json` populates real values.
    Settings {
        high: u64,
        medium: u64,
        window: u64,
        sel: u8,
        dirty: bool,
        loaded: bool,
    },
}

/// What the cockpit pane shows for the selected role.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CockpitView {
    /// Live capture-pane screen (vt100-rendered).
    Live,
    /// Tail of the role's role-{name}.log file.
    Logs,
    /// Recent health events for the project.
    Health,
}

impl CockpitView {
    pub fn next(self) -> Self {
        match self {
            CockpitView::Live => CockpitView::Logs,
            CockpitView::Logs => CockpitView::Health,
            CockpitView::Health => CockpitView::Live,
        }
    }
    pub fn label(self) -> &'static str {
        match self {
            CockpitView::Live => "live",
            CockpitView::Logs => "logs",
            CockpitView::Health => "health",
        }
    }
}

/// What the event loop asks main() to do when it needs the real terminal.
pub enum ExitRequest {
    Quit,
    /// Navigation/state-only result; keep looping without touching the terminal.
    Noop,
    /// Suspend the TUI and run this argv to completion (attach / drive),
    /// then re-enter and rescan.
    Exec(Vec<String>),
}

/// The whole application state.
pub struct App {
    pub ctx: GruContext,
    /// Shared with the scanner + capture threads so a Gru-picker switch
    /// re-targets background polling without respawning threads.
    pub scan_ctx: std::sync::Arc<std::sync::Mutex<GruContext>>,
    pub grus: Vec<GruEntry>,
    pub snapshot: Snapshot,
    pub focus: Focus,
    pub mode: Mode,

    // selection indices
    pub gru_sel: usize,
    pub project_sel: usize,
    pub role_sel: usize,

    // cockpit live view
    pub cockpit_lines: Vec<String>, // raw ANSI capture, one String per refresh
    pub cockpit_view: CockpitView,
    pub steer_buf: String,
    /// When true the cockpit is showing Gru itself (the `mos-gru` session),
    /// the top-level frame — NOT a project role. Set by `g`, cleared on back.
    pub gru_mode: bool,
    /// Context was explicitly pinned (MINIONS_ROOT/cwd) — the Gru picker is
    /// suppressed so the operator stays inside the repo they launched from.
    pub pinned: bool,

    // channels from background workers
    pub scan_rx: Receiver<Snapshot>,
    pub capture_rx: Receiver<CaptureMsg>,
    /// Async job results (haiku answers, steer toasts) posted by worker threads.
    pub jobs_rx: Receiver<JobMsg>,
    /// Cloneable sender handed to each spawned worker so it can post back.
    pub jobs_tx: Sender<JobMsg>,

    /// Count of background jobs currently in flight (haiku/steer/gru sends).
    /// Drives the global activity spinner — a non-zero count means "working".
    pub inflight: u32,
    /// Monotonic request-id source; each async ask/kick claims the next id so a
    /// late reply can be matched to (or rejected by) the current UI state.
    pub next_req: u64,
    /// Animation frame, advanced once per render tick. Drives every spinner so
    /// the UI visibly *moves* whenever something is live.
    pub spin: usize,
    /// When the last fresh scanner snapshot landed — powers "updated Ns ago".
    pub last_snapshot_at: Instant,
    /// When the last cockpit capture frame landed — powers the live pulse dot.
    pub last_capture_at: Instant,

    pub should_quit: bool,
    pub last_error: Option<String>,
}

/// A capture-pane refresh for the cockpit, tagged with its session so a stale
/// capture for a since-changed selection is dropped.
#[derive(Debug, Clone)]
pub struct CaptureMsg {
    pub session: String,
    pub raw: String,
}

impl App {
    pub fn new(
        ctx: GruContext,
        scan_ctx: std::sync::Arc<std::sync::Mutex<GruContext>>,
        grus: Vec<GruEntry>,
        scan_rx: Receiver<Snapshot>,
        capture_rx: Receiver<CaptureMsg>,
    ) -> Self {
        let multi_gru = grus.len() > 1;
        // Start at the Gru picker only when the install was NOT explicitly
        // pinned (via MINIONS_ROOT or cwd). A pinned context means "use THIS
        // repo" — skip the picker and go straight to its projects.
        let pinned = ctx.id == "env" || ctx.id == "cwd";
        let start_focus = if multi_gru && !pinned {
            Focus::GruPicker
        } else {
            Focus::Projects
        };
        let (jobs_tx, jobs_rx) = mpsc::channel();
        let now = Instant::now();
        App {
            ctx,
            scan_ctx,
            grus,
            snapshot: Snapshot::default(),
            focus: start_focus,
            mode: Mode::Normal,
            gru_sel: 0,
            project_sel: 0,
            role_sel: 0,
            cockpit_lines: Vec::new(),
            cockpit_view: CockpitView::Live,
            steer_buf: String::new(),
            gru_mode: false,
            pinned,
            scan_rx,
            capture_rx,
            jobs_rx,
            jobs_tx,
            inflight: 0,
            next_req: 1,
            spin: 0,
            last_snapshot_at: now,
            last_capture_at: now,
            should_quit: false,
            last_error: None,
        }
    }

    /// Claim the next request id (for matching an async reply to UI state).
    pub fn claim_req(&mut self) -> u64 {
        let r = self.next_req;
        self.next_req += 1;
        r
    }

    /// Re-root the active Gru context (from the picker). Updates both the
    /// owned copy used by write-actions and the shared cell the scanner reads.
    pub fn switch_gru(&mut self, idx: usize) {
        let Some(entry) = self.grus.get(idx) else {
            return;
        };
        let ctx = crate::config::context_from_entry(entry);
        if let Ok(mut g) = self.scan_ctx.lock() {
            *g = ctx.clone();
        }
        self.ctx = ctx;
        self.snapshot = Snapshot::default(); // force a clean re-scan
        self.project_sel = 0;
        self.role_sel = 0;
    }

    /// Drain background channels (non-blocking). Called once per loop iter.
    pub fn tick(&mut self) {
        // Advance the global animation frame so every spinner moves each tick.
        self.spin = self.spin.wrapping_add(1);

        while let Ok(snap) = self.scan_rx.try_recv() {
            if let Some(e) = &snap.error {
                self.last_error = Some(e.clone());
            }
            self.snapshot = snap;
            self.last_snapshot_at = Instant::now();
            self.clamp_selection();
        }
        // Keep only the latest capture matching the current session.
        let want = self.current_session();
        while let Ok(msg) = self.capture_rx.try_recv() {
            if Some(&msg.session) == want.as_ref() {
                self.cockpit_lines = msg.raw.lines().map(|s| s.to_string()).collect();
                self.last_capture_at = Instant::now();
            }
        }
        // Drain async job results (haiku answers, steer toasts).
        while let Ok(job) = self.jobs_rx.try_recv() {
            self.apply_job(job);
        }
    }

    /// Fold a finished background job into UI state. A haiku answer is only
    /// accepted if its request id still matches the open box (otherwise the
    /// operator has since closed it or asked something newer).
    fn apply_job(&mut self, job: JobMsg) {
        self.inflight = self.inflight.saturating_sub(1);
        match job {
            JobMsg::Haiku { req, text } => {
                if let Mode::Haiku {
                    req: open_req,
                    reply,
                    busy,
                    ..
                } = &mut self.mode
                {
                    if *open_req == req {
                        *reply = match text {
                            Ok(t) => t,
                            Err(e) => format!("(haiku error: {e})"),
                        };
                        *busy = false;
                    }
                }
            }
            JobMsg::Toast(msg) => {
                // Don't stomp an open haiku box with a steer toast.
                if !matches!(self.mode, Mode::Haiku { .. }) {
                    self.mode = Mode::Toast(msg);
                }
            }
            JobMsg::Config {
                high: h,
                medium: m,
                window: w,
            } => {
                // Only fold into a Settings panel the operator hasn't edited yet.
                if let Mode::Settings {
                    high,
                    medium,
                    window,
                    dirty,
                    loaded,
                    ..
                } = &mut self.mode
                {
                    if !*dirty {
                        *high = h;
                        *medium = m;
                        *window = w;
                        *loaded = true;
                    }
                }
            }
        }
    }

    /// Is any background work in flight right now?
    pub fn is_busy(&self) -> bool {
        self.inflight > 0
    }

    /// Current spinner glyph for the global animation frame.
    pub fn spinner(&self) -> &'static str {
        SPIN[self.spin % SPIN.len()]
    }

    fn clamp_selection(&mut self) {
        let np = self.snapshot.projects.len();
        if self.project_sel >= np && np > 0 {
            self.project_sel = np - 1;
        }
        if let Some(p) = self.snapshot.projects.get(self.project_sel) {
            let nr = p.roles.len();
            if self.role_sel >= nr && nr > 0 {
                self.role_sel = nr - 1;
            }
        }
    }

    pub fn current_project(&self) -> Option<&crate::scanner::ProjectStatus> {
        self.snapshot.projects.get(self.project_sel)
    }

    pub fn current_role(&self) -> Option<&crate::scanner::RoleStatus> {
        self.current_project()?.roles.get(self.role_sel)
    }

    /// The tmux session name the cockpit should be displaying, if any.
    /// In Gru mode this is always the `mos-gru` frame session.
    pub fn current_session(&self) -> Option<String> {
        if self.gru_mode {
            return Some(crate::gru::GRU_SESSION.to_string());
        }
        self.current_role().map(|r| r.session_name.clone())
    }

    /// Is the Gru frame session live? (cheap; used for the cockpit status line)
    pub fn gru_alive(&self) -> bool {
        crate::gru::gru_alive()
    }
}

