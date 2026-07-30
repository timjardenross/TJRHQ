"""Investigation Framework — types and constants (EXEC-004 WP1).

Lifecycle:
  OPEN → COLLECTING_EVIDENCE → FINDINGS_READY → DECISION_PENDING → CLOSED

Possible outcomes (WP8):
  NO_ACTION | DECISION_MADE | MISSION_CREATED | IMPROVEMENT_CREATED |
  KNOWLEDGE_UPDATED | RISK_MONITORING | DEFERRED | FURTHER_INVESTIGATION

Storage contract (reuse decisions table — ADR-0020 zero new tables):
  Investigation record:  owner = "investigation:{inv_id}"
  Evidence items:        owner = "investigation_evidence:{inv_id}"
  Findings:              owner = "investigation_finding:{inv_id}"
  Decision packages:     owner = "investigation_decision:{inv_id}"

Prefixes are chosen so LIKE 'investigation:%' matches ONLY the main record
and LIKE 'investigation_evidence:%' matches ONLY evidence items, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class InvestigationType(str, Enum):
    STRATEGIC      = "strategic"
    OPERATIONAL    = "operational"
    TECHNICAL      = "technical"
    HEALTH         = "health"
    KNOWLEDGE      = "knowledge"
    RESILIENCE     = "resilience"
    COMMUNICATIONS = "communications"
    ARCHITECTURE   = "architecture"


class InvestigationStatus(str, Enum):
    OPEN                = "open"
    COLLECTING_EVIDENCE = "collecting_evidence"
    FINDINGS_READY      = "findings_ready"
    DECISION_PENDING    = "decision_pending"
    CLOSED              = "closed"


class InvestigationOutcome(str, Enum):
    NO_ACTION             = "no_action"
    DECISION_MADE         = "decision_made"
    MISSION_CREATED       = "mission_created"
    IMPROVEMENT_CREATED   = "improvement_created"
    KNOWLEDGE_UPDATED     = "knowledge_updated"
    RISK_MONITORING       = "risk_monitoring"
    DEFERRED              = "deferred"
    FURTHER_INVESTIGATION = "further_investigation"


class EvidenceSource(str, Enum):
    COMMAND_MEMORY   = "command_memory"
    MISSION_HISTORY  = "mission_history"
    DECISION_HISTORY = "decision_history"
    HEALTH_METRICS   = "health_metrics"
    ORI_INTELLIGENCE = "ori_intelligence"
    ENGINEERING_DATA = "engineering_data"
    KNOWLEDGE_REPO   = "knowledge_repo"
    CYCLE_CONTEXT    = "cycle_context"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    source: EvidenceSource
    summary: str
    data: str
    confidence: float = 0.5
    collected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EvidencePackage:
    investigation_id: str
    items: list[EvidenceItem] = field(default_factory=list)
    collected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def summary(self) -> str:
        if not self.items:
            return "No evidence collected."
        return "; ".join(f"[{i.source.value}] {i.summary}" for i in self.items[:4])

    @property
    def avg_confidence(self) -> float:
        if not self.items:
            return 0.0
        return round(sum(i.confidence for i in self.items) / len(self.items), 2)


@dataclass
class Finding:
    observation: str
    evidence_basis: str
    confidence: float  # 0.0-1.0
    is_fact: bool = True  # True = observed, False = inference

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.75:
            return "HIGH"
        if self.confidence >= 0.50:
            return "MEDIUM"
        return "LOW"


@dataclass
class Recommendation:
    action_type: str  # no_action | mission | improvement | decision | monitoring | knowledge_update | further_investigation
    description: str
    rationale: str
    confidence: float  # 0.0-1.0


@dataclass
class FindingsReport:
    investigation_id: str
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    summary: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def lead_recommendation(self) -> Recommendation | None:
        if not self.recommendations:
            return None
        return max(self.recommendations, key=lambda r: r.confidence)

    @property
    def high_confidence_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.confidence >= 0.75]


@dataclass
class DecisionOption:
    label: str
    description: str
    benefits: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class DecisionPackage:
    investigation_id: str
    problem_statement: str
    evidence_summary: str
    options: list[DecisionOption] = field(default_factory=list)
    recommended_option: str = ""
    confidence_assessment: str = ""
    required_approvals: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Investigation:
    investigation_id: str
    question: str
    investigation_type: InvestigationType
    source: str
    officer: str
    status: InvestigationStatus = InvestigationStatus.OPEN
    context: str = ""
    outcome: InvestigationOutcome | None = None
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "question": self.question,
            "type": self.investigation_type.value,
            "source": self.source,
            "officer": self.officer,
            "status": self.status.value,
            "outcome": self.outcome.value if self.outcome else None,
            "opened_at": self.opened_at.isoformat(),
        }


# ── Storage prefixes ──────────────────────────────────────────────────────────

INV_STATEMENT_PREFIX  = "[INVESTIGATION]"
INV_OWNER_PREFIX      = "investigation:"
EVIDENCE_OWNER_PREFIX = "investigation_evidence:"
FINDING_OWNER_PREFIX  = "investigation_finding:"
DECISION_OWNER_PREFIX = "investigation_decision:"


__all__ = [
    "InvestigationType",
    "InvestigationStatus",
    "InvestigationOutcome",
    "EvidenceSource",
    "EvidenceItem",
    "EvidencePackage",
    "Finding",
    "Recommendation",
    "FindingsReport",
    "DecisionOption",
    "DecisionPackage",
    "Investigation",
    "INV_STATEMENT_PREFIX",
    "INV_OWNER_PREFIX",
    "EVIDENCE_OWNER_PREFIX",
    "FINDING_OWNER_PREFIX",
    "DECISION_OWNER_PREFIX",
]
