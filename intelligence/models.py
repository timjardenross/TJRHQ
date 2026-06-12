"""
Data models for the OR Intelligence Agent.
All fields required for source attribution and audit trail.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class SourceRecord:
    source_id: str
    source_name: str
    category: str
    priority_rank: int
    url: str
    source_type: str          # rss | api | scrape | manual
    jurisdiction: str         # AU | APAC | GLOBAL
    confidence_weight: float
    active: bool
    rss_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class SourceHealth:
    source_id: str
    source_name: str
    checked_at: datetime
    status: str               # ok | stale | failed | degraded | skipped
    items_retrieved: int = 0
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    http_status: Optional[int] = None


@dataclass
class IntelligenceItem:
    """Raw collected item before classification."""
    source_id: str
    source_name: str
    source_priority: int
    source_confidence_weight: float
    raw_title: str
    collected_at: datetime
    raw_summary: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[datetime] = None


@dataclass
class ClassifiedEvent:
    """Item after classification and dedup check."""
    event_id: str
    source_id: str
    source_name: str
    source_priority: int
    source_confidence_weight: float
    raw_title: str
    raw_summary: Optional[str]
    canonical_url: Optional[str]
    published_at: Optional[datetime]
    collected_at: datetime
    dedup_hash: str

    # Classification outputs
    event_type: str
    geography: str
    sector: str
    operational_relevance: float      # 0.0–1.0
    customer_impact: str              # low | medium | high
    banking_relevance: str            # low | medium | high
    cps230_relevance: bool
    dependency_risk: bool
    confidence: float                 # 0.0–1.0
    suppressed: bool = False
    suppression_reason: Optional[str] = None


@dataclass
class RankedEvent(ClassifiedEvent):
    """Event with final composite rank score."""
    rank_score: float = 0.0


@dataclass
class BriefEvent:
    """Snapshot of an event as it appears in a published brief."""
    event_id: str
    title: str
    location: str
    event_type: str
    risk_rating: str              # GREEN | AMBER | RED
    summary: str
    operational_impact: str
    so_what: str
    status: str
    source_name: str
    canonical_url: Optional[str]
    rank_score: float


@dataclass
class ResilienceBrief:
    """Final assembled brief. Narrative fields may be None if all LLM providers failed."""
    brief_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime

    # Collection metadata
    sources_checked: int
    sources_available: int
    sources_failed: int
    sources_stale: int
    events_evaluated: int
    events_included: int
    events_suppressed: int

    # Structured content (always present)
    top_events: list          # list[BriefEvent], max 5
    overall_risk: str         # GREEN | AMBER | RED | UNKNOWN

    # Narrative (LLM-generated; None if all providers failed)
    executive_snapshot: Optional[str]
    emerging_themes: Optional[list]
    forward_watch: Optional[list]
    cps230_implications: Optional[list]
    bottom_line: Optional[str]

    # Quality indicators
    narrative_available: bool
    llm_used: bool
    provider_used: Optional[str]
    confidence: float
    trigger_type: str         # scheduled | on_demand | test
