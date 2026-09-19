"""Briefs/Captain's Brief consolidation, Phase 4 — attention-semantics
rework (mission §7, `BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md`).

Locks in the persistence/novelty gate layered on top of
`attention_engine.py`'s existing threshold cut: a recurring event that
keeps clearing the INTERRUPT_NOW threshold every evaluation cycle must
stop re-interrupting once it has already been surfaced (core_events.
status already acknowledged/dismissed/superseded) and nothing material
has changed since — while a genuine escalation, or a fresh event with no
prior surfaced instance, must still interrupt exactly as before.

Pure unit tests against `evaluate_event()`/`evaluate_batch()` — no
Supabase, no network, matching `test_attention_engine.py`'s own scope.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import (
    AttentionCategory,
    AttentionThresholds,
    evaluate_batch,
    evaluate_event,
)


def _event(**overrides) -> dict:
    event = {
        "event_id": "evt-recur-1",
        "event_type": "ori.source.degraded",
        "domain": "operational_resilience_intelligence",
        "source": "intelligence.scheduler",
        "importance": 90,
        "confidence": 85,
        "relevance": 80,
        "occurred_at": "2026-09-19T12:00:00+00:00",
        "status": "new",
    }
    event.update(overrides)
    return event


# ─── No recent_surfaced passed at all: identical to pre-Phase-4 behaviour ───


def test_no_recent_surfaced_behaves_exactly_as_before():
    decision = evaluate_event(_event())
    assert decision.category == AttentionCategory.INTERRUPT_NOW
    assert decision.duplicate_of_event_id is None


# ─── A repeated stable condition stops re-triggering ───────────────────────


def test_same_event_reevaluated_after_acknowledgement_stops_interrupting():
    """The common real case: `event_bus.poll_events()` has no `since`
    cursor, so the exact same already-dispatched row reappears on every
    10-minute evaluation cycle. Passing that same batch as its own
    `recent_surfaced` must stop it re-triggering INTERRUPT_NOW."""
    acknowledged = _event(status="acknowledged")
    decision = evaluate_event(acknowledged, recent_surfaced=[acknowledged])
    assert decision.category != AttentionCategory.INTERRUPT_NOW
    assert decision.category == AttentionCategory.CAN_BE_DELAYED
    assert decision.duplicate_of_event_id == "evt-recur-1"
    assert "recurrence" in decision.reason


def test_new_row_for_a_persisting_condition_matches_by_domain_and_event_type():
    """A domain that re-publishes a fresh row (new event_id) every cycle
    for the same still-true condition — matched by (domain, event_type),
    the only deterministic key `core_events` offers (no title column)."""
    prior = _event(
        event_id="evt-recur-0",
        status="acknowledged",
        occurred_at="2026-09-19T10:00:00+00:00",
    )
    current = _event(event_id="evt-recur-1", occurred_at="2026-09-19T10:30:00+00:00")

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.CAN_BE_DELAYED
    assert decision.duplicate_of_event_id == "evt-recur-0"


def test_batch_threads_recent_surfaced_through_to_every_event():
    acknowledged = _event(status="acknowledged")
    decisions = evaluate_batch([acknowledged], recent_surfaced=[acknowledged])
    assert decisions[0].category != AttentionCategory.INTERRUPT_NOW


# ─── A dismissed event shouldn't resurface unchanged ────────────────────────


def test_dismissed_unchanged_event_downgrades_to_remembered_not_delayed():
    """A Captain explicitly dismissing a condition is a stronger signal
    than a routine acknowledgement — it should stop being surfaced at all
    (SHOULD_SIMPLY_BE_REMEMBERED), not just de-escalate to CAN_BE_DELAYED."""
    prior = _event(status="dismissed", occurred_at="2026-09-19T10:00:00+00:00")
    current = _event(occurred_at="2026-09-19T10:15:00+00:00")

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED
    assert decision.duplicate_of_event_id == prior["event_id"]


def test_superseded_unchanged_event_also_downgrades():
    prior = _event(status="superseded")
    decision = evaluate_event(_event(), recent_surfaced=[prior])
    assert decision.category == AttentionCategory.CAN_BE_DELAYED


# ─── A genuinely escalating condition still surfaces ────────────────────────


def test_material_importance_increase_still_interrupts():
    prior = _event(status="acknowledged", importance=76, confidence=71)
    current = _event(importance=95, confidence=92)  # delta >= material_change_delta (15)

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.INTERRUPT_NOW
    assert decision.duplicate_of_event_id is None


def test_material_confidence_increase_alone_still_interrupts():
    prior = _event(status="acknowledged", importance=90, confidence=71)
    current = _event(importance=90, confidence=95)  # only confidence moved, but by >= delta

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.INTERRUPT_NOW


def test_sub_threshold_drift_still_downgrades():
    """A small wobble (< material_change_delta) is not a genuine change —
    still suppressed, same as an exact repeat."""
    prior = _event(status="acknowledged", importance=90, confidence=85)
    current = _event(importance=92, confidence=88)  # deltas of 2 and 3, both < 15

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category != AttentionCategory.INTERRUPT_NOW


def test_missing_prior_scores_never_silently_suppress():
    """If the matched prior row is missing importance/confidence (can't
    prove 'nothing changed'), the gate must not suppress — same 'absent is
    not defaulted' convention the base threshold cut already uses."""
    prior = _event(status="acknowledged", importance=None, confidence=None)
    decision = evaluate_event(_event(), recent_surfaced=[prior])
    assert decision.category == AttentionCategory.INTERRUPT_NOW


# ─── Not a recurrence: no suppression ───────────────────────────────────────


def test_no_prior_match_stays_interrupt_now():
    other_domain = _event(
        event_id="evt-other",
        domain="engineering_intelligence",
        status="acknowledged",
    )
    decision = evaluate_event(_event(), recent_surfaced=[other_domain])
    assert decision.category == AttentionCategory.INTERRUPT_NOW


def test_prior_still_new_status_does_not_suppress():
    """A prior row that is itself still 'new' (never acknowledged/
    dismissed/superseded) is not 'already surfaced' — no dedup basis."""
    prior = _event(event_id="evt-prior-new", status="new")
    decision = evaluate_event(_event(), recent_surfaced=[prior])
    assert decision.category == AttentionCategory.INTERRUPT_NOW


def test_only_applies_to_interrupt_now_not_other_categories():
    """The gate must never touch a decision that wasn't INTERRUPT_NOW in
    the first place — additional gating on top of the threshold cut, not
    a replacement for it."""
    prior = _event(status="acknowledged", importance=50, confidence=80)
    current = _event(importance=50, confidence=80)  # mid-range -> CAN_BE_DELAYED, not interrupt

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.CAN_BE_DELAYED
    assert decision.duplicate_of_event_id is None
    assert "recurrence" not in decision.reason


# ─── Recency window ──────────────────────────────────────────────────────


def test_stale_prior_outside_lookback_window_does_not_suppress():
    prior = _event(status="acknowledged", occurred_at="2026-09-10T12:00:00+00:00")
    current = _event(occurred_at="2026-09-19T12:00:00+00:00")  # 9 days later, default lookback is 24h

    decision = evaluate_event(current, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.INTERRUPT_NOW


def test_custom_lookback_widens_the_dedup_window():
    prior = _event(status="acknowledged", occurred_at="2026-09-10T12:00:00+00:00")
    current = _event(occurred_at="2026-09-19T12:00:00+00:00")
    wide_window = AttentionThresholds(recurrence_lookback_hours=24 * 30)

    decision = evaluate_event(current, thresholds=wide_window, recent_surfaced=[prior])
    assert decision.category != AttentionCategory.INTERRUPT_NOW


def test_custom_material_change_delta_is_respected():
    prior = _event(status="acknowledged", importance=90, confidence=85)
    current = _event(importance=95, confidence=85)  # delta of 5
    strict = AttentionThresholds(material_change_delta=3)

    decision = evaluate_event(current, thresholds=strict, recent_surfaced=[prior])
    assert decision.category == AttentionCategory.INTERRUPT_NOW  # 5 >= 3 -> material


def test_full_corpus_recurrence_gate_is_deterministic():
    """Running the same (event, recent_surfaced) pair twice must produce
    identical categorisation — same trustworthy-harness precondition
    `test_attention_engine.py::test_full_corpus_categorises_every_event_deterministically`
    already holds for the base engine."""
    prior = _event(status="dismissed")
    current = _event()

    first = evaluate_event(current, recent_surfaced=[prior])
    second = evaluate_event(current, recent_surfaced=[prior])
    assert first.category == second.category
    assert first.duplicate_of_event_id == second.duplicate_of_event_id
