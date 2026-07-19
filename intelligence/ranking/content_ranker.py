"""
Content ranker — composite score for content intelligence signals.

Weights are oriented to content strategy, not operational risk:
  pillar_fit           0.30  (how strongly the event matches a content pillar)
  strategic_alignment  0.25  (captain_focus flag + source quality)
  recency              0.20  (type-parameterised decay — see USEFUL_LIFE_DAYS)
  cross_source         0.15  (multi-source confirmation from existing rank_score)
  source_quality       0.10  (source confidence_weight from registry)

Recency decay is parameterised by source type:
  linkedin_post    3d — social content expires fast
  industry_report  60d
  research_paper   180d
  hbr_article      365d — long-form analysis stays relevant
  default          14d

Does NOT modify the ORI ranker in ranker.py.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from intelligence.classification.content_classifier import ContentScore


# ── Source type useful-life lookup ────────────────────────────────────────────
# Maps source_type_label (from intelligence_source_registry) to days.
USEFUL_LIFE_DAYS: dict[str, int] = {
    "linkedin_post":    3,
    "industry_report":  60,
    "research_paper":   180,
    "hbr_article":      365,
    "default":          14,
}

_WEIGHTS = {
    "pillar_fit":           0.30,
    "strategic_alignment":  0.25,
    "recency":              0.20,
    "cross_source":         0.15,
    "source_quality":       0.10,
}

assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


def _type_adjusted_decay(collected_at_iso: str, useful_life_days: int) -> float:
    """
    Recency decay parameterised by source type useful life.

    Signal is at full value (1.0) while within the useful life window.
    After useful_life_days, decays to ~0.10 over an equal additional window.
    """
    if not collected_at_iso:
        return 0.50
    try:
        if collected_at_iso.endswith("Z"):
            collected_at_iso = collected_at_iso[:-1] + "+00:00"
        collected = datetime.fromisoformat(collected_at_iso)
        if collected.tzinfo is None:
            collected = collected.replace(tzinfo=timezone.utc)
        days_old = (datetime.now(timezone.utc) - collected).total_seconds() / 86400
    except Exception:
        return 0.50

    if useful_life_days <= 0:
        useful_life_days = 14

    if days_old <= 0:
        return 1.0
    if days_old <= useful_life_days:
        # Still within useful life — gentle linear decay from 1.0 to 0.75
        return max(0.75, 1.0 - (days_old / useful_life_days) * 0.25)
    # Beyond useful life — steeper decay, floor at 0.10
    overflow = days_old - useful_life_days
    return max(0.10, 0.75 - (overflow / useful_life_days) * 0.65)


def rank(
    score: ContentScore,
    cross_source_confirmation: float = 0.0,
) -> float:
    """
    Compute a composite content rank score (0–100).

    Args:
        score: output of content_classifier.score_for_content()
        cross_source_confirmation: 0.0–1.0, from ORI ranker's cross_source_bonus
            or derived from existing rank_score on the intelligence_events row

    Returns:
        float rank_score 0–100
    """
    # Pillar fit: content_relevance already encodes pillar match strength
    pillar_fit = min(1.0, score.content_relevance)

    # Strategic alignment: captain_focus flag + source quality
    strategic = (0.6 if score.captain_focus else 0.2) + min(0.4, score.content_relevance * 0.4)

    # Recency: type-parameterised decay
    recency = _type_adjusted_decay(score.collected_at, score.useful_life_days)

    # Cross-source: passed in from intelligence_events.rank_score (proxy)
    cross = min(1.0, cross_source_confirmation)

    # Source quality: from content_relevance boost component (already includes src_weight)
    quality = min(1.0, score.content_relevance)

    raw = (
        pillar_fit   * _WEIGHTS["pillar_fit"]           +
        strategic    * _WEIGHTS["strategic_alignment"]  +
        recency      * _WEIGHTS["recency"]              +
        cross        * _WEIGHTS["cross_source"]         +
        quality      * _WEIGHTS["source_quality"]
    )

    return round(raw * 100, 4)


def rank_batch(
    scores: list[ContentScore],
    event_rank_scores: Optional[dict[str, float]] = None,
) -> list[tuple[ContentScore, float]]:
    """
    Rank a batch of ContentScore objects.

    Args:
        scores: list of ContentScore from content_classifier
        event_rank_scores: optional dict {event_id_text: ori_rank_score} for
            cross-source confirmation proxy

    Returns:
        list of (ContentScore, rank_score) sorted descending by rank_score
    """
    event_rank_scores = event_rank_scores or {}
    results: list[tuple[ContentScore, float]] = []

    for s in scores:
        ori_score = event_rank_scores.get(s.event_id_text, 0.0)
        cross_proxy = min(1.0, ori_score / 100.0)
        rs = rank(s, cross_source_confirmation=cross_proxy)
        results.append((s, rs))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
