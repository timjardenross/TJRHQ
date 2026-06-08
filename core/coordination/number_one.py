#!/usr/bin/env python3
"""
Number One — Operational Coordination Layer for STARFLEET COMMAND

Transforms mission data, routing intelligence, priorities, blockers, and
specialist recommendations into actionable work management.

Core Responsibilities:
  - Work queue generation (prioritized mission lists)
  - Follow-up detection (stale, blocked, missing assignments)
  - Blocker management (tracking and analysis)
  - Specialist coordination (routing-based assignments)
  - Daily coordination brief (executive summary)
  - XO escalation engine (surface critical issues)

Authority Model:
  - Number One RECOMMENDS
  - Executive Officer (XO) DECIDES
  - All execution requires XO approval or direction

Design:
  - Deterministic (same inputs → same outputs)
  - Explainable (every recommendation includes rationale)
  - Rule-based (not AI, not autonomous)
  - Non-autonomous (no independent execution)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime, timedelta
import json


# ============================================================================
# Enums & Constants
# ============================================================================

class MissionStatus(Enum):
    """Mission lifecycle states."""
    PROPOSED = "PROPOSED"
    TRIAGED = "TRIAGED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"
    DEFERRED = "DEFERRED"
    CANCELLED = "CANCELLED"


class Priority(Enum):
    """Mission priority levels (P0 highest, P3 lowest)."""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ConfidenceBand(Enum):
    """Routing confidence levels."""
    HIGH = "high"  # >= 0.80
    MEDIUM = "medium"  # 0.55-0.79
    LOW = "low"  # < 0.55


class EscalationLevel(Enum):
    """Escalation severity levels."""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # Review today
    MEDIUM = "medium"  # Review this week


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Mission:
    """Mission data from Mission Registry."""
    mission_id: str
    title: str
    status: MissionStatus
    priority: Priority
    domain: str
    assigned_role: Optional[str] = None
    assigned_specialists: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # mission_ids
    blockers: list[str] = field(default_factory=list)  # descriptions
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    next_action: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_registry(mission_dict: dict) -> Mission:
        """Convert Mission Registry dict to Mission object."""
        return Mission(
            mission_id=mission_dict.get("mission_id", "UNKNOWN"),
            title=mission_dict.get("title", ""),
            status=MissionStatus(mission_dict.get("status", "PROPOSED")),
            priority=Priority(mission_dict.get("priority", "P3")),
            domain=mission_dict.get("domain", ""),
            assigned_role=mission_dict.get("assigned_role"),
            assigned_specialists=mission_dict.get("assigned_specialists", []),
            dependencies=mission_dict.get("dependencies", []),
            blockers=mission_dict.get("blockers", []),
            created_at=_parse_iso_datetime(mission_dict.get("created_at")),
            last_updated=_parse_iso_datetime(mission_dict.get("last_updated")),
            next_action=mission_dict.get("next_action"),
            metadata=mission_dict.get("metadata", {})
        )


@dataclass
class RoutingDecision:
    """Semantic routing decision from P5."""
    primary_specialist: str
    secondary_specialists: list[str] = field(default_factory=list)
    intent: str = "unknown"
    confidence: float = 0.5
    confidence_band: ConfidenceBand = ConfidenceBand.LOW
    rationale: str = ""
    escalate_to_xo: bool = False


@dataclass
class WorkQueueItem:
    """Item in the work queue."""
    mission_id: str
    priority: Priority
    status: MissionStatus
    title: str
    assigned_specialist: Optional[str]
    next_action: Optional[str]
    blockers: list[str]
    dependencies: list[str]
    confidence: Optional[float] = None
    confidence_band: Optional[ConfidenceBand] = None
    rationale: Optional[str] = None


@dataclass
class Escalation:
    """Issue requiring XO review."""
    escalation_type: str
    mission_id: str
    level: EscalationLevel
    reason: str
    data: dict[str, Any]
    recommendation: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CoordinationBrief:
    """Daily coordination brief for Captain/XO."""
    timestamp: datetime
    total_missions: int
    active_count: int
    blocked_count: int
    proposed_count: int
    system_health: str  # "green", "yellow", "red"
    top_priorities: list[WorkQueueItem]
    blocked_missions: list[WorkQueueItem]
    follow_ups: list[dict[str, Any]]
    escalations: list[Escalation]
    specialist_workload: dict[str, int]
    recommended_actions: list[str]


# ============================================================================
# Configuration
# ============================================================================

class CoordinationConfig:
    """Configuration for coordination rules."""

    # Staleness thresholds
    STALE_MISSION_DAYS = 5
    STALE_P0_DAYS = 2

    # Blocker thresholds
    BLOCKED_P1_DAYS = 3
    BLOCKED_P0_DAYS = 1

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.80
    MEDIUM_CONFIDENCE = 0.55
    LOW_CONFIDENCE = 0.0

    # Priority order for queuing
    PRIORITY_ORDER = [Priority.P0, Priority.P1, Priority.P2, Priority.P3]

    # Status order within priority
    STATUS_ORDER = [
        MissionStatus.ACTIVE,
        MissionStatus.TRIAGED,
        MissionStatus.IN_REVIEW,
        MissionStatus.PROPOSED,
        MissionStatus.BLOCKED,
        MissionStatus.DEFERRED,
        MissionStatus.CANCELLED,
        MissionStatus.COMPLETED,
    ]


# ============================================================================
# Number One Coordination Engine
# ============================================================================

class NumberOne:
    """
    Number One Coordination Engine.

    Transforms mission data and routing intelligence into actionable work
    management through deterministic rules-based coordination.
    """

    def __init__(self, config: Optional[CoordinationConfig] = None):
        """Initialize Number One."""
        self.config = config or CoordinationConfig()
        self.current_time = datetime.utcnow()

    def get_work_queue(
        self,
        missions: list[dict[str, Any]],
        routing_results: dict[str, RoutingDecision] | None = None
    ) -> list[WorkQueueItem]:
        """
        Generate prioritized work queue.

        Args:
            missions: List of mission dicts from Mission Registry
            routing_results: Optional dict mapping mission_id → RoutingDecision

        Returns:
            Sorted list of WorkQueueItem objects
        """
        # Convert missions to Mission objects
        mission_objs = [Mission.from_registry(m) for m in missions]
        routing_results = routing_results or {}

        # Filter out completed/cancelled missions
        active_missions = [
            m for m in mission_objs
            if m.status not in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]
        ]

        # Build queue items
        queue_items = []
        for mission in active_missions:
            routing = routing_results.get(mission.mission_id)
            specialist = self._determine_specialist(mission, routing)

            item = WorkQueueItem(
                mission_id=mission.mission_id,
                priority=mission.priority,
                status=mission.status,
                title=mission.title,
                assigned_specialist=specialist,
                next_action=mission.next_action or self._recommend_next_action(mission),
                blockers=mission.blockers,
                dependencies=mission.dependencies,
                confidence=routing.confidence if routing else None,
                confidence_band=routing.confidence_band if routing else None,
                rationale=routing.rationale if routing else None,
            )
            queue_items.append(item)

        # Sort queue
        return self._sort_work_queue(queue_items)

    def get_follow_ups(self, missions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Detect missions needing follow-up.

        Args:
            missions: List of mission dicts from Mission Registry

        Returns:
            List of follow-up items with reasons and recommendations
        """
        mission_objs = [Mission.from_registry(m) for m in missions]
        follow_ups = []

        for mission in mission_objs:
            if mission.status in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]:
                continue

            # Rule: Stale mission
            if self._is_stale_mission(mission):
                days_old = (self.current_time - mission.last_updated).days
                follow_ups.append({
                    "mission_id": mission.mission_id,
                    "type": "STALE_MISSION",
                    "reason": f"No update for {days_old} days",
                    "data": {"days_old": days_old, "last_updated": mission.last_updated.isoformat()},
                    "recommendation": "Contact assigned specialist for status update",
                })

            # Rule: Long-blocked mission
            if self._is_long_blocked(mission):
                blocker_age = self._calculate_blocker_age(mission)
                follow_ups.append({
                    "mission_id": mission.mission_id,
                    "type": "LONG_BLOCKED",
                    "reason": f"Blocker age: {blocker_age} days",
                    "data": {"blocker_age": blocker_age, "blockers": mission.blockers},
                    "recommendation": "Resolve blocker or reassign work",
                })

            # Rule: Missing specialist
            if not mission.assigned_role and mission.status != MissionStatus.PROPOSED:
                follow_ups.append({
                    "mission_id": mission.mission_id,
                    "type": "MISSING_SPECIALIST",
                    "reason": "No specialist assigned",
                    "data": {"status": mission.status.value},
                    "recommendation": "Assign specialist or escalate to XO",
                })

            # Rule: Missing next action
            if not mission.next_action and mission.status != MissionStatus.COMPLETED:
                follow_ups.append({
                    "mission_id": mission.mission_id,
                    "type": "MISSING_NEXT_ACTION",
                    "reason": "No next action defined",
                    "data": {"status": mission.status.value},
                    "recommendation": "Define next action or close mission",
                })

        return follow_ups

    def get_blockers(self, missions: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Generate blocker management report.

        Args:
            missions: List of mission dicts from Mission Registry

        Returns:
            Dict with blocker analysis by severity
        """
        mission_objs = [Mission.from_registry(m) for m in missions]

        critical_blockers = []
        high_blockers = []
        normal_blockers = []

        for mission in mission_objs:
            if mission.status != MissionStatus.BLOCKED or not mission.blockers:
                continue

            blocker_age = self._calculate_blocker_age(mission)
            blocker_info = {
                "mission_id": mission.mission_id,
                "blockers": mission.blockers,
                "age_days": blocker_age,
                "priority": mission.priority.value,
            }

            if mission.priority == Priority.P0:
                critical_blockers.append(blocker_info)
            elif mission.priority == Priority.P1:
                high_blockers.append(blocker_info)
            else:
                normal_blockers.append(blocker_info)

        return {
            "timestamp": self.current_time.isoformat(),
            "total_blockers": len(critical_blockers) + len(high_blockers) + len(normal_blockers),
            "critical": critical_blockers,
            "high": high_blockers,
            "normal": normal_blockers,
        }

    def get_xo_escalations(
        self,
        missions: list[dict[str, Any]],
        routing_results: dict[str, RoutingDecision] | None = None
    ) -> list[Escalation]:
        """
        Generate XO escalations for issues requiring executive review.

        Args:
            missions: List of mission dicts from Mission Registry
            routing_results: Optional dict mapping mission_id → RoutingDecision

        Returns:
            List of Escalation objects sorted by level
        """
        mission_objs = [Mission.from_registry(m) for m in missions]
        routing_results = routing_results or {}
        escalations = []

        for mission in mission_objs:
            if mission.status in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]:
                continue

            routing = routing_results.get(mission.mission_id)

            # Escalation: Blocked P0 mission
            if mission.priority == Priority.P0 and mission.status == MissionStatus.BLOCKED:
                escalations.append(Escalation(
                    escalation_type="BLOCKED_P0",
                    mission_id=mission.mission_id,
                    level=EscalationLevel.CRITICAL,
                    reason="P0 mission blocked - immediate intervention required",
                    data={"blockers": mission.blockers},
                    recommendation="Unblock immediately or escalate",
                ))

            # Escalation: Extended block on P1
            elif mission.priority == Priority.P1 and self._is_long_blocked(mission, days=3):
                blocker_age = self._calculate_blocker_age(mission)
                escalations.append(Escalation(
                    escalation_type="EXTENDED_BLOCK_P1",
                    mission_id=mission.mission_id,
                    level=EscalationLevel.HIGH,
                    reason=f"P1 mission blocked for {blocker_age} days",
                    data={"blocker_age": blocker_age, "blockers": mission.blockers},
                    recommendation="Escalate blocker or reassign work",
                ))

            # Escalation: Low confidence routing
            if routing and routing.confidence < self.config.MEDIUM_CONFIDENCE:
                escalations.append(Escalation(
                    escalation_type="LOW_CONFIDENCE_ROUTING",
                    mission_id=mission.mission_id,
                    level=EscalationLevel.MEDIUM,
                    reason=f"Low routing confidence ({routing.confidence:.2f})",
                    data={"confidence": routing.confidence, "intent": routing.intent},
                    recommendation="Manual specialist assignment required",
                ))

            # Escalation: Missing specialist on active mission
            if (not mission.assigned_role and
                mission.status in [MissionStatus.ACTIVE, MissionStatus.IN_REVIEW]):
                escalations.append(Escalation(
                    escalation_type="MISSING_SPECIALIST",
                    mission_id=mission.mission_id,
                    level=EscalationLevel.MEDIUM,
                    reason="Active mission without specialist assignment",
                    data={"status": mission.status.value},
                    recommendation="Assign specialist immediately",
                ))

            # Escalation: Stale P0 mission
            if mission.priority == Priority.P0 and self._is_stale_mission(mission, days=2):
                days_old = (self.current_time - mission.last_updated).days
                escalations.append(Escalation(
                    escalation_type="STALE_P0",
                    mission_id=mission.mission_id,
                    level=EscalationLevel.HIGH,
                    reason=f"P0 mission not updated for {days_old} days",
                    data={"days_old": days_old},
                    recommendation="Verify status immediately",
                ))

        # Sort by level (CRITICAL → HIGH → MEDIUM)
        escalations.sort(
            key=lambda e: {
                EscalationLevel.CRITICAL: 0,
                EscalationLevel.HIGH: 1,
                EscalationLevel.MEDIUM: 2,
            }[e.level]
        )

        return escalations

    def get_daily_brief(
        self,
        missions: list[dict[str, Any]],
        routing_results: dict[str, RoutingDecision] | None = None
    ) -> CoordinationBrief:
        """
        Generate daily coordination brief for Captain/XO.

        Args:
            missions: List of mission dicts from Mission Registry
            routing_results: Optional dict mapping mission_id → RoutingDecision

        Returns:
            CoordinationBrief object with all sections
        """
        mission_objs = [Mission.from_registry(m) for m in missions]
        routing_results = routing_results or {}

        # Get components
        work_queue = self.get_work_queue(missions, routing_results)
        follow_ups = self.get_follow_ups(missions)
        escalations = self.get_xo_escalations(missions, routing_results)

        # Calculate metrics (exclude cancelled/completed)
        active_missions = [m for m in mission_objs if m.status not in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]]
        total = len(active_missions)
        active = len([m for m in active_missions if m.status == MissionStatus.ACTIVE])
        blocked = len([m for m in active_missions if m.status == MissionStatus.BLOCKED])
        proposed = len([m for m in active_missions if m.status == MissionStatus.PROPOSED])

        # System health
        system_health = "red" if escalations and any(
            e.level == EscalationLevel.CRITICAL for e in escalations
        ) else ("yellow" if escalations else "green")

        # Top priorities (first 3 from work queue)
        top_priorities = work_queue[:3]

        # Blocked missions
        blocked_missions = [item for item in work_queue if item.status == MissionStatus.BLOCKED]

        # Specialist workload
        specialist_workload = self._calculate_specialist_workload(mission_objs)

        # Recommended actions
        recommended_actions = self._generate_recommendations(
            work_queue, follow_ups, escalations, blocked_missions
        )

        return CoordinationBrief(
            timestamp=self.current_time,
            total_missions=total,
            active_count=active,
            blocked_count=blocked,
            proposed_count=proposed,
            system_health=system_health,
            top_priorities=top_priorities,
            blocked_missions=blocked_missions,
            follow_ups=follow_ups,
            escalations=escalations,
            specialist_workload=specialist_workload,
            recommended_actions=recommended_actions,
        )

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _determine_specialist(
        self,
        mission: Mission,
        routing: Optional[RoutingDecision]
    ) -> Optional[str]:
        """Determine specialist for queue display."""
        # If already assigned, show that
        if mission.assigned_role:
            return mission.assigned_role

        # If routing available, show recommendation
        if routing:
            if routing.confidence >= self.config.HIGH_CONFIDENCE:
                return f"{routing.primary_specialist}"
            else:
                return "XO Review Required"

        return None

    def _recommend_next_action(self, mission: Mission) -> str:
        """Recommend next action based on mission status."""
        next_actions = {
            MissionStatus.PROPOSED: "Begin triage",
            MissionStatus.TRIAGED: "Activate and assign",
            MissionStatus.ACTIVE: "Continue implementation",
            MissionStatus.BLOCKED: "Resolve blocker",
            MissionStatus.IN_REVIEW: "Complete review",
            MissionStatus.COMPLETED: "Archived",
        }
        return next_actions.get(mission.status, "Review status")

    def _sort_work_queue(self, items: list[WorkQueueItem]) -> list[WorkQueueItem]:
        """Sort work queue by priority, then status."""
        priority_order = {p: i for i, p in enumerate(self.config.PRIORITY_ORDER)}
        status_order = {s: i for i, s in enumerate(self.config.STATUS_ORDER)}

        return sorted(
            items,
            key=lambda x: (
                priority_order.get(x.priority, 999),
                status_order.get(x.status, 999),
            )
        )

    def _is_stale_mission(self, mission: Mission, days: Optional[int] = None) -> bool:
        """Check if mission is stale (no updates)."""
        threshold_days = days or self.config.STALE_MISSION_DAYS
        if mission.priority == Priority.P0:
            threshold_days = self.config.STALE_P0_DAYS

        age = (self.current_time - mission.last_updated).days
        return age >= threshold_days

    def _is_long_blocked(self, mission: Mission, days: Optional[int] = None) -> bool:
        """Check if mission has been blocked too long."""
        if mission.status != MissionStatus.BLOCKED:
            return False

        threshold_days = days or (
            self.config.BLOCKED_P0_DAYS if mission.priority == Priority.P0
            else self.config.BLOCKED_P1_DAYS
        )

        blocker_age = self._calculate_blocker_age(mission)
        return blocker_age >= threshold_days

    def _calculate_blocker_age(self, mission: Mission) -> int:
        """Calculate how long mission has been blocked (days)."""
        # For simplicity, use mission's blocked time
        # In production, would track blocker creation time separately
        return (self.current_time - mission.last_updated).days

    def _calculate_specialist_workload(self, missions: list[Mission]) -> dict[str, int]:
        """Count active missions per specialist."""
        workload = {}
        for mission in missions:
            if mission.status in [MissionStatus.ACTIVE, MissionStatus.TRIAGED]:
                for specialist in mission.assigned_specialists:
                    workload[specialist] = workload.get(specialist, 0) + 1
        return dict(sorted(workload.items(), key=lambda x: x[1], reverse=True))

    def _generate_recommendations(
        self,
        queue: list[WorkQueueItem],
        follow_ups: list[dict],
        escalations: list[Escalation],
        blocked: list[WorkQueueItem]
    ) -> list[str]:
        """Generate recommended actions for brief."""
        recommendations = []

        # Recommend unblocking if there are blocked P1/P0 missions
        p0_p1_blocked = [b for b in blocked if b.priority in [Priority.P0, Priority.P1]]
        if p0_p1_blocked:
            for b in p0_p1_blocked[:2]:
                recommendations.append(f"Unblock {b.mission_id} (priority: {b.priority.value})")

        # Recommend activating if TRIAGED missions available
        triaged = [q for q in queue if q.status == MissionStatus.TRIAGED]
        if triaged:
            recommendations.append(f"Activate {triaged[0].mission_id}")

        # Recommend following up on stale missions
        stale_follow_ups = [f for f in follow_ups if f["type"] == "STALE_MISSION"]
        if stale_follow_ups:
            recommendations.append(f"Contact specialist for {stale_follow_ups[0]['mission_id']} status")

        # Recommend XO action on escalations
        high_escalations = [e for e in escalations if e.level == EscalationLevel.HIGH]
        if high_escalations:
            recommendations.append(f"XO: {high_escalations[0].recommendation}")

        return recommendations


# ============================================================================
# Utilities
# ============================================================================

def _parse_iso_datetime(datetime_str: Optional[str]) -> datetime:
    """Parse ISO 8601 datetime string to naive UTC datetime."""
    if not datetime_str:
        return datetime.utcnow()
    try:
        # Parse with timezone info, then convert to naive UTC
        dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            # Convert to naive UTC
            return dt.replace(tzinfo=None)
        return dt
    except (ValueError, AttributeError):
        return datetime.utcnow()


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "NumberOne",
    "MissionStatus",
    "Priority",
    "ConfidenceBand",
    "EscalationLevel",
    "Mission",
    "RoutingDecision",
    "WorkQueueItem",
    "Escalation",
    "CoordinationBrief",
    "CoordinationConfig",
]
