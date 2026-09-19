"""Domains — merged cross-domain assembly (Briefs/Captain's Brief
consolidation, Phase 2. See BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md §4.1/§6).

Two pipelines synthesise domain pictures independently today:

- Briefs' OSINT `domain_picture` (technical/regulatory/environmental/
  payments + Health OSINT + Emergency Alert Hub, intelligence_briefs table,
  `intelligence/brief/domain_picture.py`) — a stored snapshot from the most
  recent morning brief.
- Captain's Brief's event-bus domain sections (health/operational_
  intelligence/engineering/learning/opportunities,
  `core/platform/captain_brief_orchestrator.py`) — always live, computed
  fresh from `core_events` on every call.

Per the consolidation doc's own recommendation (§4.1), this module is the
one shared assembly step that normalises both into a single list of
`DomainSummary` objects — the mission's own schema (posture, confidence,
what changed, what matters, watch conditions, evidence count with
drill-down) — so the Briefs "Domains" tab renders one document instead of
reconciling two structurally incompatible shapes itself. Nothing here
recomputes either pipeline's own synthesis (`compute_domain_picture()` /
`assemble_captain_brief_document()` are both reused verbatim) — this only
normalises their already-computed output into one shape and derives the
handful of summary fields (posture/confidence/what-matters/watch) neither
pipeline expresses per-domain today.

Pure function, no I/O — same contract as `assemble_captain_brief_document()`:
takes already-fetched events and the already-fetched latest brief row as
arguments, so it's testable without a live DB or event bus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_contract import CaptainBriefItem
from core.platform.captain_brief_orchestrator import assemble_captain_brief_document

# Posture thresholds mirror captain_brief_orchestrator.py's own
# _WARNING_RISK_THRESHOLD (60.0) for RED; AMBER is this module's own choice
# for a mid-tier "worth watching" cut, kept local rather than importing that
# module's private constant.
_POSTURE_RED = 60.0
_POSTURE_AMBER = 30.0

# The five event-bus domain sections CaptainBriefDocument exposes as public
# fields (captain_brief_orchestrator.py's _DOMAIN_SECTION_MAP targets) —
# labels kept in parity with captains-brief-workbench/_components/types.ts's
# DOMAIN_SECTIONS so the two UIs describe the same domains the same way.
_EVENT_BUS_DOMAIN_LABELS: dict[str, str] = {
    "health": "Health",
    "operational_intelligence": "Operational Intelligence",
    "engineering": "Engineering",
    "learning": "Learning",
    "opportunities": "Opportunities",
}


@dataclass
class DomainEvidenceItem:
    """One drill-down preview row — never the full underlying event, just
    enough to decide whether to follow `DomainSummary.detail_href`."""

    title: str
    detail: str | None = None
    risk: str | None = None  # RED/AMBER/GREEN/UNKNOWN, when known


@dataclass
class DomainSummary:
    key: str
    label: str
    source: str  # "osint" | "event_bus"
    posture: str  # RED/AMBER/GREEN/UNKNOWN
    confidence: float | None  # 0-100 mean, None if not computable — never fabricated
    what_changed: str | None
    what_matters: list[str] = field(default_factory=list)
    watch_conditions: list[str] = field(default_factory=list)
    evidence_count: int = 0
    evidence: list[DomainEvidenceItem] = field(default_factory=list)
    as_of: str | None = None
    availability: str = "ok"  # "ok" | "no_data" | "degraded" | "unavailable"
    detail_href: str | None = None


@dataclass
class DomainsDocument:
    generated_at: str
    domains: list[DomainSummary] = field(default_factory=list)
    event_bus_as_of: str | None = None
    osint_as_of: str | None = None
    osint_available: bool = True
    warnings: list[str] = field(default_factory=list)


def _risk_label(risk_score: float | None) -> str | None:
    if risk_score is None:
        return None
    if risk_score >= _POSTURE_RED:
        return "RED"
    if risk_score >= _POSTURE_AMBER:
        return "AMBER"
    return "GREEN"


def _posture_for_items(items: list[CaptainBriefItem]) -> str:
    risk_scores = [i.risk_score for i in items if i.risk_score is not None]
    if not risk_scores:
        return "UNKNOWN"
    return _risk_label(max(risk_scores)) or "UNKNOWN"


def _confidence_for_items(items: list[CaptainBriefItem]) -> float | None:
    scores = [
        i.recommendation.confidence
        for i in items
        if i.recommendation is not None and i.recommendation.confidence is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _event_bus_domain_summary(
    key: str, label: str, items: list[CaptainBriefItem], generated_at: str
) -> DomainSummary:
    interrupt_count = sum(1 for i in items if i.category == AttentionCategory.INTERRUPT_NOW)
    what_changed = f"{interrupt_count} item(s) need attention now" if interrupt_count else None

    # Signal-leakage fix (same pattern as the `recommended_action` fix this
    # module's own docstring references — see captain_brief_contract.py's
    # `CaptainBriefItem.description` docstring: "fall back to this, never
    # to `reason` [...] a scoring formula"). `item.reason` is the Attention
    # Engine's internal routing formula — e.g. "importance=80 >= 75 AND
    # confidence=90 >= 65", or, for a SHOULD_BE_AGGREGATED group, "9 events
    # sharing domain=X/event_type=Y in this batch — aggregate as a count/
    # trend" — never fit for a Captain-facing "what matters"/"watch"/
    # evidence line. `description` (the event's own readable headline, e.g.
    # a source's `error_message`) is the only field these three should
    # read; an item with no description simply contributes nothing here,
    # rather than leaking the formula string.
    what_matters: list[str] = []
    for item in sorted(items, key=lambda i: i.priority_score or 0, reverse=True):
        if item.description and item.description not in what_matters:
            what_matters.append(item.description)
        if len(what_matters) >= 3:
            break

    watch_conditions: list[str] = []
    for item in items:
        if (
            item.risk_score is not None
            and item.risk_score >= _POSTURE_AMBER
            and item.description
            and item.description not in watch_conditions
        ):
            watch_conditions.append(item.description)
        if len(watch_conditions) >= 3:
            break

    evidence = [
        DomainEvidenceItem(title=item.event_type or item.domain, detail=item.description, risk=_risk_label(item.risk_score))
        for item in items[:5]
    ]

    return DomainSummary(
        key=key,
        label=label,
        source="event_bus",
        posture=_posture_for_items(items),
        confidence=_confidence_for_items(items),
        what_changed=what_changed,
        what_matters=what_matters,
        watch_conditions=watch_conditions,
        evidence_count=len(items),
        evidence=evidence,
        as_of=generated_at,
        availability="ok" if items else "no_data",
        detail_href=f"/captains-brief-workbench?domain={key}",
    )


def _osint_domain_summary(bucket_key: str, bucket: dict[str, Any], as_of: str | None, degraded: bool) -> DomainSummary:
    events = bucket.get("events") or []
    evidence = [
        DomainEvidenceItem(title=e.get("title") or "Untitled", risk=(e.get("risk_rating") or None))
        for e in events[:5]
    ]
    watch_conditions = [
        e["title"] for e in events if e.get("title") and (e.get("risk_rating") or "").upper() in ("RED", "AMBER")
    ][:3]

    return DomainSummary(
        key=bucket_key,
        label=bucket.get("label") or bucket_key.title(),
        source="osint",
        posture=(bucket.get("worst_risk") or "UNKNOWN"),
        # domain_picture.py's buckets don't carry a numeric confidence today
        # — left None rather than fabricated.
        confidence=None,
        # comparison.py's new/escalated/improved isn't bucket-scoped today
        # — left None rather than fabricated.
        what_changed=None,
        what_matters=[e.get("title") for e in events[:3] if e.get("title")],
        watch_conditions=watch_conditions,
        evidence_count=int(bucket.get("count") or len(events)),
        evidence=evidence,
        as_of=as_of,
        availability="degraded" if degraded else "ok",
        detail_href=None,  # filled in by the caller once brief_id is known
    )


def assemble_domains_document(events: list[dict[str, Any]], latest_brief: dict[str, Any] | None) -> DomainsDocument:
    """Merge Captain's Brief's live event-bus domains with Briefs' latest
    stored OSINT `domain_picture` into one cross-domain document.

    `events`: already-polled `core_events` rows (event_bus.poll_events()'s
    return shape) — passed through to `assemble_captain_brief_document()`
    unchanged.
    `latest_brief`: the raw `intelligence_briefs` row from
    `intelligence_store.load_latest_brief()`, or None if no brief has been
    generated yet (a real, honestly-represented state — see the
    `osint_available` field — not an error).
    """
    cb_doc = assemble_captain_brief_document(events)
    generated_at = cb_doc.generated_at.isoformat() if hasattr(cb_doc.generated_at, "isoformat") else str(cb_doc.generated_at)

    domains: list[DomainSummary] = [
        _event_bus_domain_summary(key, label, getattr(cb_doc, key), generated_at)
        for key, label in _EVENT_BUS_DOMAIN_LABELS.items()
    ]

    warnings: list[str] = []
    osint_as_of: str | None = None
    osint_available = latest_brief is not None

    if latest_brief is None:
        warnings.append(
            "No OSINT brief has been generated yet — Technical/Regulatory/Environmental/"
            "Payments/Health/Emergency domains are unavailable."
        )
    else:
        osint_as_of = latest_brief.get("published_at") or latest_brief.get("generated_at")
        coverage = latest_brief.get("coverage") or {}
        degraded = bool(coverage.get("degraded"))
        picture = latest_brief.get("domain_picture") or {}
        brief_id = latest_brief.get("brief_id")

        if not picture:
            warnings.append("The latest brief has no domain picture to group — nothing to show for OSINT domains.")
        for bucket_key, bucket in picture.items():
            summary = _osint_domain_summary(bucket_key, bucket, osint_as_of, degraded)
            summary.detail_href = f"/briefs/{brief_id}" if brief_id else None
            domains.append(summary)

        if degraded:
            warnings.append("The latest brief's collection cycle was degraded — OSINT domain coverage may be incomplete.")

    return DomainsDocument(
        generated_at=generated_at,
        domains=domains,
        event_bus_as_of=generated_at,
        osint_as_of=osint_as_of,
        osint_available=osint_available,
        warnings=warnings,
    )
