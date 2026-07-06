"""Captain Brief Orchestration (Captain Experience Programme, MSN-0313).

Assembles the canonical `CaptainBriefDocument` — the single, UI-independent
intelligence product every future Captain Experience (web, mobile, voice,
conversational) presents differently. This module builds NOTHING new at
the primitive level: it composes Event Bus, Attention Engine, Priority &
Opportunity Engine, and the Recommendation adapter — all already built
(MSN-0301/0306/0308) — into one richer, domain-organised document. The
existing `captain_brief_contract.py::CaptainBrief` (Cognitive-Model-
categorised view: interrupt_now/can_be_delayed/etc.) is reused directly,
not reimplemented — `CaptainBriefDocument` wraps it and adds domain-grouped
sections, a narrative summary, and metadata on top.

No UI, no rendering, no scheduling, no I/O beyond `event_bus.poll_events()`
— matches this mission's own Out of Scope exactly. This module produces one
plain-dataclass object; any future interface (Design Officer's concurrent
UI work, Telegram, LCARS, voice) consumes it without needing to know how
it was assembled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.platform.attention_engine import AttentionCategory, evaluate_batch
from core.platform.priority_engine import PriorityInputs, PriorityScore, rank_events
from core.platform.captain_brief_contract import (
    CaptainBrief,
    CaptainBriefItem,
    Recommendation,
    assemble_captain_brief,
    recommendations_from_events,
)

CAPTAIN_BRIEF_DOCUMENT_VERSION = "1.0"

# Domain -> section mapping (Workstream B). Only real, live-verified domains
# (MSN-0305) are mapped; a domain with no mapping simply doesn't appear in
# any section today — not an error, an honest reflection of what's real.
_DOMAIN_SECTION_MAP: dict[str, str] = {
    "health-intelligence": "health",
    "operational-resilience-intelligence": "operational_intelligence",
    "wellness-coaching": "health",  # Wellness Coaching is Health-adjacent per the Registry's own domain grouping
    "engineering": "engineering",
    "engineering-intelligence": "engineering",
    "research-learning": "learning",
    "research-learning-intelligence": "learning",
    "content-intelligence": "opportunities",
    # MSN-0328 Wave 2: new real emitters wired to close the content gap
    # between this pipeline and the surfaces converging onto it.
    "mission-lifecycle": "operational_intelligence",
    "engineering-delivery": "engineering",
    "strategic-planning": "operational_intelligence",
}

_WARNING_RISK_THRESHOLD = 60.0  # PriorityScore.risk_score above this is surfaced as a warning, not just ranked


@dataclass
class CaptainBriefDocument:
    """The canonical Captain Brief object (Workstream A). Every field is
    plain data (dataclasses, lists, strings, floats) — deliberately
    JSON-serialisable with no rendering logic, so any future interface can
    consume it directly (Workstream F: Future Extension Points)."""

    version: str
    generated_at: datetime
    summary: str
    priorities: list[CaptainBriefItem]
    recommendations: list[Recommendation]
    health: list[CaptainBriefItem]
    operational_intelligence: list[CaptainBriefItem]
    engineering: list[CaptainBriefItem]
    learning: list[CaptainBriefItem]
    opportunities: list[CaptainBriefItem]
    warnings: list[CaptainBriefItem]
    next_actions: list[str]
    metadata: dict[str, Any]
    confidence: Optional[float]


def _section_for_domain(domain: str) -> Optional[str]:
    return _DOMAIN_SECTION_MAP.get(domain)


def _generate_summary(
    total_events: int,
    domains_represented: set[str],
    priorities: list[CaptainBriefItem],
    warnings: list[CaptainBriefItem],
) -> str:
    """Workstream D — Narrative Generation. Deterministic, template-based,
    no LLM call: every sentence traces directly to a countable fact in the
    assembled document, matching Blueprint Principle 3 ("every
    recommendation must be explainable") applied to the summary itself.
    Answers exactly the 3 questions this mission's brief names: what
    changed, why it matters, what to do."""
    if total_events == 0:
        return "No new signals since the last brief."

    domain_count = len(domains_represented)
    parts = [f"{total_events} signal(s) across {domain_count} domain(s) since the last brief."]

    if warnings:
        parts.append(f"{len(warnings)} item(s) flagged as high-risk (low confidence, high stakes) — review first.")

    if priorities:
        top = priorities[0]
        parts.append(
            f"Top priority: {top.domain}/{top.event_type} (score {top.priority_score:.1f})"
            + (f" — {top.recommendation.description}" if top.recommendation else "")
            + "."
        )
    else:
        parts.append("Nothing requires immediate attention.")

    return " ".join(parts)


def _next_actions(recommendations: list[Recommendation], warnings: list[CaptainBriefItem]) -> list[str]:
    """Concise, deduplicated action list — one line per distinct
    recommendation description, warnings first (matches the summary's own
    "review first" framing)."""
    seen: set[str] = set()
    actions: list[str] = []
    for item in warnings:
        if item.recommendation and item.recommendation.description not in seen:
            seen.add(item.recommendation.description)
            actions.append(item.recommendation.description)
    for rec in recommendations:
        if rec.description not in seen:
            seen.add(rec.description)
            actions.append(rec.description)
    return actions


def assemble_captain_brief_document(
    events: list[dict[str, Any]],
    *,
    priority_weights: Optional[Any] = None,
    top_n_priorities: int = 10,
) -> CaptainBriefDocument:
    """The single assembly entry point (Workstream B/C combined) — pull
    already-polled `core_events`-shaped dicts (caller's responsibility to
    fetch via `event_bus.poll_events()`; this function does no I/O of its
    own, matching Attention/Priority Engine's own pure-function design),
    run them through Attention Engine (unchanged) and Priority Engine
    (unchanged), attach Recommendations (existing adapter, MSN-0308), group
    by domain section, generate a narrative summary, and return one
    `CaptainBriefDocument`.
    """
    decisions = evaluate_batch(events)
    recommendations_map = recommendations_from_events(events)

    inputs = [
        PriorityInputs(
            event_id=e.get("event_id"),
            domain=e.get("domain", "unknown"),
            event_type=e.get("event_type", "unknown"),
            importance=e.get("importance"),
            confidence=e.get("confidence"),
            time_sensitivity=e.get("time_sensitivity"),
        )
        for e in events
    ]
    scores = rank_events(inputs, weights=priority_weights)
    score_map: dict[str, PriorityScore] = {s.event_id: s for s in scores if s.event_id}

    brief: CaptainBrief = assemble_captain_brief(
        decisions, priority_scores=score_map, recommendations=recommendations_map
    )

    # Cross-domain priorities: every surfaced (non-never-interrupt,
    # non-remembered-only) item, ranked — not just interrupt_now/can_be_delayed,
    # since should_be_aggregated/should_be_summarised items can still matter.
    surfaced_categories = {
        AttentionCategory.INTERRUPT_NOW,
        AttentionCategory.CAN_BE_DELAYED,
        AttentionCategory.SHOULD_BE_SUMMARISED,
        AttentionCategory.SHOULD_BE_AGGREGATED,
    }
    all_surfaced_items = (
        brief.interrupt_now + brief.can_be_delayed + brief.should_be_summarised + brief.should_be_aggregated
    )
    priorities = sorted(all_surfaced_items, key=lambda i: i.priority_score or 0, reverse=True)[:top_n_priorities]

    # Domain-grouped sections (Workstream A/B)
    health: list[CaptainBriefItem] = []
    operational_intelligence: list[CaptainBriefItem] = []
    engineering: list[CaptainBriefItem] = []
    learning: list[CaptainBriefItem] = []
    opportunities: list[CaptainBriefItem] = []
    for item in all_surfaced_items:
        section = _section_for_domain(item.domain)
        if section == "health":
            health.append(item)
        elif section == "operational_intelligence":
            operational_intelligence.append(item)
        elif section == "engineering":
            engineering.append(item)
        elif section == "learning":
            learning.append(item)
        elif section == "opportunities":
            opportunities.append(item)

    # Warnings (Workstream E-adjacent): high-risk items, per the Priority
    # Engine's own risk_score (importance/confidence inverse) — a distinct
    # cut across the same data, not a new score.
    warnings: list[CaptainBriefItem] = []
    for item in all_surfaced_items:
        score = score_map.get(item.event_id or "")
        if score and score.risk_score >= _WARNING_RISK_THRESHOLD:
            warnings.append(item)

    domains_represented = {e.get("domain", "unknown") for e in events}
    summary = _generate_summary(len(events), domains_represented, priorities, warnings)
    next_actions = _next_actions(list(recommendations_map.values()), warnings)

    # Dedup against priorities' own inline recommendation (Phase 1F, DO
    # finding from the Phase 1E joint review): an item that's both a top
    # priority and carries a recommendation would otherwise show the same
    # guidance twice — once inline on the priority, once again in this
    # top-level list. Same "seen description" technique as _next_actions.
    priority_recommendation_descriptions = {
        item.recommendation.description for item in priorities if item.recommendation
    }
    deduped_recommendations = [
        rec
        for rec in recommendations_map.values()
        if rec.description not in priority_recommendation_descriptions
    ]

    # Document-level confidence: mean of every scored item's confidence,
    # None if no event carried one — never fabricated (Confidence Naming
    # Decision, MSN-0305, applied at the document level too).
    confidences = [e.get("confidence") for e in events if e.get("confidence") is not None]
    doc_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None

    metadata = {
        "total_events": len(events),
        "domains_represented": sorted(domains_represented),
        "attention_category_counts": {
            "interrupt_now": len(brief.interrupt_now),
            "can_be_delayed": len(brief.can_be_delayed),
            "should_be_summarised": len(brief.should_be_summarised),
            "should_be_aggregated": len(brief.should_be_aggregated),
            "remembered_count": brief.remembered_count,
            "never_interrupt_count": brief.never_interrupt_count,
        },
    }

    return CaptainBriefDocument(
        version=CAPTAIN_BRIEF_DOCUMENT_VERSION,
        generated_at=datetime.now(timezone.utc),
        summary=summary,
        priorities=priorities,
        recommendations=deduped_recommendations,
        health=health,
        operational_intelligence=operational_intelligence,
        engineering=engineering,
        learning=learning,
        opportunities=opportunities,
        warnings=warnings,
        next_actions=next_actions,
        metadata=metadata,
        confidence=doc_confidence,
    )


__all__ = [
    "CaptainBriefDocument",
    "CAPTAIN_BRIEF_DOCUMENT_VERSION",
    "assemble_captain_brief_document",
]
