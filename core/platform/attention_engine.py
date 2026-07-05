"""Attention Engine (Captain Intelligence Platform, MSN-0306 Programme B).

Formalises the Cognitive Model designed in MSN-0301 Workstream A and approved
unchanged by the Captain Intelligence Blueprint v1.0 (MSN-0304 §4): six
categories, each a routing decision over fields `core_events` already
carries (`importance`, `confidence`, `relevance`) plus Relationship Model
(summarisation) and Unified Memory (remembering). No new data model — this
module is a thin, pure routing table, not a rule engine that guesses at
domain semantics; scoring the raw fields is the emitting domain's job
(Domain Intelligence Framework contract), not this module's.

MSN-0306 scope (Blueprint §13/§14 Wave boundary): this module operates on
synthetic or real event dicts shaped like `core_events` rows — it has no
Supabase dependency and performs no I/O of its own. It is deliberately safe
to build and test against synthetic fixtures in parallel with Programme A
(real domain emitters, Wave 0/1) because it makes no live-system claim and
produces no Captain-facing output on its own. Wiring this against real
`event_bus.poll_events()` output is Wave 2 (Blueprint §14), gated on at
least one domain's emission being confirmed live — not part of this build.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

log = logging.getLogger(__name__)


class AttentionCategory(str, Enum):
    """The six categories of MSN-0301 Workstream A's Cognitive Model.

    Values are the exact category names used in MSN-0301/MSN-0304 so any
    downstream consumer (a future Captain Brief, this module's own tests,
    a Registry cross-reference) can treat this as the canonical vocabulary.
    """

    INTERRUPT_NOW = "interrupt_now"
    NEVER_INTERRUPT = "never_interrupt"
    CAN_BE_DELAYED = "can_be_delayed"
    SHOULD_BE_SUMMARISED = "should_be_summarised"
    SHOULD_BE_AGGREGATED = "should_be_aggregated"
    SHOULD_SIMPLY_BE_REMEMBERED = "should_simply_be_remembered"


@dataclass(frozen=True)
class AttentionThresholds:
    """Tunable thresholds for the routing table. Defaults are deliberately
    conservative (favour under- over over-interruption) and are themselves
    a Wave 3 (Priority & Opportunity Engine, MSN-0301 Workstream F) learning
    target, not a value fixed here forever — see `evaluation_metrics` in
    this mission's completion dossier for how drift would be measured."""

    interrupt_importance_floor: int = 75
    interrupt_confidence_floor: int = 70
    never_interrupt_importance_ceiling: int = 20
    delayed_importance_floor: int = 40


@dataclass
class AttentionDecision:
    """The routing outcome for one event. Every field traces back to a
    queryable input (Blueprint Principle 3: 'every Attention decision
    traces to a queryable score and an Audit event') — nothing here is a
    black-box judgment."""

    event_id: Optional[str]
    category: AttentionCategory
    reason: str
    importance: Optional[int]
    confidence: Optional[int]
    relevance: Optional[int]
    domain: str
    event_type: str
    aggregation_key: Optional[str] = None
    related_event_ids: list[str] = field(default_factory=list)


def evaluate_event(
    event: dict[str, Any],
    *,
    thresholds: Optional[AttentionThresholds] = None,
) -> AttentionDecision:
    """Route one `core_events`-shaped dict to an AttentionCategory.

    `event` must carry at minimum `event_type` and `domain` (both required,
    non-nullable on `core_events` itself); `importance`/`confidence`/
    `relevance` are optional (nullable on the real table) and are treated
    as absent (never interrupt, never remembered-as-important) rather than
    defaulted to a numeric value — an unscored event should not silently
    behave as a scored one.

    This function does not decide "should be summarised" or "should be
    aggregated" on its own (those require comparing against *other*
    events, via Relationship Model edges or a shared `event_type`/`domain`
    grouping) — call `evaluate_batch()` for that. A single-event call
    always resolves to one of the four single-event categories.
    """
    t = thresholds or AttentionThresholds()
    importance = event.get("importance")
    confidence = event.get("confidence")
    domain = event.get("domain", "unknown")
    event_type = event.get("event_type", "unknown")
    event_id = event.get("event_id")

    if importance is not None and importance <= t.never_interrupt_importance_ceiling:
        return AttentionDecision(
            event_id=event_id,
            category=AttentionCategory.NEVER_INTERRUPT,
            reason=f"importance={importance} <= floor {t.never_interrupt_importance_ceiling}",
            importance=importance,
            confidence=confidence,
            relevance=event.get("relevance"),
            domain=domain,
            event_type=event_type,
        )

    if (
        importance is not None
        and confidence is not None
        and importance >= t.interrupt_importance_floor
        and confidence >= t.interrupt_confidence_floor
    ):
        return AttentionDecision(
            event_id=event_id,
            category=AttentionCategory.INTERRUPT_NOW,
            reason=(
                f"importance={importance} >= {t.interrupt_importance_floor} AND "
                f"confidence={confidence} >= {t.interrupt_confidence_floor}"
            ),
            importance=importance,
            confidence=confidence,
            relevance=event.get("relevance"),
            domain=domain,
            event_type=event_type,
        )

    if importance is not None and importance >= t.interrupt_importance_floor and (
        confidence is None or confidence < t.interrupt_confidence_floor
    ):
        return AttentionDecision(
            event_id=event_id,
            category=AttentionCategory.CAN_BE_DELAYED,
            reason=(
                f"importance={importance} >= {t.interrupt_importance_floor} but "
                f"confidence={confidence} below floor {t.interrupt_confidence_floor} "
                "(high-importance-but-unverified never interrupts, per MSN-0301 Workstream A)"
            ),
            importance=importance,
            confidence=confidence,
            relevance=event.get("relevance"),
            domain=domain,
            event_type=event_type,
        )

    if importance is not None and importance >= t.delayed_importance_floor:
        return AttentionDecision(
            event_id=event_id,
            category=AttentionCategory.CAN_BE_DELAYED,
            reason=f"importance={importance} in mid-range [{t.delayed_importance_floor}, {t.interrupt_importance_floor})",
            importance=importance,
            confidence=confidence,
            relevance=event.get("relevance"),
            domain=domain,
            event_type=event_type,
        )

    return AttentionDecision(
        event_id=event_id,
        category=AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED,
        reason="importance below the delayed floor (or absent) — low-salience, retained not surfaced",
        importance=importance,
        confidence=confidence,
        relevance=event.get("relevance"),
        domain=domain,
        event_type=event_type,
    )


def evaluate_batch(
    events: list[dict[str, Any]],
    *,
    thresholds: Optional[AttentionThresholds] = None,
    related_edges: Optional[dict[str, list[str]]] = None,
) -> list[AttentionDecision]:
    """Route a batch of events, additionally detecting the two
    batch-only categories from MSN-0301 Workstream A:

    - SHOULD_BE_SUMMARISED: 2+ events connected by a Relationship Model
      edge (passed in as `related_edges`, a mapping of event_id -> list of
      related event_ids — this function does not itself query
      Relationship Model; that wiring is Wave 2, per this module's own
      docstring).
    - SHOULD_BE_AGGREGATED: 3+ events sharing the same (domain, event_type)
      pair in this batch — a count/trend, not N individual events, per
      MSN-0301 Workstream A's own definition.

    Per-event categories (interrupt/never/delayed/remembered) from
    `evaluate_event()` take precedence for any event that also happens to
    share a group — an interrupt-worthy event is never silently folded
    into an aggregate.
    """
    decisions = [evaluate_event(e, thresholds=thresholds) for e in events]

    single_event_categories = {
        AttentionCategory.INTERRUPT_NOW,
        AttentionCategory.NEVER_INTERRUPT,
    }

    if related_edges:
        for decision in decisions:
            if decision.category in single_event_categories:
                continue
            related = related_edges.get(decision.event_id or "", [])
            if len(related) >= 1:
                decision.category = AttentionCategory.SHOULD_BE_SUMMARISED
                decision.related_event_ids = related
                decision.reason = f"{len(related)} related event(s) via Relationship Model edge — summarise, don't repeat"

    group_counts: dict[tuple[str, str], list[AttentionDecision]] = {}
    for decision in decisions:
        if decision.category in single_event_categories or decision.category == AttentionCategory.SHOULD_BE_SUMMARISED:
            continue
        key = (decision.domain, decision.event_type)
        group_counts.setdefault(key, []).append(decision)

    for (domain, event_type), group in group_counts.items():
        if len(group) >= 3:
            for decision in group:
                decision.category = AttentionCategory.SHOULD_BE_AGGREGATED
                decision.aggregation_key = f"{domain}:{event_type}"
                decision.reason = f"{len(group)} events sharing domain={domain}/event_type={event_type} in this batch — aggregate as a count/trend"

    return decisions


__all__ = [
    "AttentionCategory",
    "AttentionThresholds",
    "AttentionDecision",
    "evaluate_event",
    "evaluate_batch",
]
