"""USS-TJR-MSN-0339 WP5: Operational Intelligence Validation Suite tests.

Two things this proves:
1. The suite's stage-6 mechanism (`_replay_through_attention_engine`, used
   by every real case) is genuinely sensitive to regression — the design
   doc's own execution gate ("a deliberately reintroduced regression is
   caught"), demonstrated here as a pure-function check with no live
   writes: take a real row shape, mutate it to simulate a regression, and
   confirm the same logic every case uses would now correctly fail.
2. The synthetic replay cases (`_case_bushfire_synthetic_replay`,
   `_case_aws_sydney_synthetic_replay`) produce a stable classification
   without any DB access — pinning them against classifier drift.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import AttentionCategory
from intelligence.validation_suite import (
    CASES,
    KNOWN_GAPS,
    _case_aws_sydney_synthetic_replay,
    _case_bushfire_synthetic_replay,
    _fail,
    _pass,
    _replay_through_attention_engine,
)


def _real_fortinet_row():
    """Real values captured live 2026-07-08 (event_id a2a930ce...) — pinned
    here so this test needs no live DB call, matching this suite's own
    non-goal of requiring 100% live access to prove its core mechanism.

    rank_score=79.0959 is the value as originally captured 2026-07-08 —
    kept as the historical record even though rank_score decays over time
    (recency_decay/SRS) and re-querying this same event_id later shows a
    much lower current value; it's irrelevant to classification anyway
    since the 2026-08-22/23 fix (see _row_importance's docstring).
    customer_impact/banking_relevance/cps230_relevance were re-queried
    live to backfill this fixture — they don't decay, and _row_importance
    now reads these instead of rank_score, so the fixture was silently
    falling through to the lowest importance tier without them."""
    return {
        "event_id": "a2a930ce-4555-41f0-b42b-9840b1eafc6e",
        "rank_score": 79.0959,
        "confidence": 0.86,
        "operational_relevance": 1.0,
        "customer_impact": "high",
        "banking_relevance": "medium",
        "cps230_relevance": True,
    }


def test_real_fortinet_shape_replays_to_interrupt_now():
    decision = _replay_through_attention_engine(_real_fortinet_row())
    assert decision.category == AttentionCategory.INTERRUPT_NOW


def test_deliberately_reintroduced_confidence_regression_is_caught():
    """Simulates a regression that under-scores confidence (e.g. a
    classifier weight bug) on the exact real Fortinet-shaped row — proves
    the same stage-6 mechanism every real case relies on would flag it,
    satisfying the design doc's own 'deliberately reintroduced regression
    is caught' execution gate without touching any live system."""
    regressed = dict(_real_fortinet_row())
    regressed["confidence"] = 0.40  # simulated regression: was 0.86

    decision = _replay_through_attention_engine(regressed)

    assert decision.category != AttentionCategory.INTERRUPT_NOW, (
        "regression was NOT caught — a confidence-scoring bug would silently "
        "ship an event that should interrupt as one that no longer does"
    )


def test_deliberately_reintroduced_importance_regression_is_caught():
    """Same idea, on the importance side (e.g. a severity-tiering
    regression) — the other half of the INTERRUPT_NOW gate.

    _row_importance() stopped reading rank_score as of the 2026-08-22/23
    fix (see its own docstring / _real_fortinet_row's) — it now derives
    importance from customer_impact/banking_relevance/cps230_relevance.
    Mutating rank_score here no longer simulates anything; downgrading
    customer_impact is what a real severity-tiering regression would
    actually look like now."""
    regressed = dict(_real_fortinet_row())
    regressed["customer_impact"] = "low"  # simulated regression: was "high"
    regressed["cps230_relevance"] = False  # simulated regression: was True

    decision = _replay_through_attention_engine(regressed)

    assert decision.category != AttentionCategory.INTERRUPT_NOW


def test_bushfire_synthetic_replay_is_stable_and_passes():
    result = _case_bushfire_synthetic_replay()
    assert result.passed, result.detail
    assert result.evidence["event_type"] == "severe_weather"


def test_aws_synthetic_replay_is_stable_and_passes():
    result = _case_aws_sydney_synthetic_replay()
    assert result.passed, result.detail
    assert result.evidence["event_type"] == "technology_outage"


def test_all_cases_registered_and_named_uniquely():
    names = [c.__name__ for c in CASES]
    assert len(names) == len(set(names))
    assert len(CASES) == 8


def test_known_gaps_is_non_empty_and_not_silently_hidden():
    # Design doc §5: coverage gaps must be named, never silently absent.
    assert len(KNOWN_GAPS) >= 2


def test_fail_and_pass_helpers_set_expected_fields():
    f = _fail("x", "real", "collectible", "no row")
    assert not f.passed and f.stage_reached == "collectible"
    p = _pass("x", "real", "ok")
    assert p.passed and p.stage_reached == "reaches_right_destination"
