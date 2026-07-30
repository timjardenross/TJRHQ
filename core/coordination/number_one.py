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

try:
    from core.coordination.number_one_memory_adapter import NumberOneMemoryAdapter, MemoryContext
except Exception:  # pragma: no cover - advisory-only fallback
    NumberOneMemoryAdapter = None
    MemoryContext = None


# ============================================================================
# Enums & Constants
# ============================================================================

class MissionStatus(Enum):
    """Mission lifecycle states.

    MSN-0053: superset = canonical D-008 lifecycle (ADR-0001/MSN-ENFORCE-001,
    now USS-TJR-MSN-0063 per D-076; legacy id is a permanent alias)
    7-state backbone + operational Blocked/Archived) PLUS the legacy
    pre-D-008 states (retained so existing logic/tests keep working).
    Parsing is via _to_status() and never raises.
    """
    # --- Pre-triage capture state (assigned by /mission-capture) ---
    IDEA = "Idea"
    # --- Canonical D-008 backbone (live missions table) ---
    DESIGNED = "Designed"
    IMPLEMENTED = "Implemented"
    TESTED = "Tested"
    AWAITING_NUMBER_ONE_REVIEW = "Awaiting Number One Review"
    VALIDATED = "Validated"
    AWAITING_XO_APPROVAL = "Awaiting XO Approval"
    CLOSED = "Closed"
    # --- D-008 operational states (Blocked/Archived; D-009 CHECK deferred) ---
    BLOCKED_OPS = "Blocked"
    ARCHIVED = "Archived"
    # --- Legacy pre-D-008 states (retained for back-compat) ---
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
        # MSN-0053: tolerate D-008 + legacy field names; never raise on status/priority.
        return Mission(
            # live Command Memory uses `id`; legacy uses `mission_id`
            mission_id=mission_dict.get("mission_id") or mission_dict.get("id") or "UNKNOWN",
            title=mission_dict.get("title", ""),
            status=_to_status(mission_dict.get("status")),
            priority=_to_priority(mission_dict.get("priority")),
            domain=mission_dict.get("domain") or "",
            assigned_role=mission_dict.get("assigned_role"),
            assigned_specialists=mission_dict.get("assigned_specialists") or [],
            dependencies=mission_dict.get("dependencies") or [],
            blockers=mission_dict.get("blockers") or [],
            created_at=_parse_iso_datetime(mission_dict.get("created_at")),
            # live uses `updated_at`; legacy uses `last_updated`
            last_updated=_parse_iso_datetime(
                mission_dict.get("last_updated") or mission_dict.get("updated_at")
            ),
            next_action=mission_dict.get("next_action"),
            metadata=mission_dict.get("metadata") or {},
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
    # Engineering-handoff lifecycle projection (read-only; None for missions).
    # M-20260614-ENGINEERING-HANDOFF-LIFECYCLE: surfaces the handoff's
    # Pending Triage / Assigned / In Progress / Awaiting Review stage.
    engineering_status: Optional[str] = None


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
        # D-008 active states (most-needs-attention first), then legacy, then terminal
        MissionStatus.AWAITING_XO_APPROVAL,
        MissionStatus.AWAITING_NUMBER_ONE_REVIEW,
        MissionStatus.BLOCKED_OPS,
        MissionStatus.IMPLEMENTED,
        MissionStatus.TESTED,
        MissionStatus.DESIGNED,
        MissionStatus.VALIDATED,
        MissionStatus.ACTIVE,
        MissionStatus.TRIAGED,
        MissionStatus.IN_REVIEW,
        MissionStatus.PROPOSED,
        MissionStatus.BLOCKED,
        MissionStatus.DEFERRED,
        MissionStatus.CLOSED,
        MissionStatus.ARCHIVED,
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
        self.memory_adapter = NumberOneMemoryAdapter() if NumberOneMemoryAdapter else None

    def request_advisory_support(self, mission: dict[str, Any]) -> dict[str, Any]:
        """MSN-0093 WP2 — consume advisory intelligence for one mission.

        Number One remains the assignment authority; this only *requests* risk,
        dependency, historical-comparison and confidence support from the shared
        advisory runtime. Lazy-imported so Number One has no hard dependency on
        the advisory layer (returns a clear note if it is unavailable).
        """
        try:
            from number_one_advisory import advisory_support  # noqa: PLC0415
            return advisory_support(mission)
        except Exception as exc:  # noqa: BLE001
            return {
                "mission_id": mission.get("mission_id") or mission.get("id", ""),
                "error": f"advisory runtime unavailable: {exc}",
                "authority_note": "Number One decides assignment. Advisory only.",
            }

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

        # Filter out completed/cancelled and dormant (Idea) missions
        active_missions = [
            m for m in mission_objs
            if m.status not in TERMINAL_STATUSES and m.status not in DORMANT_STATUSES
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
                engineering_status=mission.metadata.get("engineering_status"),
            )
            queue_items.append(item)

        # Sort queue
        return self._sort_work_queue(queue_items)

    def get_health_adjusted_queue(
        self,
        missions: list[dict[str, Any]],
        capacity_status: str,
        routing_results: dict[str, "RoutingDecision"] | None = None,
    ) -> dict[str, Any]:
        """
        Return the work queue with an advisory health-capacity overlay.

        The base priority ordering from get_work_queue() is never overridden —
        P0 missions always surface first.  The overlay adds a capacity_note to
        each item and produces a recommended_focus list appropriate to the
        Captain's current health state.

        capacity_status:
          "Green"   — full capacity; normal queue ordering applies
          "Amber"   — reduced capacity; adds advisory note per item
          "Red"     — critical-only; P0 missions recommended; all others deferred

        Returns a dict (not a list) so the health context travels with the queue:
          {
            "capacity_status": str,
            "queue": list[dict],          # WorkQueueItems serialised + capacity_note
            "recommended_focus": list[str],
            "advisory": str,              # plain-English capacity statement
          }

        Mission records are NEVER altered. This is a read-only advisory overlay.
        """
        base_queue = self.get_work_queue(missions, routing_results)

        annotated = []
        for item in base_queue:
            d = {
                "mission_id": item.mission_id,
                "priority": item.priority.value if hasattr(item.priority, "value") else item.priority,
                "status": item.status.value if hasattr(item.status, "value") else str(item.status),
                "title": item.title,
                "assigned_specialist": item.assigned_specialist,
                "next_action": item.next_action,
                "blockers": item.blockers,
                "capacity_note": "",
            }
            pri = d["priority"]
            if capacity_status == "Red":
                if pri == "P0":
                    d["capacity_note"] = "CRITICAL — proceed regardless of capacity"
                else:
                    d["capacity_note"] = "DEFERRED — Red capacity: P0 only today"
            elif capacity_status == "Amber":
                if pri in ("P0", "P1"):
                    d["capacity_note"] = "Proceed — priority justifies reduced capacity"
                else:
                    d["capacity_note"] = "Advisory: consider deferring on reduced capacity days"
            else:
                d["capacity_note"] = ""  # Green: no overlay needed
            annotated.append(d)

        # Advisory statement
        if capacity_status == "Red":
            advisory = (
                "Captain is at RED capacity today. "
                "Number One recommends P0 missions only. "
                "All other work is deferred until capacity recovers."
            )
            recommended_focus = [
                m["title"] for m in annotated if m["priority"] == "P0" and "BLOCKED" not in m["status"].upper()
            ][:3] or ["No active P0 missions — prioritise rest and recovery"]
        elif capacity_status == "Amber":
            advisory = (
                "Captain is at AMBER capacity today. "
                "P0 and P1 missions are recommended. "
                "P2/P3 work should be deferred unless low-cognitive-load."
            )
            recommended_focus = [
                m["title"] for m in annotated
                if m["priority"] in ("P0", "P1") and "BLOCKED" not in m["status"].upper()
            ][:3]
        else:
            advisory = "Captain is at GREEN capacity. Normal prioritisation applies."
            recommended_focus = [
                m["title"] for m in annotated
                if "BLOCKED" not in m["status"].upper()
            ][:3]

        return {
            "capacity_status": capacity_status,
            "queue": annotated,
            "recommended_focus": recommended_focus,
            "advisory": advisory,
        }

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
            if mission.status in TERMINAL_STATUSES or mission.status in DORMANT_STATUSES:
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
            if mission.status in TERMINAL_STATUSES or mission.status in DORMANT_STATUSES:
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
        memory_context = self._get_memory_context(missions, routing_results)

        # Calculate metrics (exclude cancelled/completed/dormant)
        active_missions = [m for m in mission_objs if m.status not in TERMINAL_STATUSES and m.status not in DORMANT_STATUSES]
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
            work_queue, follow_ups, escalations, blocked_missions, memory_context
        )

        brief = CoordinationBrief(
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
        self._persist_memory_context(brief, missions, routing_results)
        return brief

    def build_memory_enhanced_brief(
        self,
        missions: list[dict[str, Any]],
        routing_results: dict[str, RoutingDecision] | None = None,
    ) -> CoordinationBrief:
        """Compatibility wrapper for memory-aware brief generation."""
        return self.get_daily_brief(missions, routing_results)

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
            MissionStatus.IDEA: "Triage: promote to Designed or close",
            MissionStatus.DESIGNED: "Begin implementation",
            MissionStatus.IMPLEMENTED: "Run tests",
            MissionStatus.TESTED: "Submit for Number One review",
            MissionStatus.AWAITING_NUMBER_ONE_REVIEW: "Number One review pending",
            MissionStatus.VALIDATED: "Submit for XO approval",
            MissionStatus.AWAITING_XO_APPROVAL: "XO approval pending",
            MissionStatus.CLOSED: "Closed",
            MissionStatus.BLOCKED_OPS: "Resolve blocker",
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
        blocked: list[WorkQueueItem],
        memory_context: Optional[Any] = None,
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

        if memory_context and getattr(memory_context, "found", False):
            for item in getattr(memory_context, "recommendations", [])[:3]:
                recommendations.append(f"Memory context: {item}")
            summary = getattr(memory_context, "summary", "")
            if summary:
                recommendations.append(f"Memory context summary: {summary[:160]}")

        return recommendations

    def _get_memory_context(
        self,
        missions: list[dict[str, Any]],
        routing_results: dict[str, RoutingDecision] | None = None,
    ) -> Any:
        if not self.memory_adapter:
            return None
        try:
            return self.memory_adapter.retrieve_context(missions, routing_results or {})
        except Exception as exc:
            log.warning("[number-one] memory retrieval failed (non-blocking): %s", exc)
            return None

    def _persist_memory_context(
        self,
        brief: CoordinationBrief,
        missions: list[dict[str, Any]],
        routing_results: dict[str, RoutingDecision] | None = None,
    ) -> None:
        if not self.memory_adapter:
            return
        try:
            payload = {
                "brief_id": f"NUM1-BRIEF-{brief.timestamp.strftime('%Y%m%d%H%M%S')}",
                "mission_id": missions[0].get("mission_id") if missions else "",
                "summary": " | ".join(brief.recommended_actions[:5]),
                "recommendations": brief.recommended_actions,
                "confidence": 0.0,
            }
            self.memory_adapter.persist_brief(payload)
        except Exception as exc:
            log.warning("[number-one] memory persistence failed (non-blocking): %s", exc)


# ============================================================================
# Utilities
# ============================================================================

# MSN-0053: terminal states (excluded from the active work queue / counts).
TERMINAL_STATUSES = {
    MissionStatus.CLOSED, MissionStatus.ARCHIVED,        # D-008 terminal
    MissionStatus.COMPLETED, MissionStatus.CANCELLED,    # legacy terminal
}

# Dormant states: captured but not yet triaged — excluded from active work queue
# without permanently closing the record. Promoted to Designed when actioned.
DORMANT_STATUSES = {
    MissionStatus.IDEA,
}


def _to_status(value: Optional[str]) -> MissionStatus:
    """Parse a status string to MissionStatus. Never raises (MSN-0053).

    Handles D-008 values, legacy values, and case differences (e.g. live
    'Blocked' -> BLOCKED_OPS). Unknown -> DESIGNED (canonical entry state) + warn.
    """
    if value is None:
        return MissionStatus.DESIGNED
    v = str(value).strip()
    for s in MissionStatus:          # exact value match (D-008 + legacy)
        if s.value == v:
            return s
    for s in MissionStatus:          # case-insensitive (e.g. 'blocked')
        if s.value.lower() == v.lower():
            return s
    log.warning("[number-one] unknown mission status %r; defaulting to Designed", value)
    return MissionStatus.DESIGNED


def _to_priority(value: Optional[str]) -> Priority:
    """Parse a priority to Priority. Never raises (MSN-0053).

    Tolerates None (-> P3), 'P1', and 'P1 High' style. Unknown -> P3.
    """
    if not value:
        return Priority.P3
    token = str(value).strip().split()[0].upper()
    for p in Priority:
        if p.value == token:
            return p
    return Priority.P3


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
