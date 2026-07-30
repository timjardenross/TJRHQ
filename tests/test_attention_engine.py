"""MSN-0306 (Captain Intelligence Platform, Programme B): Attention Engine
test harness.

Exercises every branch of `core/platform/attention_engine.py`'s routing
table against the synthetic multi-domain corpus in
`tests/fixtures/synthetic_core_events.py`. Pure unit tests — no Supabase,
no network, no live system dependency, matching the module's own scope.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import (
    AttentionCategory,
    AttentionThresholds,
    evaluate_event,
    evaluate_batch,
)
from tests.fixtures.synthetic_core_events import (
    INTERRUPT_NOW_EVENT,
    NEVER_INTERRUPT_EVENT,
    CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT,
    CAN_BE_DELAYED_MIDRANGE_EVENT,
    REMEMBERED_EVENT,
    MISSING_SCORES_EVENT,
    AGGREGATION_GROUP,
    SUMMARISATION_PAIR,
    SUMMARISATION_EDGES,
    FULL_MULTI_DOMAIN_CORPUS,
)


def test_high_importance_high_confidence_interrupts_now():
    decision = evaluate_event(INTERRUPT_NOW_EVENT)
    assert decision.category == AttentionCategory.INTERRUPT_NOW
    assert decision.event_id == "evt-001"
    assert "importance" in decision.reason and "confidence" in decision.reason


def test_low_importance_never_interrupts():
    decision = evaluate_event(NEVER_INTERRUPT_EVENT)
    assert decision.category == AttentionCategory.NEVER_INTERRUPT


def test_high_importance_low_confidence_is_delayed_not_interrupt():
    """The single most important rule in MSN-0301's Cognitive Model: a
    high-importance-but-unverified signal must never interrupt."""
    decision = evaluate_event(CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT)
    assert decision.category == AttentionCategory.CAN_BE_DELAYED
    assert decision.category != AttentionCategory.INTERRUPT_NOW


def test_midrange_importance_is_delayed():
    decision = evaluate_event(CAN_BE_DELAYED_MIDRANGE_EVENT)
    assert decision.category == AttentionCategory.CAN_BE_DELAYED


def test_low_importance_is_remembered_not_surfaced():
    decision = evaluate_event(REMEMBERED_EVENT)
    assert decision.category == AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED


def test_missing_scores_treated_as_absent_not_defaulted():
    """An unscored event (nullable importance/confidence/relevance on the
    real core_events table) must resolve to the lowest-salience category,
    never silently behave as if it were scored."""
    decision = evaluate_event(MISSING_SCORES_EVENT)
    assert decision.category == AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED
    assert decision.importance is None
    assert decision.confidence is None


def test_three_same_domain_event_type_events_aggregate():
    decisions = evaluate_batch(AGGREGATION_GROUP)
    assert all(d.category == AttentionCategory.SHOULD_BE_AGGREGATED for d in decisions)
    assert all(d.aggregation_key == "operational_resilience_intelligence:ori.signal.ranked" for d in decisions)


def test_related_events_summarise_instead_of_aggregating():
    decisions = evaluate_batch(SUMMARISATION_PAIR, related_edges=SUMMARISATION_EDGES)
    assert all(d.category == AttentionCategory.SHOULD_BE_SUMMARISED for d in decisions)
    by_id = {d.event_id: d for d in decisions}
    assert by_id["evt-sum-1"].related_event_ids == ["evt-sum-2"]
    assert by_id["evt-sum-2"].related_event_ids == ["evt-sum-1"]


def test_interrupt_now_never_gets_reclassified_by_batch_grouping():
    """An interrupt-worthy event sharing a (domain, event_type) with 2+
    others must stay INTERRUPT_NOW, never get folded into an aggregate."""
    padded_batch = [INTERRUPT_NOW_EVENT] + [
        {**INTERRUPT_NOW_EVENT, "event_id": f"evt-pad-{i}", "importance": 25, "confidence": 50}
        for i in range(2)
    ]
    decisions = evaluate_batch(padded_batch)
    interrupt_decision = next(d for d in decisions if d.event_id == "evt-001")
    assert interrupt_decision.category == AttentionCategory.INTERRUPT_NOW


def test_full_corpus_categorises_every_event_deterministically():
    """Running the full synthetic corpus twice must produce identical
    categorisation — a precondition for treating this as a trustworthy
    evaluation harness."""
    first = evaluate_batch(FULL_MULTI_DOMAIN_CORPUS, related_edges=SUMMARISATION_EDGES)
    second = evaluate_batch(FULL_MULTI_DOMAIN_CORPUS, related_edges=SUMMARISATION_EDGES)
    assert [d.category for d in first] == [d.category for d in second]
    assert len(first) == len(FULL_MULTI_DOMAIN_CORPUS)


def test_custom_thresholds_change_routing():
    """Thresholds are explicitly tunable (Learning & Adaptation target,
    MSN-0301 Workstream F) — confirm changing them changes the outcome,
    proving the routing table isn't hardcoded past the dataclass."""
    strict = AttentionThresholds(interrupt_importance_floor=95, interrupt_confidence_floor=95)
    decision = evaluate_event(INTERRUPT_NOW_EVENT, thresholds=strict)
    assert decision.category != AttentionCategory.INTERRUPT_NOW
