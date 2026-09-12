import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# ============================================================================
# Existing models (unchanged)
# ============================================================================


@dataclass
class Relationship:
    source_id: str
    target_id: str
    target_type: str          # mission | decision | adr | capability | risk
    relationship_type: str    # triggered_by | depends_on | supports | governed_by | informed_by | references
    confidence: float         # 0.0–1.0
    evidence: str             # text snippet that led to this extraction


@dataclass
class EntityRef:
    id: str
    type: str
    title: str
    status: str | None = None


@dataclass
class ContextPackage:
    # Identity
    entity_id: str
    entity_type: str
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    # Sections
    overview: dict[str, Any] = field(default_factory=dict)
    triggering_decisions: list[EntityRef] = field(default_factory=list)
    dependencies: list[EntityRef] = field(default_factory=list)       # missions this one depends on
    dependent_missions: list[EntityRef] = field(default_factory=list) # missions that depend on this
    capabilities_built: list[EntityRef] = field(default_factory=list)
    governing_adrs: list[EntityRef] = field(default_factory=list)
    related_decisions: list[EntityRef] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    # Quality
    completeness_score: float = 0.0
    gaps: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# ============================================================================
# WP2: New context package dataclasses
# ============================================================================

@dataclass
class HealthStatusSnapshot:
    pain_level: str | None = None
    mood: str | None = None      # low | stable | positive
    energy: str | None = None    # low | moderate | high
    stress: str | None = None    # low | moderate | high
    sleep_quality: str | None = None  # poor | fair | good


@dataclass
class HealthTrendSummary:
    pain_trend: str | None = None     # improving | stable | worsening | unknown
    energy_trend: str | None = None
    overall_direction: str | None = None


@dataclass
class HealthContextPackage:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    source_file: str = ""
    status_summary: HealthStatusSnapshot = field(default_factory=HealthStatusSnapshot)
    trend_summary: HealthTrendSummary = field(default_factory=HealthTrendSummary)
    recovery_priorities: list[str] = field(default_factory=list)
    health_themes: list[str] = field(default_factory=list)
    medical_officer_note: str | None = None
    safety_flags: list[str] = field(default_factory=list)
    workload_constraint: str | None = None  # reduced | normal | unknown
    capacity_score: int | None = None        # 0–100 from capacity_score.py
    capacity_status: str | None = None       # Green | Amber | Red | Unknown
    data_quality: str = "missing"  # complete | partial | missing

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class Recommendation:
    priority_rank: int
    mission_id: str
    title: str
    reason: str
    deadline_urgency: str          # high | medium | low | none
    confidence: float
    next_action: str
    blockers: list[str] = field(default_factory=list)
    health_constraint_note: str | None = None
    due_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BlockerContextPackage:
    mission_id: str
    mission_title: str
    priority: str
    escalation_level: str          # critical | high | medium | none
    blockers: list[dict[str, Any]] = field(default_factory=list)
    blocked_since: str | None = None
    blocker_age_days: int = 0
    dependent_missions: list[str] = field(default_factory=list)
    recommended_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionContextPackage:
    decision_id: str
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    date: str = ""
    status: str = ""
    question: str = ""
    action: str | None = None
    bottleneck: str | None = None
    related_missions: list[dict[str, Any]] = field(default_factory=list)
    awaiting_captain_input: bool = False
    urgency: str = "none"          # high | medium | low | none

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemHealthSummary:
    status: str = "green"          # green | yellow | red
    alert_count: int = 0
    active_mission_count: int = 0
    blocked_mission_count: int = 0


@dataclass
class KeyDate:
    date: str
    label: str
    mission_id: str | None = None


@dataclass
class CaptainBriefContext:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    date: str = ""
    source: str = "fresh"          # fresh | cached | stale
    health: HealthContextPackage | None = None
    top_priorities: list[Recommendation] = field(default_factory=list)
    blockers: list[BlockerContextPackage] = field(default_factory=list)
    decisions_awaiting_input: list[DecisionContextPackage] = field(default_factory=list)
    system_health: SystemHealthSummary = field(default_factory=SystemHealthSummary)
    key_dates_this_week: list[KeyDate] = field(default_factory=list)
    number_one_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class COPPriorityItem:
    rank: int
    mission_id: str
    title: str
    status: str
    next_action: str
    due_date: str | None = None
    blocker_count: int = 0


@dataclass
class OperationalStatus:
    overall: str = "green"         # green | yellow | red
    alert_count: int = 0
    active_missions: int = 0
    services_status: str = "all_green"  # all_green | warnings | critical


@dataclass
class BlockersSummary:
    count: int = 0
    top_blocker: str | None = None


@dataclass
class CaptainOperatingPictureContext:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    source: str = "fresh"
    health_snapshot: dict[str, Any] = field(default_factory=dict)
    top_3_priorities: list[COPPriorityItem] = field(default_factory=list)
    operational_status: OperationalStatus = field(default_factory=OperationalStatus)
    blockers_summary: BlockersSummary = field(default_factory=BlockersSummary)
    number_one_says: str | None = None
    quick_actions: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class RetrievalContextPackage:
    source_type: str               # captains_log | decision | mission | memory_file
    source_path: str
    date: str
    excerpt: str
    title: str | None = None
    relevance_score: float = 0.0
    related_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationPackage:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    recommendations: list[Recommendation] = field(default_factory=list)
    health_constraints_applied: bool = False
    total_active_missions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)
