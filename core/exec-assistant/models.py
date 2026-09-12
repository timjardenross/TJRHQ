"""Database models for Exec-Assistant

Defines schemas for:
- Executive context and preferences
- Commitments and follow-ups
- Scheduling and optimization
- Alerts and recommendations
- Briefs and summaries
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from uuid import UUID

# ──────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────

class ContextType(str, Enum):
    """Types of executive context"""
    PREFERENCE = "preference"      # Working style, meeting preferences
    PRIORITY = "priority"          # Strategic focus areas
    RELATIONSHIP = "relationship"  # Stakeholder context
    FRAMEWORK = "framework"        # Decision frameworks, SOPs
    PATTERN = "pattern"            # Recurring patterns detected


class ContextSource(str, Enum):
    """Source of context information"""
    MANUAL = "manual"          # Explicitly set by user
    LEARNED = "learned"        # Learned from feedback
    INFERRED = "inferred"      # Inferred from patterns


class CommitmentType(str, Enum):
    """Types of commitments to track"""
    MEETING = "meeting"
    DELIVERABLE = "deliverable"
    FOLLOW_UP = "follow_up"
    DECISION = "decision"
    REVIEW = "review"


class CommitmentStatus(str, Enum):
    """Status of a commitment"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class AlertType(str, Enum):
    """Types of alerts"""
    OVERLOAD = "overload"                # Schedule too full
    CONFLICT = "conflict"                # Scheduling conflicts
    RELATIONSHIP_GAP = "relationship_gap"  # Follow-ups needed
    PATTERN = "pattern"                  # Recurring pattern
    RISK = "risk"                        # Risk or issue
    OPPORTUNITY = "opportunity"          # Proactive opportunity


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(str, Enum):
    """Status of an alert"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class BriefType(str, Enum):
    """Types of briefs to generate"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MEETING_PREP = "meeting_prep"
    CUSTOM = "custom"


# ──────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class ExecutiveContext:
    """Executive preference, priority, relationship, or framework context"""
    id: UUID
    executive_id: UUID
    context_type: ContextType
    key: str
    value: dict[str, Any]
    source: ContextSource = ContextSource.MANUAL
    confidence: float | None = None  # 0-1 for learned/inferred
    updated_at: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Commitment:
    """A commitment or follow-up to track"""
    id: UUID
    executive_id: UUID
    commitment_type: CommitmentType
    title: str
    description: str | None = None
    source: str = "manual"  # telegram, email, calendar, manual, slack
    source_id: str | None = None
    status: CommitmentStatus = CommitmentStatus.OPEN
    due_date: date | None = None
    due_time: time | None = None
    reminded_at: datetime | None = None
    assigned_to: str | None = None  # 'self' or specialist name
    assigned_at: datetime | None = None
    priority: int | None = None  # 1=highest, 5=lowest
    context: dict[str, Any] = field(default_factory=dict)
    completed_at: datetime | None = None
    completion_notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SchedulingSuggestion:
    """Meeting optimization suggestion"""
    id: UUID
    executive_id: UUID
    calendar_event_id: str
    event_title: str
    current_time: datetime | None = None
    proposed_time: datetime | None = None
    reason_for_change: str = ""
    change_type: str | None = None  # consolidation, conflict_resolution, focus_time_protection
    confidence: float | None = None  # 0-1
    status: str = "pending_approval"  # pending_approval, approved, rejected, applied
    approval_reason: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    suggested_at: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Alert:
    """Proactive alert for executive attention"""
    id: UUID
    executive_id: UUID
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str | None = None
    recommendation: str | None = None
    action_items: list[str] = field(default_factory=list)
    status: AlertStatus = AlertStatus.ACTIVE
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Brief:
    """Generated executive brief or summary"""
    id: UUID
    executive_id: UUID
    brief_type: BriefType
    title: str
    subject_matter: str | None = None
    content: dict[str, Any] = field(default_factory=dict)
    sections: list[dict[str, str]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    sent_at: datetime | None = None
    delivery_channel: str | None = None  # telegram, email, dashboard
    rating: int | None = None  # 1-5
    feedback: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SyncStatus:
    """Track sync status for external integrations"""
    id: UUID
    executive_id: UUID
    integration_type: str  # google_calendar, gmail, telegram, slack, supabase
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None  # success, failed, partial
    last_sync_error: str | None = None
    sync_cursor: str | None = None  # For incremental syncs
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# ──────────────────────────────────────────────────────────────────────────
# Priority Matrix (Eisenhower Matrix)
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class PriorityMatrix:
    """Eisenhower Matrix: Urgent/Important quadrants"""
    critical: list[Commitment] = field(default_factory=list)   # Urgent + Important
    strategic: list[Commitment] = field(default_factory=list)  # Not Urgent + Important
    routine: list[Commitment] = field(default_factory=list)    # Urgent + Not Important
    delegate: list[Commitment] = field(default_factory=list)   # Not Urgent + Not Important


@dataclass
class PriorityAnalysis:
    """Analysis of task priorities"""
    matrix: PriorityMatrix
    total_tasks: int
    critical_count: int
    strategic_count: int
    routine_count: int
    delegate_count: int
    recommended_focus: list[str] = field(default_factory=list)
    workload_assessment: str = "balanced"  # balanced, overload, underutilized


# ──────────────────────────────────────────────────────────────────────────
# Delegation Decision
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class DelegationDecision:
    """Recommendation on who should handle a task"""
    specialist: str  # Name of specialist or 'self'
    confidence: float  # 0-1
    rationale: str
    alternative_specialists: list[tuple] = field(default_factory=list)  # [(name, confidence)]
    action_level: str = "handle"  # handle, propose, escalate
    urgency: str = "normal"  # low, normal, high
    complexity: str = "medium"  # simple, medium, complex
