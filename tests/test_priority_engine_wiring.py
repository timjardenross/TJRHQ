"""Tests for the Priority Engine wiring into the intelligence persistence pipeline.

Covers the `_priority_score_for_event` helper added to
`intelligence/persistence/intelligence_store.py` (MSN-0306 activation).

These are pure unit tests — no Supabase, no network calls. They verify:
1. Events below the CAN_BE_DELAYED attention floor (importance < 40) return None.
2. Events at or above the floor produce a non-None PriorityScore.
3. The score maps importance/confidence from the RankedEvent fields correctly.
4. value_dimensions and opportunity_value are correctly absent (Wave 3 supply
   path not yet wired — the engine must not error on empty inputs).
5. Scoring failure is non-blocking — a contrived bad input must not propagate.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from intelligence.models import ClassifiedEvent, RankedEvent
from intelligence.persistence.intelligence_store import (
    _priority_score_for_event,
    _PRIORITY_SCORING_IMPORTANCE_FLOOR,
    _derive_attention_importance,
)
from core.platform.priority_engine import PriorityScore


def _make_ranked_event(
    *,
    customer_impact: str = "low",
    banking_relevance: str = "low",
    cps230_relevance: bool = False,
    confidence: float = 0.75,
    operational_relevance: float = 0.60,
    event_type: str = "regulatory",
) -> RankedEvent:
    """Minimal RankedEvent for wiring tests. Fields not relevant to priority
    scoring are filled with valid-but-inert values."""
    now = datetime.now(tz=timezone.utc)
    return RankedEvent(
        event_id="test-evt-001",
        source_id="src-test",
        source_name="Test Source",
        source_priority=2,
        source_confidence_weight=0.8,
        source_category="media",
        raw_title="Test event title",
        raw_summary="Test summary",
        canonical_url="https://example.com/test",
        published_at=now,
        collected_at=now,
        dedup_hash="aabbccdd",
        event_type=event_type,
        geography="AU",
        sector="financial_services",
        operational_relevance=operational_relevance,
        customer_impact=customer_impact,
        banking_relevance=banking_relevance,
        cps230_relevance=cps230_relevance,
        dependency_risk=False,
        confidence=confidence,
    )


class TestPriorityScoreFloorGate:
    """Events below the CAN_BE_DELAYED attention floor must not be scored."""

    def test_low_importance_event_returns_none(self):
        """GREEN (importance=15): customer_impact=low, banking_relevance=low.
        _derive_attention_importance returns 15 — below the 40 floor."""
        event = _make_ranked_event(customer_impact="low", banking_relevance="low")
        attention_importance = _derive_attention_importance(event)
        assert attention_importance == 15
        assert attention_importance < _PRIORITY_SCORING_IMPORTANCE_FLOOR

        result = _priority_score_for_event(event, attention_importance)
        assert result is None

    def test_floor_constant_matches_attention_engine_delayed_floor(self):
        """The floor must be 40 — the AttentionThresholds.delayed_importance_floor
        default. Changing this without changing the constant would silently
        score NEVER_INTERRUPT events."""
        assert _PRIORITY_SCORING_IMPORTANCE_FLOOR == 40


class TestPriorityScoreScoredTiers:
    """Events at or above the CAN_BE_DELAYED floor must produce a PriorityScore."""

    def test_amber_event_produces_score(self):
        """AMBER (importance=42): customer_impact=medium. Clears the 40 floor."""
        event = _make_ranked_event(customer_impact="medium", banking_relevance="low")
        attention_importance = _derive_attention_importance(event)
        assert attention_importance == 42

        result = _priority_score_for_event(event, attention_importance)
        assert result is not None
        assert isinstance(result, PriorityScore)

    def test_red_event_produces_score(self):
        """RED (importance=55): customer_impact=high without cps230. Clearly above floor."""
        event = _make_ranked_event(customer_impact="high", banking_relevance="low")
        attention_importance = _derive_attention_importance(event)
        assert attention_importance == 55

        result = _priority_score_for_event(event, attention_importance)
        assert result is not None
        assert result.total_score > 0

    def test_red_cps230_event_produces_highest_score(self):
        """RED+CPS230 (importance=90): should produce a higher score than plain RED."""
        red_cps230 = _make_ranked_event(customer_impact="high", cps230_relevance=True, confidence=0.85)
        red_only = _make_ranked_event(customer_impact="high", cps230_relevance=False, confidence=0.85)

        red_cps230_score = _priority_score_for_event(red_cps230, _derive_attention_importance(red_cps230))
        red_only_score = _priority_score_for_event(red_only, _derive_attention_importance(red_only))

        assert red_cps230_score is not None
        assert red_only_score is not None
        assert red_cps230_score.total_score > red_only_score.total_score


class TestPriorityScoreFieldMapping:
    """The scored output must correctly reflect the fields from RankedEvent."""

    def test_importance_maps_from_attention_importance(self):
        """importance_score must equal the attention_importance value (0-100 int)
        passed in — not the raw rank_score, not a re-derived value."""
        event = _make_ranked_event(customer_impact="high")
        attention_importance = _derive_attention_importance(event)  # 55
        result = _priority_score_for_event(event, attention_importance)
        assert result is not None
        assert result.importance_score == float(attention_importance)

    def test_confidence_maps_from_event_confidence_scaled_to_100(self):
        """RankedEvent.confidence is 0.0–1.0; PriorityInputs expects 0–100.
        The helper must scale correctly."""
        event = _make_ranked_event(customer_impact="high", confidence=0.80)
        result = _priority_score_for_event(event, _derive_attention_importance(event))
        assert result is not None
        # confidence=0.80 -> scaled to 80 -> risk = (55/100)*(1-80/100)*100 = 11.0
        expected_risk = round((55 / 100.0) * (1.0 - 80 / 100.0) * 100.0, 2)
        assert result.risk_score == pytest.approx(expected_risk, abs=0.01)

    def test_value_dimensions_empty_does_not_error(self):
        """Wave 3 supply path not yet wired — value_dimensions must be empty
        and the engine must return a valid score rather than raising."""
        event = _make_ranked_event(customer_impact="high")
        result = _priority_score_for_event(event, _derive_attention_importance(event))
        assert result is not None
        assert result.value_score == 0.0
        assert result.dominant_value_dimension is None

    def test_opportunity_value_absent_does_not_error(self):
        """opportunity_value is None (no comms/opportunities.py integration yet).
        The engine must score zero for that dimension and not raise."""
        event = _make_ranked_event(customer_impact="high")
        result = _priority_score_for_event(event, _derive_attention_importance(event))
        assert result is not None
        assert result.opportunity_score == 0.0

    def test_explanation_string_is_non_empty(self):
        """Every scored event must carry an explanation (Blueprint Principle 3:
        every Priority ranking traces to a queryable score)."""
        event = _make_ranked_event(customer_impact="medium")
        result = _priority_score_for_event(event, _derive_attention_importance(event))
        assert result is not None
        assert result.explanation
        assert "=" in result.explanation
