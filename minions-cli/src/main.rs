use anyhow::Result;
use clap::{Parser, Subcommand};
use minions_core::{Project, ProjectStatus, StateStore};
use tabled::{Table, Tabled};

#[derive(Parser)]
#[command(name = "mos")]
#[command(about = "MinionsOS — project and role management CLI (Rust edition)", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Show a dashboard of all projects and their health
    Status,

    /// Project management commands
    Project {
        #[command(subcommand)]
        command: ProjectCommands,
    },

    /// Role management commands
    Role {
        #[command(subcommand)]
        command: RoleCommands,
    },
}

#[derive(Subcommand)]
enum ProjectCommands {
    /// List all projects
    List,

    /// Show details for a specific project
    Show {
        /// Project port
        port: u16,
    },
}

#[derive(Subcommand)]
enum RoleCommands {
    /// List roles for a project
    List {
        /// Project port
        port: u16,
    },
}

#[derive(Tabled)]
struct ProjectRow {
    #[tabled(rename = "Port")]
    port: u16,

    #[tabled(rename = "Name")]
    name: String,

    #[tabled(rename = "Status")]
    status: String,

    #[tabled(rename = "Phase")]
    phase: String,

    #[tabled(rename = "Active Roles")]
    active_roles: usize,

    #[tabled(rename = "Created")]
    created: String,
}

impl From<&Project> for ProjectRow {
    fn from(p: &Project) -> Self {
        let status = match p.status {
            ProjectStatus::Active => "active",
            ProjectStatus::Dormant => "dormant",
            ProjectStatus::Closed => "closed",
        };

        let active_role_count = p.active_roles.iter()
            .filter(|r| r.state != minions_core::RoleState::Dismissed)
            .count();

        Self {
            port: p.port,
            name: p.real_name.clone(),
            status: status.to_string(),
            phase: p.current_phase.clone().unwrap_or_else(|| "-".to_string()),
            active_roles: active_role_count,
            created: p.created.format("%Y-%m-%d").to_string(),
        }
    }
}

#[derive(Tabled)]
struct RoleRow {
    #[tabled(rename = "Name")]
    name: String,

    #[tabled(rename = "State")]
    state: String,

    #[tabled(rename = "PID")]
    pid: String,

    #[tabled(rename = "Session")]
    session: String,

    #[tabled(rename = "Last Seen")]
    last_seen: String,
}

impl From<&minions_core::RoleInfo> for RoleRow {
    fn from(r: &minions_core::RoleInfo) -> Self {
        let state = match r.state {
            minions_core::RoleState::Active => "active",
            minions_core::RoleState::Idle => "idle",
            minions_core::RoleState::Dismissed => "dismissed",
        };

        let pid = r.pid.map(|p| p.to_string()).unwrap_or_else(|| "-".to_string());

        let last_seen = r.last_seen
            .map(|dt| dt.format("%H:%M:%S").to_string())
            .unwrap_or_else(|| "-".to_string());

        Self {
            name: r.name.clone(),
            state: state.to_string(),
            pid,
            session: r.session_name.clone(),
            last_seen,
        }
    }
}

fn cmd_status(store: &StateStore) -> Result<()> {
    let projects = store.load_projects()?;

    if projects.is_empty() {
        println!("No projects found.");
        return Ok(());
    }

    let rows: Vec<ProjectRow> = projects.iter().map(ProjectRow::from).collect();
    let table = Table::new(rows).to_string();

    println!("{}", table);
    println!("\nTotal: {} projects", projects.len());

    Ok(())
}

fn cmd_project_list(store: &StateStore) -> Result<()> {
    cmd_status(store)
}

fn cmd_project_show(store: &StateStore, port: u16) -> Result<()> {
    let project = store.load_project(port)?
        .ok_or_else(|| anyhow::anyhow!("Project {} not found", port))?;

    println!("Project: {}", project.real_name);
    println!("Port: {}", project.port);
    println!("Status: {:?}", project.status);
    println!("Phase: {}", project.current_phase.as_deref().unwrap_or("-"));
    println!("Created: {}", project.created);

    if !project.active_roles.is_empty() {
        println!("\nRoles:");
        let rows: Vec<RoleRow> = project.active_roles.iter().map(RoleRow::from).collect();
        let table = Table::new(rows).to_string();
        println!("{}", table);
    }

    Ok(())
}

fn cmd_role_list(store: &StateStore, port: u16) -> Result<()> {
    let project = store.load_project(port)?
        .ok_or_else(|| anyhow::anyhow!("Project {} not found", port))?;

    if project.active_roles.is_empty() {
        println!("No roles in project {}", port);
        return Ok(());
    }

    let rows: Vec<RoleRow> = project.active_roles.iter().map(RoleRow::from).collect();
    let table = Table::new(rows).to_string();

    println!("{}", table);
    println!("\nTotal: {} roles", project.active_roles.len());

    Ok(())
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let store = StateStore::new();

    if !store.exists() {
        eprintln!("Error: projects.json not found");
        eprintln!("Make sure MinionsOS is initialized and MINIONS_STATE_DIR is set correctly");
        std::process::exit(1);
    }

    match cli.command {
        Commands::Status => cmd_status(&store),
        Commands::Project { command } => match command {
            ProjectCommands::List => cmd_project_list(&store),
            ProjectCommands::Show { port } => cmd_project_show(&store, port),
        },
        Commands::Role { command } => match command {
            RoleCommands::List { port } => cmd_role_list(&store, port),
        },
    }
}
