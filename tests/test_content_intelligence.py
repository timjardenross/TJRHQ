#!/usr/bin/env python3
"""
Unit tests for Content Intelligence (USS-TJR-MSN-0202).

Tests are pure (no network, no DB). Target: <50ms suite.
All functions under test are deterministic.
"""

import sys
import os
import time
from typing import Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone, timedelta
from intelligence.classification.content_classifier import score_for_content, _derive_angle
from intelligence.ranking.content_ranker import (
    rank, rank_batch, _type_adjusted_decay, USEFUL_LIFE_DAYS
)
from intelligence.classification.content_classifier import ContentScore


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _event(
    title: str = "AI augments leadership in financial services",
    summary: str = "",
    event_type: str = "regulatory",
    rank_score: float = 55.0,
    source_confidence_weight: float = 0.8,
    operational_relevance: float = 0.6,
    collected_at: Optional[str] = None,
    event_id: str = "test-event-001",
    source_id: str = "src-001",
    source_name: str = "Test Source",
) -> dict:
    if collected_at is None:
        collected_at = datetime.now(timezone.utc).isoformat()
    return {
        "event_id": event_id,
        "source_id": source_id,
        "source_name": source_name,
        "raw_title": title,
        "raw_summary": summary,
        "event_type": event_type,
        "rank_score": rank_score,
        "source_confidence_weight": source_confidence_weight,
        "operational_relevance": operational_relevance,
        "collected_at": collected_at,
        "canonical_url": "https://example.com/article",
    }


def _score(
    pillar_key: str = "ai_augmented_leadership",
    content_relevance: float = 0.70,
    captain_focus: bool = True,
    collected_at: Optional[str] = None,
    useful_life_days: int = 14,
) -> ContentScore:
    if collected_at is None:
        collected_at = datetime.now(timezone.utc).isoformat()
    return ContentScore(
        event_id_text="test-001",
        source_name="Test Source",
        pillar_key=pillar_key,
        pillar_name="AI-Augmented Leadership",
        content_relevance=content_relevance,
        captain_focus=captain_focus,
        suggested_angle="AI leadership: the accountability angle",
        raw_title="AI augments leadership",
        raw_summary=None,
        canonical_url="https://example.com",
        collected_at=collected_at,
        useful_life_days=useful_life_days,
    )


# ── content_classifier tests ──────────────────────────────────────────────────

class TestContentClassifier:

    def test_strong_pillar_match_returns_score(self):
        ev = _event(
            title="AI augments leadership and decision-making for executives",
            summary="Leaders adopting AI must maintain accountability for judgement.",
        )
        result = score_for_content(ev)
        assert result is not None
        # Text hits both ai_augmented_leadership and decision_quality_governance keywords;
        # either is a valid classification. Just confirm a pillar was assigned.
        assert result.pillar_key in (
            "ai_augmented_leadership", "decision_quality_governance"
        )
        assert result.content_relevance > 0.0

    def test_operational_resilience_match(self):
        ev = _event(title="Operational resilience outage recovery incident at major bank")
        result = score_for_content(ev)
        assert result is not None
        assert result.pillar_key == "operational_resilience"

    def test_business_continuity_match(self):
        ev = _event(title="CPS 230 compliance continuity BCP requirement for banks")
        result = score_for_content(ev)
        assert result is not None
        assert result.pillar_key == "business_continuity"

    def test_captain_focus_detected(self):
        ev = _event(title="Operational resilience and AI-augmented governance for leaders")
        result = score_for_content(ev, active_mission_keywords=["governance"])
        assert result is not None
        assert result.captain_focus is True

    def test_captain_focus_false_without_keywords(self):
        ev = _event(title="Shipping container port delays in Southeast Asia logistics")
        result = score_for_content(ev, active_mission_keywords=[])
        # May or may not match — just verify the field exists and is bool
        if result is not None:
            assert isinstance(result.captain_focus, bool)

    def test_suggested_angle_is_non_empty(self):
        ev = _event(title="AI agent automation augmented leadership copilot model")
        result = score_for_content(ev)
        assert result is not None
        assert len(result.suggested_angle) > 10

    def test_low_relevance_event_returns_none_or_low(self):
        ev = _event(
            title="Shipping container port delays in Southeast Asia",
            summary="",
            rank_score=5.0,
            source_confidence_weight=0.3,
            operational_relevance=0.1,
        )
        result = score_for_content(ev)
        # Either filtered out or low relevance
        if result is not None:
            assert result.content_relevance < 0.50

    def test_useful_life_days_passed_through(self):
        ev = _event(title="HBR article on decision quality and governance")
        result = score_for_content(ev, useful_life_days=365)
        assert result is not None
        assert result.useful_life_days == 365

    def test_idempotent_on_same_event(self):
        ev = _event(title="AI leadership decision quality governance")
        r1 = score_for_content(ev)
        r2 = score_for_content(ev)
        assert (r1 is None) == (r2 is None)
        if r1 and r2:
            assert r1.pillar_key == r2.pillar_key
            assert r1.content_relevance == r2.content_relevance


# ── content_ranker tests ──────────────────────────────────────────────────────

class TestContentRanker:

    def test_recent_event_scores_higher_than_old(self):
        fresh = _score(collected_at=datetime.now(timezone.utc).isoformat())
        stale_dt = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        stale = _score(collected_at=stale_dt)

        fresh_score = rank(fresh)
        stale_score = rank(stale)
        assert fresh_score > stale_score

    def test_captain_focus_boosts_score(self):
        focused     = _score(captain_focus=True)
        unfocused   = _score(captain_focus=False)
        assert rank(focused) > rank(unfocused)

    def test_score_in_valid_range(self):
        s = _score()
        r = rank(s)
        assert 0.0 <= r <= 100.0

    def test_cross_source_bonus_raises_score(self):
        base = rank(_score(), cross_source_confirmation=0.0)
        with_cross = rank(_score(), cross_source_confirmation=1.0)
        assert with_cross > base

    def test_hbr_article_decays_slower_than_linkedin_post(self):
        # Both 10 days old
        old_dt = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        hbr_decay  = _type_adjusted_decay(old_dt, useful_life_days=365)
        li_decay   = _type_adjusted_decay(old_dt, useful_life_days=3)
        assert hbr_decay > li_decay, (
            f"HBR decay {hbr_decay:.3f} should exceed LinkedIn decay {li_decay:.3f} at 10 days"
        )

    def test_research_paper_decays_slower_than_linkedin(self):
        old_dt = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        research_decay = _type_adjusted_decay(old_dt, useful_life_days=180)
        li_decay       = _type_adjusted_decay(old_dt, useful_life_days=3)
        assert research_decay > li_decay

    def test_useful_life_days_table_covers_all_types(self):
        for label in ["linkedin_post", "industry_report", "research_paper", "hbr_article", "default"]:
            assert label in USEFUL_LIFE_DAYS
            assert USEFUL_LIFE_DAYS[label] > 0

    def test_rank_batch_sorted_descending(self):
        scores = [
            _score(content_relevance=0.30, captain_focus=False),
            _score(content_relevance=0.80, captain_focus=True),
            _score(content_relevance=0.55, captain_focus=True),
        ]
        # Give each a distinct event_id
        for i, s in enumerate(scores):
            s = ContentScore(**{**s.__dict__, "event_id_text": f"evt-{i}"})
            scores[i] = s

        ranked = rank_batch(scores)
        assert len(ranked) == 3
        rs = [r for _, r in ranked]
        assert rs == sorted(rs, reverse=True), "rank_batch output must be sorted descending"

    def test_decay_floor_is_010(self):
        very_old = (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat()
        decay = _type_adjusted_decay(very_old, useful_life_days=14)
        assert decay >= 0.10

    def test_decay_ceiling_is_100_for_fresh_event(self):
        fresh = datetime.now(timezone.utc).isoformat()
        decay = _type_adjusted_decay(fresh, useful_life_days=14)
        assert decay <= 1.0
        assert decay >= 0.99


# ── Performance guard ─────────────────────────────────────────────────────────

def test_suite_performance():
    """Full pure-function pass must complete in under 200ms."""
    start = time.perf_counter()

    events = [
        _event(title=t) for t in [
            "AI augments leadership and decision quality",
            "CPS 230 operational resilience business continuity",
            "Human performance capacity burnout recovery",
            "Future of work remote productivity automation",
            "Wellness sleep recovery sustainable performance",
        ]
    ]
    scores = [score_for_content(e) for e in events]
    scores = [s for s in scores if s is not None]
    ranked = rank_batch(scores)

    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, f"Suite took {elapsed_ms:.1f}ms — must be under 200ms"
    assert len(ranked) > 0


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    suites = [TestContentClassifier(), TestContentRanker()]
    passed = failed = 0

    for suite in suites:
        for name in [m for m in dir(suite) if m.startswith("test_")]:
            try:
                getattr(suite, name)()
                print(f"  ✓ {type(suite).__name__}.{name}")
                passed += 1
            except Exception as exc:
                print(f"  ✗ {type(suite).__name__}.{name}: {exc}")
                traceback.print_exc()
                failed += 1

    try:
        test_suite_performance()
        print(f"  ✓ test_suite_performance")
        passed += 1
    except Exception as exc:
        print(f"  ✗ test_suite_performance: {exc}")
        failed += 1

    print(f"\n{passed + failed} tests — {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
