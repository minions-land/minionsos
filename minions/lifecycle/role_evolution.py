"""Role evolution: data-driven SPLIT, MERGE, and DISMISS for Roles.

Design (matches the docs/research/role-evolution-experiments.md findings):

  - Trigger is **evidence-gated, not diversity-gated**. Three primitives:

      SPLIT   — one role becomes several specialists. Requires repeated
                artifact-grounded failures of the same Role attributable
                to a partition of its work into >= 2 distinct sub-domains.

      MERGE   — two active Roles fuse into one. Triggered ONLY by
                behavioural convergence (artifact-overlap >= threshold).
                Roles do NOT need to share a SPLIT lineage; two
                independently-spawned Experts that have grown into the
                same scope are valid merge candidates.

      DISMISS — a Role with no recent work is retired. Distinct from
                MERGE because a Role with no work is not something to
                fuse into another Role's scope; it is something that
                should stop existing. If new work appears later that no
                active Role can cover, a separate spawn trigger handles
                it.

  - This module is pure logic. It reads project artifacts, computes
    scores, and returns a structured recommendation. It does NOT perform
    spawn / dismiss; the operator (Gru, or an MCP tool) must invoke
    ``apply_split`` / ``apply_merge`` / ``apply_dismiss`` separately.

  - Cooldown: a Role that was just split, merged, or dismissed is in a
    protective window during which it cannot be re-evaluated. This
    prevents oscillation where a fresh specialist is killed for
    starvation before it has time to receive any work.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from minions.paths import project_shared_workspace, project_workspace_root
from minions.state.store import StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables (overridable via gru.yaml :: role_evolution.*)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tunables:
    """Trigger thresholds. All overridable via gru.yaml."""

    # SPLIT
    split_min_failures: int = 5
    split_min_subdomains: int = 2
    split_min_per_subdomain: int = 3
    split_recent_window_hours: float = 24.0

    # DISMISS-by-starvation (was MERGE-by-starvation; renamed because the
    # right primitive for "no work" is retirement, not fusion).
    dismiss_starve_min_age_hours: float = 6.0
    dismiss_starve_max_tasks: int = 1
    dismiss_starve_min_consecutive_evals: int = 2

    # MERGE-by-convergence
    merge_convergence_threshold: float = 0.75
    merge_convergence_min_consecutive_evals: int = 2

    # Protective cooldown
    cooldown_after_split_hours: float = 12.0
    cooldown_after_merge_hours: float = 6.0
    cooldown_after_dismiss_hours: float = 6.0


_DEFAULT_TUNABLES = Tunables()


def load_tunables(gru_config: dict | None = None) -> Tunables:
    cfg = (gru_config or {}).get("role_evolution") or {}
    base = _DEFAULT_TUNABLES

    # Back-compat: earlier versions called these merge_starve_*. Accept the
    # old keys but prefer the new dismiss_starve_* names.
    merge_starve_age_legacy = cfg.get("merge_starve_min_age_hours")
    merge_starve_max_legacy = cfg.get("merge_starve_max_tasks")
    merge_starve_consec_legacy = cfg.get("merge_starve_min_consecutive_evals")

    return Tunables(
        split_min_failures=int(cfg.get("split_min_failures", base.split_min_failures)),
        split_min_subdomains=int(cfg.get("split_min_subdomains", base.split_min_subdomains)),
        split_min_per_subdomain=int(
            cfg.get("split_min_per_subdomain", base.split_min_per_subdomain)
        ),
        split_recent_window_hours=float(
            cfg.get("split_recent_window_hours", base.split_recent_window_hours)
        ),
        dismiss_starve_min_age_hours=float(
            cfg.get(
                "dismiss_starve_min_age_hours",
                merge_starve_age_legacy
                if merge_starve_age_legacy is not None
                else base.dismiss_starve_min_age_hours,
            )
        ),
        dismiss_starve_max_tasks=int(
            cfg.get(
                "dismiss_starve_max_tasks",
                merge_starve_max_legacy
                if merge_starve_max_legacy is not None
                else base.dismiss_starve_max_tasks,
            )
        ),
        dismiss_starve_min_consecutive_evals=int(
            cfg.get(
                "dismiss_starve_min_consecutive_evals",
                merge_starve_consec_legacy
                if merge_starve_consec_legacy is not None
                else base.dismiss_starve_min_consecutive_evals,
            )
        ),
        merge_convergence_threshold=float(
            cfg.get("merge_convergence_threshold", base.merge_convergence_threshold)
        ),
        merge_convergence_min_consecutive_evals=int(
            cfg.get(
                "merge_convergence_min_consecutive_evals",
                base.merge_convergence_min_consecutive_evals,
            )
        ),
        cooldown_after_split_hours=float(
            cfg.get("cooldown_after_split_hours", base.cooldown_after_split_hours)
        ),
        cooldown_after_merge_hours=float(
            cfg.get("cooldown_after_merge_hours", base.cooldown_after_merge_hours)
        ),
        cooldown_after_dismiss_hours=float(
            cfg.get("cooldown_after_dismiss_hours", base.cooldown_after_dismiss_hours)
        ),
    )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FailureEvent:
    """One artifact-grounded failure attributable to a Role."""

    role_name: str
    when: datetime
    source: Literal["ethics", "review", "experiment", "selfreport"]
    text: str
    artifact_path: str  # path under branches/shared/...

    @property
    def age_hours(self) -> float:
        return (datetime.now(UTC) - self.when).total_seconds() / 3600.0


@dataclass
class FailureCluster:
    """Cluster of failure events sharing a sub-domain label."""

    label: str
    events: list[FailureEvent] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.events)


@dataclass
class RoleStats:
    """Per-role activity stats over the recent window."""

    role_name: str
    age_hours: float  # since spawn
    age_since_last_evolution_hours: float | None  # None if never evolved
    n_tasks_recent: int
    n_messages_recent: int
    artifacts_recent: list[str]  # shared subdir paths


@dataclass
class SplitDecision:
    decision: Literal["SPLIT", "KEEP"]
    role: str
    reason: str
    clusters: list[FailureCluster] = field(default_factory=list)
    proposed_specialists: list[dict] = field(default_factory=list)


@dataclass
class MergeDecision:
    decision: Literal["MERGE", "KEEP"]
    kind: Literal["convergence", "none"]
    roles: list[str] = field(default_factory=list)
    reason: str = ""
    proposed_role: dict | None = None
    convergence_score: float | None = None


@dataclass
class DismissDecision:
    """A starved Role that should simply be retired, not merged.

    Conceptually distinct from MERGE: a Role with no recent work is not
    something we want to fuse into another Role's scope — it is something
    that should stop existing. If new work appears later that needs the
    same coverage, a fresh spawn is the right answer (separate trigger,
    not part of this evaluation).
    """

    decision: Literal["DISMISS", "KEEP"]
    role: str
    reason: str = ""
    n_tasks_recent: int = 0
    age_hours: float = 0.0


@dataclass
class EvaluationReport:
    """Full set of recommendations from one evaluation pass."""

    project_port: int
    when: datetime
    splits: list[SplitDecision] = field(default_factory=list)
    merges: list[MergeDecision] = field(default_factory=list)
    dismisses: list[DismissDecision] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Signal collection
# ---------------------------------------------------------------------------


_ROLE_TAG = re.compile(r"\b(noter|coder|writer|ethics|gru|expert-[a-z0-9-]+)\b", re.I)
_ARTIFACT_AGE_DAYS_LIMIT = 30


def _shared_dir(project_port: int) -> Path:
    return project_shared_workspace(project_port)


def _read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _walk_recent(root: Path, window_hours: float) -> Iterable[Path]:
    """Yield files under root with mtime within the window."""
    if not root.exists():
        return
    cutoff = time.time() - window_hours * 3600.0
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime >= cutoff:
                yield p
        except OSError:
            continue


def collect_failure_events(
    project_port: int,
    window_hours: float,
) -> list[FailureEvent]:
    """Collect artifact-grounded failure events from shared/.

    Sources:
      - Ethics reports under shared/ethics/
      - Review packets under shared/reviews/round-*/
      - Experiment reports under shared/exp/exp-*/report.md whose
        first non-blank line begins with FAIL or whose body contains
        'FAILED' / 'error:'
      - Draft self-reports tagged with [evidence:...] and "wrong"/"failed"

    Each event must mention a Role name to be attributable. Unattributed
    failures are dropped (the trigger requires per-Role evidence).
    """
    shared = _shared_dir(project_port)
    events: list[FailureEvent] = []

    # Ethics — every report in shared/ethics is treated as a failure event
    # (Ethics writes there only when it has flagged something).
    for p in _walk_recent(shared / "ethics", window_hours):
        text = _read_text_safe(p)
        for role in _attributable_roles(text):
            events.append(
                FailureEvent(
                    role_name=role,
                    when=_mtime(p),
                    source="ethics",
                    text=text[:2000],
                    artifact_path=str(p.relative_to(shared.parent)),
                )
            )

    # Review — consolidated.md lines flagged "Reviewer recommends Major Revisions"
    for p in _walk_recent(shared / "reviews", window_hours):
        if p.name not in {"consolidated.md", "summary.md"}:
            continue
        text = _read_text_safe(p)
        if not _has_review_failure_signal(text):
            continue
        for role in _attributable_roles(text):
            events.append(
                FailureEvent(
                    role_name=role,
                    when=_mtime(p),
                    source="review",
                    text=text[:2000],
                    artifact_path=str(p.relative_to(shared.parent)),
                )
            )

    # Experiment failures
    for p in _walk_recent(shared / "exp", window_hours):
        if p.name != "report.md":
            continue
        text = _read_text_safe(p)
        if not _has_experiment_failure_signal(text):
            continue
        # Expert (the unified worker) owns experiments
        events.append(
            FailureEvent(
                role_name="expert",
                when=_mtime(p),
                source="experiment",
                text=text[:2000],
                artifact_path=str(p.relative_to(shared.parent)),
            )
        )

    return events


def _mtime(p: Path) -> datetime:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)


def _attributable_roles(text: str) -> list[str]:
    """Pull lowercased role-name mentions from a text blob."""
    found: list[str] = []
    for m in _ROLE_TAG.finditer(text):
        name = m.group(0).lower()
        if name not in found:
            found.append(name)
    return found


_REVIEW_FAIL_SIGNALS = ("major revisions", "reject", "fundamental flaw", "unsupported claim")


def _has_review_failure_signal(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in _REVIEW_FAIL_SIGNALS)


def _has_experiment_failure_signal(text: str) -> bool:
    low = text.lower()
    if low.startswith("fail") or "\nfail" in low[:200]:
        return True
    return ("status: failed" in low) or ("traceback" in low) or ("error:" in low[:1000])


# ---------------------------------------------------------------------------
# Failure clustering
# ---------------------------------------------------------------------------

# Sub-domain inference: lowercased keyword -> cluster label. Order matters;
# first match wins. The list is intentionally short — we want clusters to
# emerge from real artifacts, not from a fixed taxonomy. Operators can extend
# this via gru.yaml :: role_evolution.subdomain_keywords.
_DEFAULT_SUBDOMAIN_KEYWORDS: list[tuple[str, str]] = [
    ("convergence", "optimization"),
    ("gradient", "optimization"),
    ("loss", "optimization"),
    ("regression", "statistics"),
    ("p-value", "statistics"),
    ("significance", "statistics"),
    ("hypothesis", "statistics"),
    ("dataset", "data"),
    ("preprocess", "data"),
    ("annotation", "data"),
    ("bias", "ethics"),
    ("consent", "ethics"),
    ("privacy", "ethics"),
    ("citation", "scholarship"),
    ("plagiarism", "scholarship"),
    ("reproducibility", "scholarship"),
]


def cluster_failures(
    events,
    keyword_table=None,
):
    """Bucket failures into sub-domain clusters by keyword match.

    Events that match no keyword fall into the ``misc`` bucket and are
    NOT counted toward the SPLIT trigger (we require labeled clusters
    so the supervisor can name a sub-domain).
    """
    table = keyword_table or _DEFAULT_SUBDOMAIN_KEYWORDS
    buckets: dict[str, FailureCluster] = {}
    for ev in events:
        low = ev.text.lower()
        label = "misc"
        for kw, lbl in table:
            if kw in low:
                label = lbl
                break
        bucket = buckets.setdefault(label, FailureCluster(label=label))
        bucket.events.append(ev)
    return list(buckets.values())


# ---------------------------------------------------------------------------
# Role stats — used by both starvation and convergence
# ---------------------------------------------------------------------------


def collect_role_stats(
    project,
    window_hours: float,
):
    """Per-Role activity summary over the recent window."""
    out: dict[str, RoleStats] = {}
    now = datetime.now(UTC)
    shared = _shared_dir(project.port)
    project_root = project_workspace_root(project.port)

    for r in project.active_roles:
        if r.state != "active":
            continue
        spawned = _parse_iso(r.spawned_at) if r.spawned_at else now
        age_h = (now - spawned).total_seconds() / 3600.0
        last_evolved_at = _last_role_evolution_time(project.port, r.name)
        age_since_evol = (
            (now - last_evolved_at).total_seconds() / 3600.0 if last_evolved_at else None
        )

        artifacts: list[str] = []
        candidate_roots = [project_root / "branches" / r.name]
        for sub in ("notes", "ethics", "exp", "handoffs", "draft"):
            candidate_roots.append(shared / sub)
        for root in candidate_roots:
            for p in _walk_recent(root, window_hours):
                if r.name.lower() in str(p).lower():
                    artifacts.append(str(p))

        out[r.name] = RoleStats(
            role_name=r.name,
            age_hours=age_h,
            age_since_last_evolution_hours=age_since_evol,
            n_tasks_recent=len([a for a in artifacts if "/exp/" in a or "/handoffs/" in a]),
            n_messages_recent=len(artifacts),
            artifacts_recent=artifacts,
        )
    return out


def _parse_iso(s: str):
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Convergence score — pure pre-filter; charter LLM-judge lives separately
# ---------------------------------------------------------------------------


def convergence_score(a: RoleStats, b: RoleStats) -> float:
    """0-1 measure of artifact and directory overlap between two roles."""
    set_a = {Path(p).name for p in a.artifacts_recent}
    set_b = {Path(p).name for p in b.artifacts_recent}
    if not set_a and not set_b:
        return 0.0
    jaccard = len(set_a & set_b) / max(1, len(set_a | set_b))

    def _prefix(p: str) -> str:
        parts = Path(p).parts
        return "/".join(parts[-3:-1]) if len(parts) >= 3 else "/".join(parts[:-1])

    prefix_a = Counter(_prefix(p) for p in a.artifacts_recent)
    prefix_b = Counter(_prefix(p) for p in b.artifacts_recent)
    if prefix_a and prefix_b:
        common = sum((prefix_a & prefix_b).values())
        total = sum((prefix_a | prefix_b).values())
        prefix_overlap = common / max(1, total)
    else:
        prefix_overlap = 0.0

    return 0.6 * jaccard + 0.4 * prefix_overlap


# ---------------------------------------------------------------------------
# Decision functions
# ---------------------------------------------------------------------------


def _last_role_evolution_time(project_port: int, role_name: str):
    """Most recent SPLIT/MERGE involving this role, from the audit log."""
    log = _shared_dir(project_port) / "governance" / "role_evolution.jsonl"
    if not log.exists():
        return None
    last = None
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            roles = set(rec.get("roles_in", []) + rec.get("roles_out", []))
            if role_name in roles:
                ts = _parse_iso(rec.get("when", ""))
                if last is None or ts > last:
                    last = ts
    except OSError:
        return None
    return last


def evaluate_split(role, events, tunables=_DEFAULT_TUNABLES):
    """Decide whether *role* should be split, given its recent failures.

    Evidence-gated: clusters must be labeled, ≥ split_min_subdomains
    distinct, and each ≥ split_min_per_subdomain large. Total failures
    must exceed split_min_failures.
    """
    role_events = [e for e in events if e.role_name == role.name]
    n = len(role_events)
    if n < tunables.split_min_failures:
        return SplitDecision(
            decision="KEEP",
            role=role.name,
            reason=f"Only {n} attributable failure(s); threshold is {tunables.split_min_failures}.",
        )
    clusters = cluster_failures(role_events)
    labeled = [c for c in clusters if c.label != "misc" and c.n >= tunables.split_min_per_subdomain]
    if len(labeled) < tunables.split_min_subdomains:
        return SplitDecision(
            decision="KEEP",
            role=role.name,
            reason=(
                f"{n} failures but only {len(labeled)} sub-domain(s) with >= "
                f"{tunables.split_min_per_subdomain} events; need "
                f"{tunables.split_min_subdomains}."
            ),
            clusters=clusters,
        )
    proposed = [
        {
            "name": f"{role.name}-{c.label}",
            "charter": f"Specialist for {c.label} concerns previously handled by {role.name}.",
            "pitfalls": _summarize_pitfalls(c.events),
        }
        for c in labeled
    ]
    return SplitDecision(
        decision="SPLIT",
        role=role.name,
        reason=(
            f"{n} attributable failures clustered into {len(labeled)} sub-domains: "
            + ", ".join(f"{c.label}({c.n})" for c in labeled)
        ),
        clusters=clusters,
        proposed_specialists=proposed,
    )


def _summarize_pitfalls(events):
    parts = []
    for e in events[:3]:
        first = e.text.strip().split(".")[0][:200]
        parts.append(first)
    return " | ".join(parts) or "see linked artifacts"


def evaluate_merge(project, stats, tunables=_DEFAULT_TUNABLES):
    """Find merge candidates: convergence only.

    Starvation is NOT a merge case — a Role with no work should be
    dismissed (see ``evaluate_dismiss``), not fused into another Role's
    scope. Merge is reserved for the case where two active Roles have
    converged in behaviour and one of them is redundant.
    """
    out = []
    names = sorted(stats.keys())
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            sc = convergence_score(stats[a], stats[b])
            if sc >= tunables.merge_convergence_threshold:
                out.append(
                    MergeDecision(
                        decision="MERGE",
                        kind="convergence",
                        roles=[a, b],
                        reason=(
                            f"{a} and {b} have artifact-overlap score {sc:.2f} >= "
                            f"{tunables.merge_convergence_threshold:.2f}."
                        ),
                        proposed_role={
                            "name": f"{a}-{b}-merged",
                            "charter": (f"Unified role covering both {a} and {b} recent scope."),
                            "pitfalls": (
                                "Audit handoffs from both predecessors before "
                                "discarding either pending tasks."
                            ),
                        },
                        convergence_score=sc,
                    )
                )
    return out


def evaluate_dismiss(stats, tunables=_DEFAULT_TUNABLES):
    """Find roles that should be dismissed for lack of work.

    A Role with age >= dismiss_starve_min_age_hours and recent task count
    <= dismiss_starve_max_tasks is recommended for dismissal. The
    operator (or auto-apply) calls ``mos_dismiss_role`` directly; no
    replacement role is implied. If new work appears later that no
    active Role can cover, a separate spawn trigger handles it.
    """
    out: list[DismissDecision] = []
    for name, s in stats.items():
        if s.age_hours < tunables.dismiss_starve_min_age_hours:
            continue
        if s.n_tasks_recent <= tunables.dismiss_starve_max_tasks:
            out.append(
                DismissDecision(
                    decision="DISMISS",
                    role=name,
                    reason=(
                        f"{name}: only {s.n_tasks_recent} task(s) in last window, "
                        f"age {s.age_hours:.1f}h."
                    ),
                    n_tasks_recent=s.n_tasks_recent,
                    age_hours=s.age_hours,
                )
            )
    return out


# ---------------------------------------------------------------------------
# Top-level evaluator + audit log
# ---------------------------------------------------------------------------


def evaluate(project_port: int, store=None, tunables=_DEFAULT_TUNABLES):
    store = store or StateStore()
    project = store.get_project(project_port)
    if project is None:
        raise ValueError(f"project {project_port} not found")

    events = collect_failure_events(project_port, tunables.split_recent_window_hours)
    stats = collect_role_stats(project, tunables.split_recent_window_hours)

    now = datetime.now(UTC)

    def _in_cooldown(role_name):
        last = _last_role_evolution_time(project_port, role_name)
        if last is None:
            return False
        hours = (now - last).total_seconds() / 3600.0
        return hours < max(
            tunables.cooldown_after_split_hours,
            tunables.cooldown_after_merge_hours,
            tunables.cooldown_after_dismiss_hours,
        )

    splits = []
    for r in project.active_roles:
        if r.state != "active":
            continue
        if _in_cooldown(r.name):
            splits.append(
                SplitDecision(
                    decision="KEEP",
                    role=r.name,
                    reason="In post-evolution cooldown.",
                )
            )
            continue
        splits.append(evaluate_split(r, events, tunables))

    merges_raw = evaluate_merge(project, stats, tunables)
    merges = [m for m in merges_raw if not any(_in_cooldown(rn) for rn in m.roles)]

    dismisses_raw = evaluate_dismiss(stats, tunables)
    dismisses = [d for d in dismisses_raw if not _in_cooldown(d.role)]

    return EvaluationReport(
        project_port=project_port,
        when=now,
        splits=splits,
        merges=merges,
        dismisses=dismisses,
    )


def append_audit(project_port, kind, roles_in, roles_out, reason, extra=None):
    """Append a single line to branches/shared/governance/role_evolution.jsonl."""
    gov_dir = _shared_dir(project_port) / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    log = gov_dir / "role_evolution.jsonl"
    rec = {
        "when": datetime.now(UTC).isoformat(),
        "kind": kind,
        "roles_in": roles_in,
        "roles_out": roles_out,
        "reason": reason,
    }
    if extra:
        rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(log, "a", encoding="utf-8") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Apply decision: actually invoke spawn / dismiss
# ---------------------------------------------------------------------------


@dataclass
class ApplyResult:
    kind: Literal["split", "merge", "dismiss"]
    roles_in: list[str]
    roles_out: list[str]
    notes: list[str] = field(default_factory=list)


def apply_split(
    project_port,
    source_role,
    into_specs,
    evidence_refs,
    reason,
    store=None,
    dry_run=False,
):
    """Realize a SPLIT decision: spawn each specialist, dismiss the source.

    Each spec must include {name, charter, pitfalls}. Specialists are
    spawned via ``register_expert`` so they become EACN-visible Experts;
    the source role is dismissed afterwards. Failures during spawn are
    surfaced; on partial failure the source role is **kept alive** to
    avoid losing all coverage.
    """
    if not evidence_refs:
        raise ValueError("apply_split requires non-empty evidence_refs")
    if len(into_specs) < 2:
        raise ValueError("SPLIT requires at least 2 specialists")
    from minions.lifecycle.role import dismiss_role, register_expert

    store = store or StateStore()
    new_names = []
    notes = []
    if dry_run:
        new_names = [s["name"] for s in into_specs]
        notes.append("dry_run=True; no spawn or dismiss performed")
    else:
        for spec in into_specs:
            name = spec["name"]
            try:
                register_expert(
                    project_port=project_port,
                    domain=spec.get("charter", name),
                    name=name,
                    init_brief=(
                        f"You are a SPLIT child of {source_role}. "
                        f"Charter: {spec.get('charter', '')}\n"
                        f"Pitfalls observed in your parent: {spec.get('pitfalls', '')}"
                    ),
                    store=store,
                )
                new_names.append(name)
            except Exception as e:
                notes.append(f"spawn failed for {name}: {e!r}")
        if len(new_names) >= 2:
            try:
                dismiss_role(
                    project_port=project_port,
                    role_name=source_role,
                    caller="role_evolution:apply_split",
                    reason=reason,
                )
                notes.append(f"dismissed source role {source_role}")
            except Exception as e:
                notes.append(f"dismiss failed for {source_role}: {e!r}")
        else:
            notes.append("kept source role alive: not enough specialists came up")

    append_audit(
        project_port=project_port,
        kind="split",
        roles_in=[source_role],
        roles_out=new_names,
        reason=reason,
        extra={"evidence_refs": evidence_refs, "notes": notes, "dry_run": dry_run},
    )
    return ApplyResult(kind="split", roles_in=[source_role], roles_out=new_names, notes=notes)


def apply_merge(
    project_port,
    source_roles,
    into_spec,
    evidence_refs,
    reason,
    store=None,
    dry_run=False,
):
    """Realize a MERGE decision: spawn the unified role, dismiss the sources."""
    if not evidence_refs:
        raise ValueError("apply_merge requires non-empty evidence_refs")
    if len(source_roles) < 1:
        raise ValueError("MERGE requires at least 1 source role")
    from minions.lifecycle.role import dismiss_role, register_expert

    store = store or StateStore()
    notes = []
    new_name = into_spec["name"]
    if dry_run:
        notes.append("dry_run=True; no spawn or dismiss performed")
        roles_out = [new_name]
    else:
        try:
            register_expert(
                project_port=project_port,
                domain=into_spec.get("charter", new_name),
                name=new_name,
                init_brief=(
                    "You are a MERGE child of "
                    + ", ".join(source_roles)
                    + ".\nCharter: "
                    + str(into_spec.get("charter", ""))
                    + "\nPitfalls inherited: "
                    + str(into_spec.get("pitfalls", ""))
                ),
                store=store,
            )
            roles_out = [new_name]
        except Exception as e:
            notes.append(f"spawn failed for {new_name}: {e!r}")
            roles_out = []
        for src in source_roles:
            try:
                dismiss_role(
                    project_port=project_port,
                    role_name=src,
                    caller="role_evolution:apply_merge",
                    reason=reason,
                )
                notes.append(f"dismissed source role {src}")
            except Exception as e:
                notes.append(f"dismiss failed for {src}: {e!r}")

    append_audit(
        project_port=project_port,
        kind="merge",
        roles_in=source_roles,
        roles_out=roles_out,
        reason=reason,
        extra={"evidence_refs": evidence_refs, "notes": notes, "dry_run": dry_run},
    )
    return ApplyResult(kind="merge", roles_in=source_roles, roles_out=roles_out, notes=notes)


def apply_dismiss(
    project_port,
    role_name,
    evidence_refs,
    reason,
    store=None,
    dry_run=False,
):
    """Realize a DISMISS decision: retire a Role with no recent work.

    No replacement is implied. If new work appears later that no active
    Role can cover, the spawn trigger handles it (separate concern).
    Requires non-empty ``evidence_refs`` for symmetry with apply_split /
    apply_merge — typically a synthetic ``"auto:starvation:<role>"``
    string when invoked by the periodic Gru evaluator, or a
    governance-log line ref when invoked manually.
    """
    if not evidence_refs:
        raise ValueError("apply_dismiss requires non-empty evidence_refs")
    from minions.lifecycle.role import dismiss_role

    store = store or StateStore()
    notes = []
    if dry_run:
        notes.append("dry_run=True; no dismiss performed")
    else:
        try:
            dismiss_role(
                project_port=project_port,
                role_name=role_name,
                caller="role_evolution:apply_dismiss",
                reason=reason,
            )
            notes.append(f"dismissed {role_name}")
        except Exception as e:
            notes.append(f"dismiss failed for {role_name}: {e!r}")

    append_audit(
        project_port=project_port,
        kind="dismiss",
        roles_in=[role_name],
        roles_out=[],
        reason=reason,
        extra={"evidence_refs": evidence_refs, "notes": notes, "dry_run": dry_run},
    )
    return ApplyResult(kind="dismiss", roles_in=[role_name], roles_out=[], notes=notes)
