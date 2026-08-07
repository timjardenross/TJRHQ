"""
Ranking engine — weighted composite score, 100% rule-based.

rank_score is a value 0–100 computed from:
  source_priority       0.25  (inverted: priority 1 = max score)
  operational_impact    0.20
  customer_impact       0.15
  banking_relevance     0.15
  cps230_relevance      0.10
  cross_source          0.10  (multi-source confirmation)
  geography_priority    0.05

Multiplied by:
  recency_decay factor (0–1.0 based on event age)
  source_reliability_score (SRS 0–1.0 from intelligence_source_registry)

Top events are determined by highest rank_score among non-suppressed events.
Sources with low SRS (TIER_4, unreliable) are de-emphasized automatically.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Optional

from intelligence.config import RANK_WEIGHTS, GEOGRAPHY_SCORES, IMPACT_SCORES, TOP_EVENTS_LIMIT
from intelligence.models import ClassifiedEvent, RankedEvent

log = logging.getLogger(__name__)

# SRS cache (source_id → reliability_score) — refreshed on each brief generation
_SRS_CACHE: dict[str, float] = {}


# Source priority → normalised score (5 = lowest priority = lowest score)
_PRIORITY_SCORES = {1: 1.0, 2: 0.80, 3: 0.55, 4: 0.30, 5: 0.10}

# Categories that publish general news — cap their final score so they don't
# outrank primary regulatory/cyber/infrastructure sources on keyword coincidences.
# Loosened 2026-07-04 (Captain: "extra articles fine if quality's good") — media
# sources already score low on source_priority (rank 4 -> 0.30, vs 1.0 for primary
# regulatory/cyber sources), so a media item's realistic ceiling pre-cap is ~72-73;
# 80 lets well-corroborated, high-impact media stories compete for top-events
# placement instead of being flattened to the same ~55, while still sitting below
# genuine critical regulatory/cyber alerts (which routinely score 85-100).
_MEDIA_CATEGORIES = {"media"}
_MEDIA_SCORE_CAP = 80.0  # out of 100


def _load_srs_scores():
    """Load source reliability scores from database into cache."""
    global _SRS_CACHE
    try:
        from intelligence.persistence import intelligence_store as store
        scores = store.get_source_reliability_scores()
        _SRS_CACHE = {s["source_id"]: s["reliability_score"] for s in scores}
        log.debug(f"Loaded SRS scores for {len(_SRS_CACHE)} sources")
    except Exception as e:
        log.warning(f"Failed to load SRS scores (will use default 0.75): {e}")
        _SRS_CACHE = {}


def _get_source_reliability_score(source_id: str) -> float:
    """Get SRS for a source, defaulting to 0.75 (TIER_4 equivalent) if unknown."""
    if not _SRS_CACHE:
        _load_srs_scores()
    return _SRS_CACHE.get(source_id, 0.75)


def _recency_decay(collected_at: Optional[datetime]) -> float:
    if not collected_at:
        return 0.50
    now = datetime.now(timezone.utc)
    delta = now - collected_at.replace(tzinfo=timezone.utc) if collected_at.tzinfo is None else now - collected_at
    days = delta.total_seconds() / 86400
    if days <= 0:
        return 1.0
    if days <= 7:
        return max(0.35, 1.0 - (days / 7) * 0.35)
    if days <= 14:
        return max(0.10, 0.65 - ((days - 7) / 7) * 0.35)
    return 0.10


def _cross_source_bonus(event: ClassifiedEvent, all_events: list[ClassifiedEvent]) -> float:
    """
    Simple cross-source confirmation: how many other sources have a similar title?
    Returns 0.0–1.0 proportional to confirmation count.
    """
    import re
    words = set(re.findall(r"\w{4,}", event.raw_title.lower()))
    if not words:
        return 0.0

    confirmed = 0
    for other in all_events:
        if other.event_id == event.event_id:
            continue
        if other.source_id == event.source_id:
            continue
        other_words = set(re.findall(r"\w{4,}", other.raw_title.lower()))
        overlap = len(words & other_words)
        if overlap >= 2:
            confirmed += 1

    return min(1.0, confirmed * 0.33)


def rank(
    events: list[ClassifiedEvent],
    period_start: Optional[datetime] = None,
) -> list[RankedEvent]:
    """
    Compute rank_score for every non-suppressed event.
    Applies Source Reliability Scoring (SRS) as a multiplier.
    Returns list of RankedEvent sorted by rank_score descending.
    Suppressed events are included at rank_score = 0.0 for audit trail.
    """
    # Load SRS scores from database (cached for this brief generation)
    _load_srs_scores()

    ranked: list[RankedEvent] = []

    active = [e for e in events if not e.suppressed]

    for event in events:
        if event.suppressed:
            ranked.append(RankedEvent(**event.__dict__, rank_score=0.0))
            continue

        w = RANK_WEIGHTS

        source_score    = _PRIORITY_SCORES.get(event.source_priority, 0.10)
        op_score        = event.operational_relevance
        cust_score      = IMPACT_SCORES.get(event.customer_impact, 0.10)
        bank_score      = IMPACT_SCORES.get(event.banking_relevance, 0.10)
        cps230_score    = 1.0 if event.cps230_relevance else 0.0
        cross_score     = _cross_source_bonus(event, active)
        geo_score       = GEOGRAPHY_SCORES.get(event.geography, 0.25)

        raw_score = (
            source_score  * w["source_priority"]    +
            op_score      * w["operational_impact"] +
            cust_score    * w["customer_impact"]    +
            bank_score    * w["banking_relevance"]  +
            cps230_score  * w["cps230_relevance"]   +
            cross_score   * w["cross_source"]       +
            geo_score     * w["geography_priority"]
        )

        decay = _recency_decay(event.collected_at)

        # Apply Source Reliability Score (SRS) multiplier
        srs = _get_source_reliability_score(event.source_id)
        final_score = round(raw_score * decay * srs * 100, 4)

        # Cap media/general news sources so keyword coincidences don't outrank
        # primary regulatory, cyber, or infrastructure events
        if event.source_category in _MEDIA_CATEGORIES:
            final_score = min(final_score, _MEDIA_SCORE_CAP)

        ranked.append(RankedEvent(**event.__dict__, rank_score=final_score))

    ranked.sort(key=lambda e: e.rank_score, reverse=True)
    return ranked


def top_events(ranked: list[RankedEvent], limit: int = TOP_EVENTS_LIMIT) -> list[RankedEvent]:
    """Return the top N non-suppressed events by rank_score."""
    return [e for e in ranked if not e.suppressed][:limit]
