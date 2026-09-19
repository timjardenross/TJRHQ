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
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)

# core_events.status values (core/platform/event_bus.py::_VALID_STATUSES)
# that mean "a Captain or the dispatcher has already seen this" — the
# persistence gate's dedup key, per the consolidation mission's §7
# ("Rework Attention Semantics").
_ALREADY_SURFACED_STATUSES = {"acknowledged", "dismissed", "superseded"}


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

    # Phase 4 (attention-semantics rework, consolidation mission §7):
    # gating for the persistence/novelty check applied on top of the
    # threshold cut above, not a replacement for it. Conservative by the
    # same "favour under- over over-interruption" logic as the floors
    # above — a stable, already-surfaced condition should stop
    # re-interrupting, but a real change of this size or more never gets
    # suppressed.
    material_change_delta: int = 15
    recurrence_lookback_hours: int = 24


@dataclass
class AttentionDecision:
    """The routing outcome for one event. Every field traces back to a
    queryable input (Blueprint Principle 3: 'every Attention decision
    traces to a queryable score and an Audit event') — nothing here is a
    black-box judgment."""

    event_id: str | None
    category: AttentionCategory
    reason: str
    importance: int | None
    confidence: int | None
    relevance: int | None
    domain: str
    event_type: str
    aggregation_key: str | None = None
    related_event_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)  # MSN-0328 Wave 2 — see core_events.metrics
    # Briefs/Captain's Brief consolidation signal-leakage fix: the event's
    # own `description` (readable content, e.g. a headline or a state
    # transition) — carried through unchanged so a downstream consumer with
    # no genuine recommendation can fall back to this instead of a bare
    # scoring formula (`reason`), without ever mistaking it for a
    # recommendation. Never populated from `recommended_action`.
    description: str | None = None
    # Phase 4 (attention-semantics rework, consolidation mission §7): set
    # only when the persistence gate downgraded this decision away from a
    # fresh INTERRUPT_NOW because it is a recurrence of an already-
    # surfaced, materially-unchanged prior event — the event_id of that
    # prior event, so the downgrade traces to a real queryable row
    # (Blueprint Principle 3), same convention as `related_event_ids` for
    # SHOULD_BE_SUMMARISED.
    duplicate_of_event_id: str | None = None


def _parse_occurred_at(value: Any) -> datetime | None:
    """Best-effort parse of a `core_events.occurred_at` value (timestamptz
    from Supabase is an ISO string; tests may pass a real `datetime`).
    Returns None — never "now" — for anything missing or unparseable, so
    an event with no timestamp gets no recency filtering rather than a
    fabricated one."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _find_recurrence(
    event: dict[str, Any],
    recent_surfaced: list[dict[str, Any]],
    *,
    lookback_hours: int,
) -> dict[str, Any] | None:
    """Deterministic recurrence lookup: the most recent row in
    `recent_surfaced` sharing this event's (domain, event_type) whose
    `status` shows it was already surfaced (acknowledged/dismissed/
    superseded — `core/platform/event_bus.py`'s own status vocabulary),
    within `lookback_hours` of this event's own `occurred_at`.

    Matches by (domain, event_type) rather than title similarity (the
    technique `intelligence/brief/comparison.py` uses for
    `intelligence_briefs.top_events`) because `core_events` has no title
    column — (domain, event_type) is this table's own deterministic
    grouping key (the same pair `evaluate_batch()`'s SHOULD_BE_AGGREGATED
    branch below already groups by). A row is allowed to match itself
    (same event_id): that is the common real case where the very same
    already-acknowledged row is simply re-polled on the next evaluation
    cycle, and it correctly carries zero delta against itself.
    """
    domain = event.get("domain")
    event_type = event.get("event_type")
    event_time = _parse_occurred_at(event.get("occurred_at"))
    cutoff = event_time - timedelta(hours=lookback_hours) if event_time else None

    best: tuple[datetime, dict[str, Any]] | None = None
    for row in recent_surfaced:
        if row.get("domain") != domain or row.get("event_type") != event_type:
            continue
        if (row.get("status") or "new") not in _ALREADY_SURFACED_STATUSES:
            continue
        row_time = _parse_occurred_at(row.get("occurred_at"))
        if cutoff is not None and row_time is not None and row_time < cutoff:
            continue
        sort_key = row_time or datetime.min.replace(tzinfo=timezone.utc)
        if best is None or sort_key > best[0]:
            best = (sort_key, row)

    return best[1] if best else None


def _is_material_change(event: dict[str, Any], prior: dict[str, Any], delta: int) -> bool:
    """True if importance or confidence moved by >= `delta` since `prior`
    — a genuine change, not just a re-poll of a stable condition. Either
    side missing a score means there is nothing to compare, so this
    returns True (never silently suppress on incomplete data) rather than
    defaulting a missing score to a number — same "absent is not
    defaulted" convention `evaluate_event()` already applies to its own
    threshold cut."""
    cur_importance, cur_confidence = event.get("importance"), event.get("confidence")
    prior_importance, prior_confidence = prior.get("importance"), prior.get("confidence")
    if None in (cur_importance, cur_confidence, prior_importance, prior_confidence):
        return True
    return abs(cur_importance - prior_importance) >= delta or abs(cur_confidence - prior_confidence) >= delta


def _apply_recurrence_gate(
    event: dict[str, Any],
    decision: AttentionDecision,
    recent_surfaced: list[dict[str, Any]],
    t: AttentionThresholds,
) -> AttentionDecision:
    """Materiality/novelty/persistence gate (consolidation mission §7):
    additional gating layered on top of the threshold cut in
    `_route_by_threshold()`, not a replacement for it. An event that
    clears the threshold into INTERRUPT_NOW but is a recurrence of an
    already-surfaced, materially-unchanged prior event is downgraded — a
    prior `dismissed` event is the strongest signal available (a Captain
    explicitly said "not this") and downgrades all the way to
    SHOULD_SIMPLY_BE_REMEMBERED; `acknowledged`/`superseded` downgrade to
    CAN_BE_DELAYED (already seen, still worth a look, just not urgent
    again). A genuine change (`_is_material_change`) always wins — this
    never suppresses a real escalation.
    """
    prior = _find_recurrence(event, recent_surfaced, lookback_hours=t.recurrence_lookback_hours)
    if prior is None or _is_material_change(event, prior, t.material_change_delta):
        return decision

    prior_status = prior.get("status")
    decision.category = (
        AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED
        if prior_status == "dismissed"
        else AttentionCategory.CAN_BE_DELAYED
    )
    decision.duplicate_of_event_id = prior.get("event_id")
    decision.reason = (
        f"recurrence of already-{prior_status} event {prior.get('event_id')} "
        f"({decision.domain}/{decision.event_type}) within {t.recurrence_lookback_hours}h "
        f"with importance/confidence moved < {t.material_change_delta} — not re-interrupting "
        "a stable, already-surfaced condition"
    )
    return decision


def evaluate_event(
    event: dict[str, Any],
    *,
    thresholds: AttentionThresholds | None = None,
    recent_surfaced: list[dict[str, Any]] | None = None,
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

    `recent_surfaced` (Phase 4, consolidation mission §7): optional list
    of `core_events`-shaped rows to check this event's recurrence against
    — typically the same batch being evaluated (so an event whose own
    `status` already moved past "new" gates against itself) and/or a
    broader history window a caller has separately polled. Omitted (the
    default) means no recurrence check runs at all — identical behaviour
    to before this gate existed. Only ever narrows an INTERRUPT_NOW
    decision to something less disruptive; never widens one, and never
    touches any other category.
    """
    t = thresholds or AttentionThresholds()
    decision = _route_by_threshold(event, t)
    if decision.category == AttentionCategory.INTERRUPT_NOW and recent_surfaced:
        decision = _apply_recurrence_gate(event, decision, recent_surfaced, t)
    return decision


def _route_by_threshold(event: dict[str, Any], t: AttentionThresholds) -> AttentionDecision:
    """The original pure threshold cut (unchanged) — factored out of
    `evaluate_event()` so the Phase 4 persistence gate above can wrap it
    without touching this logic at all."""
    importance = event.get("importance")
    confidence = event.get("confidence")
    domain = event.get("domain", "unknown")
    event_type = event.get("event_type", "unknown")
    event_id = event.get("event_id")
    metrics = event.get("metrics") or {}
    description = event.get("description")

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
            metrics=metrics,
            description=description,
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
            metrics=metrics,
            description=description,
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
            metrics=metrics,
            description=description,
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
            metrics=metrics,
            description=description,
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
        metrics=metrics,
        description=description,
    )


def evaluate_batch(
    events: list[dict[str, Any]],
    *,
    thresholds: AttentionThresholds | None = None,
    related_edges: dict[str, list[str]] | None = None,
    recent_surfaced: list[dict[str, Any]] | None = None,
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

    `recent_surfaced` (Phase 4, consolidation mission §7) is forwarded
    unchanged to every `evaluate_event()` call — see that function's
    docstring. A decision the persistence gate downgrades out of
    INTERRUPT_NOW here (into CAN_BE_DELAYED/SHOULD_SIMPLY_BE_REMEMBERED)
    becomes eligible for the SHOULD_BE_SUMMARISED/SHOULD_BE_AGGREGATED
    grouping below like any other non-interrupt decision — deliberate,
    not a gap: 3+ recurring-and-suppressed events in one batch is still
    an honest count/trend worth aggregating.

    Per-event categories (interrupt/never/delayed/remembered) from
    `evaluate_event()` take precedence for any event that also happens to
    share a group — an interrupt-worthy event is never silently folded
    into an aggregate.
    """
    decisions = [
        evaluate_event(e, thresholds=thresholds, recent_surfaced=recent_surfaced) for e in events
    ]

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
    "AttentionDecision",
    "AttentionThresholds",
    "evaluate_batch",
    "evaluate_event",
]
