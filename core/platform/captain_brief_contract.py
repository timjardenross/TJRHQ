"""Captain Brief & Recommendation contracts (Captain Intelligence Platform,
MSN-0306 Programme B).

Two data contracts, both design-only scaffolding per this mission's scope:

1. **Captain Brief** — the aggregated, human-facing view MSN-0301 Workstream
   E and the Blueprint v1.0 (MSN-0304 §6) both insist no domain hand-authors:
   "the brief is not a document generated on a timer — it is whatever the
   Attention Engine currently holds." This module defines that view's shape
   and a pure function to assemble it from `AttentionDecision`/`PriorityScore`
   output — it does not fetch events, run on a schedule, or render anything.

2. **Recommendation object model** — a structured replacement for the free-text
   `recommended_action` field on `core_events`. MSN-0302 §8 found that only 3
   of 9 real domains write structured "Required Decisions"/"Potential Actions"
   at all; most bury this in LLM-generated prose. This gives every domain one
   optional, structured shape to fill in instead, without forcing any domain
   to adopt it before it's ready (the field stays free-text-compatible: a
   `Recommendation` can always be flattened to a single string).

MSN-0306 scope boundary: no I/O, no scheduling, no live Captain-facing
output. Wiring this against real `event_bus.poll_events()` data and an
actual delivery surface (Telegram/LCARS) is Wave 4 (Blueprint §14),
gated on Attention/Priority Engine having real data to work with — not
part of this build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.platform.attention_engine import AttentionCategory, AttentionDecision
from core.platform.priority_engine import PriorityScore


@dataclass
class Recommendation:
    """A structured, optional replacement for `core_events.recommended_action`
    free text. Every field is optional except `description` — a domain not
    ready to populate the rest can still emit a plain string via
    `Recommendation(description="...")` and this stays forward-compatible.
    """

    description: str
    action_type: Optional[str] = None  # e.g. "review", "approve", "acknowledge", "investigate"
    confidence: Optional[int] = None  # 0-100 — how sure the emitting domain is this is the right action
    evidence: list[str] = field(default_factory=list)  # file:line / row / event_id references
    requires_approval: bool = False  # maps to the Permissions capability's authority-gating concept
    supporting_context: Optional[str] = None

    def as_text(self) -> str:
        """Flatten to the free-text shape `core_events.recommended_action`
        expects today, for domains/consumers not yet using the structured
        form."""
        return self.description


@dataclass
class CaptainBriefItem:
    """One line of the Captain Brief — an Attention decision, optionally
    enriched with a Priority rank and a structured Recommendation."""

    event_id: Optional[str]
    domain: str
    event_type: str
    category: AttentionCategory
    reason: str
    priority_score: Optional[float] = None
    priority_explanation: Optional[str] = None
    risk_score: Optional[float] = None
    recommendation: Optional[Recommendation] = None
    related_event_ids: list[str] = field(default_factory=list)
    aggregation_key: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)  # MSN-0328 Wave 2 — structured per-domain detail, see core_events.metrics


@dataclass
class CaptainBrief:
    """The full aggregated view for one Captain Brief 'read' — not a
    document generated on a schedule (MSN-0301 Workstream E); this is
    what the Attention/Priority Engines currently hold, queried on demand.
    Fields are grouped by Cognitive Model category, ranked within
    'interrupt_now' and 'can_be_delayed' by Priority score (highest first)
    since those are the categories where relative ordering matters to a
    human deciding what to look at first."""

    generated_at: datetime
    interrupt_now: list[CaptainBriefItem] = field(default_factory=list)
    can_be_delayed: list[CaptainBriefItem] = field(default_factory=list)
    should_be_summarised: list[CaptainBriefItem] = field(default_factory=list)
    should_be_aggregated: list[CaptainBriefItem] = field(default_factory=list)
    remembered_count: int = 0  # count only — individual "remembered" items are not surfaced in the brief itself
    never_interrupt_count: int = 0  # count only, for completeness/audit — never shown to the Captain


def recommendation_from_event(event: dict[str, Any]) -> Optional[Recommendation]:
    """MSN-0308: adapter from `core_events.recommended_action` (free text,
    written by every domain today per MSN-0302 §8) to a `Recommendation`
    object, so `assemble_captain_brief()` can surface something even
    though zero domains populate the structured fields yet (MSN-0307
    finding). Deliberately minimal — wraps the existing text as-is, adds
    no inference, no new domain emitter changes required. A domain that
    starts emitting a real `Recommendation` later simply won't need this
    adapter for its own events; this is a bridge, not a replacement for
    domains adopting the structured form themselves.
    """
    text = event.get("recommended_action")
    if not text:
        return None
    return Recommendation(description=text)


def recommendations_from_events(events: list[dict[str, Any]]) -> dict[str, Recommendation]:
    """Batch form of `recommendation_from_event`, keyed by `event_id` —
    the exact shape `assemble_captain_brief()`'s `recommendations` param
    expects. Events with no `event_id` or no `recommended_action` are
    simply absent from the result, not an error."""
    result: dict[str, Recommendation] = {}
    for event in events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        rec = recommendation_from_event(event)
        if rec is not None:
            result[event_id] = rec
    return result


def assemble_captain_brief(
    decisions: list[AttentionDecision],
    *,
    priority_scores: Optional[dict[str, PriorityScore]] = None,
    recommendations: Optional[dict[str, Recommendation]] = None,
) -> CaptainBrief:
    """Pure function: combine Attention Engine output (required) with
    optional Priority Engine scores and Recommendations, keyed by
    `event_id`, into one `CaptainBrief`. Does not query anything itself —
    the caller is responsible for having already run `evaluate_batch()`
    and (optionally) `rank_events()`.
    """
    priority_scores = priority_scores or {}
    recommendations = recommendations or {}
    brief = CaptainBrief(generated_at=datetime.now(timezone.utc))

    for decision in decisions:
        score = priority_scores.get(decision.event_id or "")
        item = CaptainBriefItem(
            event_id=decision.event_id,
            domain=decision.domain,
            event_type=decision.event_type,
            category=decision.category,
            reason=decision.reason,
            priority_score=score.total_score if score else None,
            priority_explanation=score.explanation if score else None,
            risk_score=score.risk_score if score else None,
            recommendation=recommendations.get(decision.event_id or ""),
            related_event_ids=decision.related_event_ids,
            aggregation_key=decision.aggregation_key,
            metrics=decision.metrics,
        )

        if decision.category == AttentionCategory.INTERRUPT_NOW:
            brief.interrupt_now.append(item)
        elif decision.category == AttentionCategory.CAN_BE_DELAYED:
            brief.can_be_delayed.append(item)
        elif decision.category == AttentionCategory.SHOULD_BE_SUMMARISED:
            brief.should_be_summarised.append(item)
        elif decision.category == AttentionCategory.SHOULD_BE_AGGREGATED:
            brief.should_be_aggregated.append(item)
        elif decision.category == AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED:
            brief.remembered_count += 1
        elif decision.category == AttentionCategory.NEVER_INTERRUPT:
            brief.never_interrupt_count += 1

    brief.interrupt_now.sort(key=lambda i: i.priority_score or 0, reverse=True)
    brief.can_be_delayed.sort(key=lambda i: i.priority_score or 0, reverse=True)

    return brief


__all__ = [
    "Recommendation",
    "CaptainBriefItem",
    "CaptainBrief",
    "assemble_captain_brief",
    "recommendation_from_event",
    "recommendations_from_events",
]
