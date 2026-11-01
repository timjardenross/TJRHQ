"""
Data models for the OR Intelligence Agent.
All fields required for source attribution and audit trail.
"""

from dataclasses import dataclass, field
from datetime import datetime


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
    rss_url: str | None = None
    api_endpoint: str | None = None
    notes: str | None = None
    # continuous: zero items is suspicious (news/regulatory feeds).
    # intermittent: zero items is the expected, correct state most of the time
    # (incident-only status feeds) — must not be flagged as degraded on that basis alone.
    content_expectation: str = "continuous"


@dataclass
class SourceHealth:
    source_id: str
    source_name: str
    checked_at: datetime
    status: str               # ok | stale | failed | degraded | skipped
    items_retrieved: int = 0
    latency_ms: int | None = None
    error_message: str | None = None
    http_status: int | None = None
    # Orthogonal to status — whether the retrieved content is genuinely real, not
    # generic site furniture/marketing boilerplate/a stale identical repeat/a JS
    # template placeholder. None = not evaluated by this adapter type.
    content_valid: bool | None = None
    content_validity_reason: str | None = None


@dataclass
class IntelligenceItem:
    """Raw collected item before classification."""
    source_id: str
    source_name: str
    source_priority: int
    source_confidence_weight: float
    source_category: str
    raw_title: str
    collected_at: datetime
    raw_summary: str | None = None
    canonical_url: str | None = None
    published_at: datetime | None = None


@dataclass
class ClassifiedEvent:
    """Item after classification and dedup check."""
    event_id: str
    source_id: str
    source_name: str
    source_priority: int
    source_confidence_weight: float
    source_category: str
    raw_title: str
    raw_summary: str | None
    canonical_url: str | None
    published_at: datetime | None
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
    suppression_reason: str | None = None
    affected_cves: list[str] = field(default_factory=list)  # CVE IDs extracted from title/summary


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
    canonical_url: str | None
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
    executive_snapshot: str | None
    emerging_themes: list | None
    forward_watch: list | None
    cps230_implications: list | None
    bottom_line: str | None

    # Quality indicators
    narrative_available: bool
    llm_used: bool
    provider_used: str | None
    confidence: float
    trigger_type: str         # scheduled | on_demand | test

    # Briefs canonical uplift (BRIEFS_CANONICAL_UPLIFT.md) — all optional,
    # None on a brief generated before this uplift or when the underlying
    # computation had nothing to report (e.g. no prior brief to compare to).
    morning_cycle_id: str | None = None   # AEST date 'YYYY-MM-DD' of this morning's collection cycle
    coverage: dict | None = None          # structured collection coverage / degraded-cutoff record
    comparison: dict | None = None        # deterministic vs-prior-brief diff (new/escalated/improved/...)
    domain_picture: dict | None = None    # deterministic domain grouping of top_events
    known_unknowns: list | None = None    # LLM-identified evidence gaps, if any
