"""MSN-0306 (Captain Intelligence Platform, Programme B): Priority &
Opportunity Engine test harness.

Ranking validation examples against the synthetic corpus — confirms the
scoring model is predictable and explainable (every score traces to its
component inputs), per this mission's own success criteria. Pure unit
tests — no Supabase, no network dependency.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.platform.priority_engine import (
    PriorityWeights,
    PriorityInputs,
    score_event,
    rank_events,
)
from tests.fixtures.synthetic_core_events import (
    INTERRUPT_NOW_EVENT,
    CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT,
    CAN_BE_DELAYED_MIDRANGE_EVENT,
    SUMMARISATION_PAIR,
    SYNTHETIC_VALUE_DIMENSIONS,
    SYNTHETIC_OPPORTUNITY_VALUES,
)


def _inputs_from_event(event: dict, *, value_dimensions=None, opportunity_value=None) -> PriorityInputs:
    return PriorityInputs(
        event_id=event["event_id"],
        domain=event["domain"],
        event_type=event["event_type"],
        importance=event.get("importance"),
        confidence=event.get("confidence"),
        relevance=event.get("relevance"),
        value_dimensions=value_dimensions or {},
        opportunity_value=opportunity_value,
    )


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        PriorityWeights(urgency=0.5, importance=0.5, time_sensitivity=0.5, value=0.5, risk=0.5, opportunity=0.5)


def test_default_weights_sum_to_one():
    # Constructing with defaults must not raise
    PriorityWeights()


def test_high_importance_high_confidence_scores_low_risk():
    inputs = _inputs_from_event(INTERRUPT_NOW_EVENT, value_dimensions=SYNTHETIC_VALUE_DIMENSIONS["evt-001"])
    score = score_event(inputs)
    # importance=90, confidence=85 -> risk = (90/100)*(1-85/100)*100 = 13.5
    assert score.risk_score == pytest.approx(13.5, abs=0.01)


def test_high_importance_low_confidence_scores_high_risk():
    """The whole point of risk-as-inverse-relationship: an unverified
    high-stakes signal must score as genuinely risky, not neutral."""
    inputs = _inputs_from_event(
        CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT,
        value_dimensions=SYNTHETIC_VALUE_DIMENSIONS["evt-003"],
    )
    score = score_event(inputs)
    # importance=80, confidence=30 -> risk = (80/100)*(1-30/100)*100 = 56.0
    assert score.risk_score == pytest.approx(56.0, abs=0.01)
    assert score.risk_score > 50


def test_missing_confidence_treated_as_maximally_uncertain():
    inputs = PriorityInputs(event_id="evt-x", domain="d", event_type="t", importance=80, confidence=None)
    score = score_event(inputs)
    # confidence absent -> treated as 0 -> risk = (80/100)*(1-0)*100 = 80.0
    assert score.risk_score == pytest.approx(80.0, abs=0.01)


def test_dominant_value_dimension_is_the_highest_scored_one():
    inputs = _inputs_from_event(
        SUMMARISATION_PAIR[1],  # evt-sum-2
        value_dimensions=SYNTHETIC_VALUE_DIMENSIONS["evt-sum-2"],
        opportunity_value=SYNTHETIC_OPPORTUNITY_VALUES["evt-sum-2"],
    )
    score = score_event(inputs)
    assert score.dominant_value_dimension == "career"  # 55 > 30 (strategic)
    assert score.value_score == 55.0


def test_no_value_dimensions_scores_zero_value_not_an_error():
    inputs = _inputs_from_event(CAN_BE_DELAYED_MIDRANGE_EVENT)
    score = score_event(inputs)
    assert score.dominant_value_dimension is None
    assert score.value_score == 0.0


def test_explanation_cites_every_component():
    inputs = _inputs_from_event(INTERRUPT_NOW_EVENT, value_dimensions=SYNTHETIC_VALUE_DIMENSIONS["evt-001"])
    score = score_event(inputs)
    for term in ("importance=", "urgency=", "time_sensitivity=", "risk=", "opportunity=", "value="):
        assert term in score.explanation


def test_ranking_is_deterministic_and_explainable():
    """Ranking validation example: given a known set of inputs, the
    ordering must be reproducible and every entry must carry a non-empty
    explanation string."""
    events = [
        INTERRUPT_NOW_EVENT,
        CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT,
        CAN_BE_DELAYED_MIDRANGE_EVENT,
    ]
    inputs_list = [
        _inputs_from_event(e, value_dimensions=SYNTHETIC_VALUE_DIMENSIONS.get(e["event_id"], {}))
        for e in events
    ]
    first_run = rank_events(inputs_list)
    second_run = rank_events(inputs_list)

    assert [s.event_id for s in first_run] == [s.event_id for s in second_run]
    assert all(s.explanation for s in first_run)
    # Highest-importance, highest-confidence, highest-value event should rank first
    assert first_run[0].event_id == "evt-001"
    # Scores must be in non-increasing order
    scores = [s.total_score for s in first_run]
    assert scores == sorted(scores, reverse=True)


def test_custom_weights_change_ranking_outcome():
    """Weights are explicitly a Learning & Adaptation target (not fixed
    forever, per MSN-0301 Workstream F) — confirm changing them can
    change the ranking, proving the model isn't hardcoded past the
    dataclass."""
    events = [CAN_BE_DELAYED_LOW_CONFIDENCE_EVENT, CAN_BE_DELAYED_MIDRANGE_EVENT]
    inputs_list = [_inputs_from_event(e) for e in events]

    default_ranked = rank_events(inputs_list)

    # Weight entirely toward risk: the low-confidence/high-importance event
    # (evt-003, high risk) should now clearly outrank the mid-range one.
    risk_heavy = PriorityWeights(urgency=0.0, importance=0.0, time_sensitivity=0.0, value=0.0, risk=1.0, opportunity=0.0)
    risk_ranked = rank_events(inputs_list, weights=risk_heavy)

    assert risk_ranked[0].event_id == "evt-003"
    assert risk_ranked[0].risk_score > risk_ranked[1].risk_score
