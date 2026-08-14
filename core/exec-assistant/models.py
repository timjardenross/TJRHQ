"""Database models for Exec-Assistant

Defines schemas for:
- Executive context and preferences
- Commitments and follow-ups
- Scheduling and optimization
- Alerts and recommendations
- Briefs and summaries
"""

from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
from typing import Optional, Dict, Any, List
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
    value: Dict[str, Any]
    source: ContextSource = ContextSource.MANUAL
    confidence: Optional[float] = None  # 0-1 for learned/inferred
    updated_at: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Commitment:
    """A commitment or follow-up to track"""
    id: UUID
    executive_id: UUID
    commitment_type: CommitmentType
    title: str
    description: Optional[str] = None
    source: str = "manual"  # telegram, email, calendar, manual, slack
    source_id: Optional[str] = None
    status: CommitmentStatus = CommitmentStatus.OPEN
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    reminded_at: Optional[datetime] = None
    assigned_to: Optional[str] = None  # 'self' or specialist name
    assigned_at: Optional[datetime] = None
    priority: Optional[int] = None  # 1=highest, 5=lowest
    context: Dict[str, Any] = field(default_factory=dict)
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SchedulingSuggestion:
    """Meeting optimization suggestion"""
    id: UUID
    executive_id: UUID
    calendar_event_id: str
    event_title: str
    current_time: Optional[datetime] = None
    proposed_time: Optional[datetime] = None
    reason_for_change: str = ""
    change_type: Optional[str] = None  # consolidation, conflict_resolution, focus_time_protection
    confidence: Optional[float] = None  # 0-1
    status: str = "pending_approval"  # pending_approval, approved, rejected, applied
    approval_reason: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
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
    description: Optional[str] = None
    recommendation: Optional[str] = None
    action_items: List[str] = field(default_factory=list)
    status: AlertStatus = AlertStatus.ACTIVE
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Brief:
    """Generated executive brief or summary"""
    id: UUID
    executive_id: UUID
    brief_type: BriefType
    title: str
    subject_matter: Optional[str] = None
    content: Dict[str, Any] = field(default_factory=dict)
    sections: List[Dict[str, str]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    delivery_channel: Optional[str] = None  # telegram, email, dashboard
    rating: Optional[int] = None  # 1-5
    feedback: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SyncStatus:
    """Track sync status for external integrations"""
    id: UUID
    executive_id: UUID
    integration_type: str  # google_calendar, gmail, telegram, slack, supabase
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None  # success, failed, partial
    last_sync_error: Optional[str] = None
    sync_cursor: Optional[str] = None  # For incremental syncs
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# ──────────────────────────────────────────────────────────────────────────
# Priority Matrix (Eisenhower Matrix)
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class PriorityMatrix:
    """Eisenhower Matrix: Urgent/Important quadrants"""
    critical: List[Commitment] = field(default_factory=list)   # Urgent + Important
    strategic: List[Commitment] = field(default_factory=list)  # Not Urgent + Important
    routine: List[Commitment] = field(default_factory=list)    # Urgent + Not Important
    delegate: List[Commitment] = field(default_factory=list)   # Not Urgent + Not Important


@dataclass
class PriorityAnalysis:
    """Analysis of task priorities"""
    matrix: PriorityMatrix
    total_tasks: int
    critical_count: int
    strategic_count: int
    routine_count: int
    delegate_count: int
    recommended_focus: List[str] = field(default_factory=list)
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
    alternative_specialists: List[tuple] = field(default_factory=list)  # [(name, confidence)]
    action_level: str = "handle"  # handle, propose, escalate
    urgency: str = "normal"  # low, normal, high
    complexity: str = "medium"  # simple, medium, complex
