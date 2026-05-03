//! Deterministic runtime contracts for MinionsOS V5.
//!
//! This crate intentionally does not talk to EACN3 and does not contain prompt,
//! tool, or research workflow logic. It is a small Rust kernel for decisions
//! that should be stable across the Python runtime: phase eligibility and
//! explicit EACN task-target wake hints.

use std::collections::BTreeSet;

/// Runtime state for a registered MinionsOS role.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RoleState {
    Active,
    Sleeping,
    Dismissed,
    Other(String),
}

impl RoleState {
    /// Convert a persisted Python state string into a Rust enum.
    pub fn from_persisted(value: &str) -> Self {
        match value {
            "active" => Self::Active,
            "sleeping" => Self::Sleeping,
            "dismissed" => Self::Dismissed,
            other => Self::Other(other.to_string()),
        }
    }

    /// True if this role can be considered for local wake dispatch.
    pub fn schedulable(&self) -> bool {
        matches!(self, Self::Active | Self::Sleeping)
    }
}

/// Minimal role record needed by runtime contracts.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RoleRecord {
    pub name: String,
    pub state: RoleState,
    pub eacn_agent_id: Option<String>,
    pub domains: BTreeSet<String>,
}

impl RoleRecord {
    pub fn new(
        name: impl Into<String>,
        state: RoleState,
        eacn_agent_id: Option<String>,
        domains: impl IntoIterator<Item = impl Into<String>>,
    ) -> Self {
        Self {
            name: name.into(),
            state,
            eacn_agent_id,
            domains: domains.into_iter().map(Into::into).collect(),
        }
    }
}

/// Project phase snapshot used to decide which roles may go online.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct PhasePolicy {
    pub current_phase: Option<String>,
    pub version: u64,
    pub allowed_roles: BTreeSet<String>,
}

impl PhasePolicy {
    /// Return true when the phase allows a role to work.
    ///
    /// Empty allow-list means legacy/open scheduling. `*` and `all` are explicit
    /// wildcards and match every role.
    pub fn allows_role(&self, role_name: &str) -> bool {
        self.allowed_roles.is_empty()
            || self.allowed_roles.contains("*")
            || self.allowed_roles.contains("all")
            || self.allowed_roles.contains(role_name)
    }

    /// Return active/sleeping non-Gru roles allowed by the phase policy.
    pub fn online_roles(&self, roles: &[RoleRecord]) -> Vec<String> {
        roles
            .iter()
            .filter(|role| role.state.schedulable())
            .filter(|role| role.name != "gru")
            .filter(|role| self.allows_role(&role.name))
            .map(|role| role.name.clone())
            .collect()
    }
}

/// Minimal EACN task metadata needed for explicit invitation wake hints.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct TaskRecord {
    pub task_id: Option<String>,
    pub domains: BTreeSet<String>,
    pub invited_agent_ids: BTreeSet<String>,
    pub invited_roles: BTreeSet<String>,
}

impl TaskRecord {
    pub fn new(
        task_id: Option<impl Into<String>>,
        domains: impl IntoIterator<Item = impl Into<String>>,
        invited_agent_ids: impl IntoIterator<Item = impl Into<String>>,
        invited_roles: impl IntoIterator<Item = impl Into<String>>,
    ) -> Self {
        Self {
            task_id: task_id.map(Into::into),
            domains: domains.into_iter().map(Into::into).collect(),
            invited_agent_ids: invited_agent_ids.into_iter().map(Into::into).collect(),
            invited_roles: invited_roles.into_iter().map(Into::into).collect(),
        }
    }
}

/// Why a role was selected for an explicit task wake hint.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MatchReason {
    InvitedAgentIds,
    InvitedRoles,
}

impl MatchReason {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::InvitedAgentIds => "invited_agent_ids",
            Self::InvitedRoles => "invited_roles",
        }
    }
}

/// An explicit EACN task wake target.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouterTarget {
    pub role_name: String,
    pub reason: MatchReason,
}

/// Return explicitly invited local role targets for a task.
///
/// This mirrors MinionsOS V5's Python-side contract:
/// - EACN3 owns domain routing and writes native task broadcasts to each agent queue;
/// - MinionsOS may only create wake hints for explicit invitations it can see;
/// - dismissed roles are ignored.
pub fn explicit_task_targets(roles: &[RoleRecord], task: &TaskRecord) -> Vec<RouterTarget> {
    let mut matches = Vec::new();
    for role in roles {
        if !role.state.schedulable() {
            continue;
        }
        if task.invited_roles.contains(&role.name) {
            matches.push(RouterTarget {
                role_name: role.name.clone(),
                reason: MatchReason::InvitedRoles,
            });
            continue;
        }
        let agent_id = role.eacn_agent_id.as_deref().unwrap_or(role.name.as_str());
        if task.invited_agent_ids.contains(agent_id) || task.invited_agent_ids.contains(&role.name)
        {
            matches.push(RouterTarget {
                role_name: role.name.clone(),
                reason: MatchReason::InvitedAgentIds,
            });
        }
    }
    matches
}

#[cfg(test)]
mod tests {
    use super::*;

    fn domains(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    fn role(name: &str, state: RoleState, role_domains: &[&str]) -> RoleRecord {
        RoleRecord::new(
            name,
            state,
            Some(format!("{name}-agent")),
            domains(role_domains),
        )
    }

    #[test]
    fn phase_empty_allow_list_keeps_legacy_open_scheduling() {
        let policy = PhasePolicy::default();
        assert!(policy.allows_role("coder"));
        assert!(policy.allows_role("reviewer"));
    }

    #[test]
    fn phase_online_roles_excludes_gru_and_dismissed_roles() {
        let policy = PhasePolicy {
            current_phase: Some("experiment".to_string()),
            version: 3,
            allowed_roles: BTreeSet::from(["coder".to_string(), "experimenter".to_string()]),
        };
        let roles = vec![
            role("gru", RoleState::Active, &["coordination"]),
            role("coder", RoleState::Sleeping, &["coding"]),
            role("experimenter", RoleState::Active, &["experiments"]),
            role("writer", RoleState::Active, &["writing"]),
            role("reviewer", RoleState::Dismissed, &["review"]),
        ];
        assert_eq!(policy.online_roles(&roles), vec!["coder", "experimenter"]);
    }

    #[test]
    fn public_task_domains_do_not_create_minionsos_targets() {
        let roles = vec![
            role(
                "coder",
                RoleState::Active,
                &["minionsos", "project-local", "coding"],
            ),
            role(
                "writer",
                RoleState::Active,
                &["minionsos", "project-local", "writing"],
            ),
        ];
        let task = TaskRecord::new(
            Some("t-generic"),
            domains(&["minionsos", "project-local"]),
            Vec::<String>::new(),
            Vec::<String>::new(),
        );
        assert!(explicit_task_targets(&roles, &task).is_empty());
    }

    #[test]
    fn public_task_domain_routing_is_left_to_eacn3() {
        let roles = vec![
            role("gru", RoleState::Active, &["coordination"]),
            role("noter", RoleState::Active, &["status"]),
            role(
                "coder",
                RoleState::Sleeping,
                &["minionsos", "coding", "debugging"],
            ),
            role("writer", RoleState::Active, &["writing"]),
        ];
        let task = TaskRecord::new(
            Some("t-coding"),
            domains(&["coding"]),
            Vec::<String>::new(),
            Vec::<String>::new(),
        );
        assert!(explicit_task_targets(&roles, &task).is_empty());
    }

    #[test]
    fn invited_roles_bypass_domain_matching_but_not_schedulability() {
        let roles = vec![
            role("coder", RoleState::Active, &["coding"]),
            role("writer", RoleState::Sleeping, &["writing"]),
            role("reviewer", RoleState::Dismissed, &["review"]),
        ];
        let task = TaskRecord::new(
            Some("t-invited"),
            domains(&["unknown"]),
            Vec::<String>::new(),
            domains(&["writer", "reviewer"]),
        );
        assert_eq!(
            explicit_task_targets(&roles, &task),
            vec![RouterTarget {
                role_name: "writer".to_string(),
                reason: MatchReason::InvitedRoles,
            }]
        );
    }

    #[test]
    fn invited_agent_ids_match_agent_id_or_role_name() {
        let roles = vec![
            role("coder", RoleState::Active, &["coding"]),
            RoleRecord::new(
                "expert-dl",
                RoleState::Active,
                Some("expert-agent-1".to_string()),
                domains(&["expert", "analysis"]),
            ),
        ];
        let task = TaskRecord::new(
            Some("t-agent"),
            domains(&["unknown"]),
            domains(&["expert-agent-1", "coder"]),
            Vec::<String>::new(),
        );
        assert_eq!(
            explicit_task_targets(&roles, &task),
            vec![
                RouterTarget {
                    role_name: "coder".to_string(),
                    reason: MatchReason::InvitedAgentIds,
                },
                RouterTarget {
                    role_name: "expert-dl".to_string(),
                    reason: MatchReason::InvitedAgentIds,
                },
            ]
        );
    }
}
