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

from core.platform.attention_engine import AttentionCategory  # noqa: E402
from intelligence.validation_suite import (  # noqa: E402
    _case_aws_sydney_synthetic_replay,
    _case_bushfire_synthetic_replay,
    _fail,
    _pass,
    _replay_through_attention_engine,
    CASES,
    KNOWN_GAPS,
)


def _real_fortinet_row():
    """Real values captured live 2026-07-08 (event_id a2a930ce...) — pinned
    here so this test needs no live DB call, matching this suite's own
    non-goal of requiring 100% live access to prove its core mechanism."""
    return {
        "event_id": "a2a930ce-4555-41f0-b42b-9840b1eafc6e",
        "rank_score": 79.0959,
        "confidence": 0.86,
        "operational_relevance": 1.0,
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
    """Same idea, on the importance/rank_score side (e.g. a ranking-weight
    regression) — the other half of the INTERRUPT_NOW gate."""
    regressed = dict(_real_fortinet_row())
    regressed["rank_score"] = 30.0  # simulated regression: was 79.10

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
