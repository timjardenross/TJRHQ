from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
import json


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
    status: Optional[str] = None


@dataclass
class ContextPackage:
    # Identity
    entity_id: str
    entity_type: str
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    # Sections
    overview: Dict[str, Any] = field(default_factory=dict)
    triggering_decisions: List[EntityRef] = field(default_factory=list)
    dependencies: List[EntityRef] = field(default_factory=list)       # missions this one depends on
    dependent_missions: List[EntityRef] = field(default_factory=list) # missions that depend on this
    capabilities_built: List[EntityRef] = field(default_factory=list)
    governing_adrs: List[EntityRef] = field(default_factory=list)
    related_decisions: List[EntityRef] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)

    # Quality
    completeness_score: float = 0.0
    gaps: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# ============================================================================
# WP2: New context package dataclasses
# ============================================================================

@dataclass
class HealthStatusSnapshot:
    pain_level: Optional[str] = None
    mood: Optional[str] = None      # low | stable | positive
    energy: Optional[str] = None    # low | moderate | high
    stress: Optional[str] = None    # low | moderate | high
    sleep_quality: Optional[str] = None  # poor | fair | good


@dataclass
class HealthTrendSummary:
    pain_trend: Optional[str] = None     # improving | stable | worsening | unknown
    energy_trend: Optional[str] = None
    overall_direction: Optional[str] = None


@dataclass
class HealthContextPackage:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    source_file: str = ""
    status_summary: HealthStatusSnapshot = field(default_factory=HealthStatusSnapshot)
    trend_summary: HealthTrendSummary = field(default_factory=HealthTrendSummary)
    recovery_priorities: List[str] = field(default_factory=list)
    health_themes: List[str] = field(default_factory=list)
    medical_officer_note: Optional[str] = None
    safety_flags: List[str] = field(default_factory=list)
    workload_constraint: Optional[str] = None  # reduced | normal | unknown
    data_quality: str = "missing"  # complete | partial | missing

    def to_dict(self) -> Dict[str, Any]:
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
    blockers: List[str] = field(default_factory=list)
    health_constraint_note: Optional[str] = None
    due_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlockerContextPackage:
    mission_id: str
    mission_title: str
    priority: str
    escalation_level: str          # critical | high | medium | none
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    blocked_since: Optional[str] = None
    blocker_age_days: int = 0
    dependent_missions: List[str] = field(default_factory=list)
    recommended_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionContextPackage:
    decision_id: str
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    date: str = ""
    status: str = ""
    question: str = ""
    action: Optional[str] = None
    bottleneck: Optional[str] = None
    related_missions: List[Dict[str, Any]] = field(default_factory=list)
    awaiting_captain_input: bool = False
    urgency: str = "none"          # high | medium | low | none

    def to_dict(self) -> Dict[str, Any]:
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
    mission_id: Optional[str] = None


@dataclass
class CaptainBriefContext:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    date: str = ""
    source: str = "fresh"          # fresh | cached | stale
    health: Optional[HealthContextPackage] = None
    top_priorities: List[Recommendation] = field(default_factory=list)
    blockers: List[BlockerContextPackage] = field(default_factory=list)
    decisions_awaiting_input: List[DecisionContextPackage] = field(default_factory=list)
    system_health: SystemHealthSummary = field(default_factory=SystemHealthSummary)
    key_dates_this_week: List[KeyDate] = field(default_factory=list)
    number_one_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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
    due_date: Optional[str] = None
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
    top_blocker: Optional[str] = None


@dataclass
class CaptainOperatingPictureContext:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    source: str = "fresh"
    health_snapshot: Dict[str, Any] = field(default_factory=dict)
    top_3_priorities: List[COPPriorityItem] = field(default_factory=list)
    operational_status: OperationalStatus = field(default_factory=OperationalStatus)
    blockers_summary: BlockersSummary = field(default_factory=BlockersSummary)
    number_one_says: Optional[str] = None
    quick_actions: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class RetrievalContextPackage:
    source_type: str               # captains_log | decision | mission | memory_file
    source_path: str
    date: str
    excerpt: str
    title: Optional[str] = None
    relevance_score: float = 0.0
    related_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationPackage:
    assembled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    recommendations: List[Recommendation] = field(default_factory=list)
    health_constraints_applied: bool = False
    total_active_missions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)
