"""
Technical OSINT relevance gate — OSINT Ingestion Quality & Relevance
Mission, Phase 4 (mission_relevance) + Phase 6 (novelty).

Deterministic only, no LLM call — mission §25's staged-filtering
principle (cheap deterministic pass first) plus the Phase 1 audit finding
that this pipeline's shadow-mode/selective-augmentation LLM machinery
(intelligence/ingestion/selective_augmentation.py, Issue 16) already
exists for a DIFFERENT axis (risk/relevance_score, 0-100 composite) and
was, until the companion 2026-09-05 fix, silently never reaching the DB.
Routing THIS gate's ambiguous band to an LLM call is a natural Phase 11
follow-on once real shadow-mode data (now unblocked) shows whether the
deterministic scoring below actually produces an ambiguous band worth
spending an LLM call on — not built here to avoid repeating the same
"ship an LLM path with no data to validate it" mistake twice.

Layering (runs AFTER intelligence/classification/filter.py::should_suppress,
never before — it reads that outcome rather than re-deciding it):

  1. should_suppress()==True  -> mission_relevance = NOT_RELEVANT.
     This is mission §7's distinction: NOT_RELEVANT is a different concept
     from LOW confidence_level, even though today's `suppressed` bool
     conflates "not relevant" with "certainly wrong" — this module doesn't
     change that bool, only adds an inspectable label alongside it.
  2. should_suppress()==False -> compute a proximity/category match
     strength against config/osint_intelligence_missions.json and label
     RELEVANT or LOW_CONFIDENCE. A survivor of should_suppress is not
     automatically a strong relevance match — should_suppress's floor
     (_MIN_OP_RELEVANCE = 0.20) is deliberately permissive so world-news
     content isn't over-filtered (2026-08-22 fix, see filter.py); this
     gate adds the finer-grained label should_suppress was never designed
     to produce.

Novelty (Phase 6) is derived here only from the suppression_reason
string — NOT from cluster membership. Cluster-derived novelty (a
canonical vs. a fuzzy-dedup DUPLICATE member) is set separately in
intelligence/ingestion/phase_a_enrichment.py, which already knows cluster
membership at the point it calls this module; this function only fills
in the values phase_a_enrichment.py can't derive from clustering alone.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from intelligence.classification.filter import should_suppress
from intelligence.models import ClassifiedEvent

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "osint_intelligence_missions.json"

# Below this combined-strength score, a should_suppress survivor is labelled
# LOW_CONFIDENCE rather than RELEVANT. Provisional — same caveat as
# selective_augmentation.py's AMBIGUOUS_LOW/HIGH: unvalidated against real
# shadow-mode/eval-set data, expected to move during Phase 11 tuning.
_RELEVANT_STRENGTH_FLOOR = 0.35

_PROXIMITY_GEOGRAPHY_MAP = {
    "AU": "AU",
    "NZ": "NZ",
}

_NOVELTY_FROM_SUPPRESSION_REASON = {
    "opinion_or_commentary": "COMMENTARY",
    "routine_statistics_publication": "BACKGROUND",
    "speech_no_or_relevance": "BACKGROUND",
    "status_page_scheduled_maintenance": "BACKGROUND",
    "status_page_datacenter_maintenance_window": "BACKGROUND",
}


def _load_config() -> Optional[dict]:
    try:
        return json.loads(_CONFIG_PATH.read_text())["technical"]
    except Exception:
        logger.exception("Failed to load technical mission config from %s", _CONFIG_PATH)
        return None


_CONFIG = _load_config()


def _category_match(text: str, config: dict) -> Optional[dict]:
    """Best-matching priority_category by keyword hit count. Returns None
    if no category has any keyword hit — that's a real signal (mission §5's
    mission statement is a closed list of named priority areas, not
    "anything vaguely technology-related")."""
    best = None
    best_hits = 0
    for category in config.get("priority_categories", []):
        hits = sum(1 for kw in category.get("keywords", []) if kw.lower() in text)
        if hits > best_hits:
            best_hits = hits
            best = category
    return best


def _proximity_tier(event: ClassifiedEvent, text: str, config: dict) -> dict:
    """Match event.geography to a proximity tier, falling back to
    GLOBAL_LOCAL (weight 0.05, the lowest tier) if geography is unset/
    unrecognised — an unknown-geography item shouldn't default to full
    AU weight."""
    tiers = {t["tier"]: t for t in config.get("proximity_tiers", [])}
    geo = _PROXIMITY_GEOGRAPHY_MAP.get(getattr(event, "geography", None) or "")
    if geo and geo in tiers:
        return tiers[geo]
    # APAC/GLOBAL_SYSTEMIC aren't ClassifiedEvent.geography values today
    # (that field is AU/NZ/other per classifier.py) — a non-AU/NZ event
    # only reaches GLOBAL_SYSTEMIC tier via an explicit systemic-value
    # keyword hit, otherwise it's GLOBAL_LOCAL.
    systemic_kw = config.get("systemic_value_override", {}).get("keywords", [])
    if any(kw.lower() in text for kw in systemic_kw):
        return tiers.get("GLOBAL_SYSTEMIC", {"tier": "GLOBAL_SYSTEMIC", "weight": 0.6})
    return tiers.get("GLOBAL_LOCAL", {"tier": "GLOBAL_LOCAL", "weight": 0.05})


def assess_relevance(event: ClassifiedEvent) -> dict:
    """
    Returns {"mission_relevance": ..., "relevance_reason": ..., "novelty": ...}.

    Never raises — falls back to a conservative, inspectable default
    (LOW_CONFIDENCE / WATCH-leaning, not NOT_RELEVANT) on any internal
    failure, since a mis-suppressed relevant item is a worse failure mode
    than one that just doesn't get a confident label.
    """
    try:
        suppressed, reason = should_suppress(event)
        text = f"{event.raw_title} {event.raw_summary or ''}".lower()

        if suppressed:
            novelty = _NOVELTY_FROM_SUPPRESSION_REASON.get(reason, "BACKGROUND")
            return {
                "mission_relevance": "NOT_RELEVANT",
                "relevance_reason": f"Suppressed by deterministic filter: {reason}",
                "novelty": novelty,
            }

        if _CONFIG is None:
            # Config failed to load — should_suppress already ran, so this
            # is a fallback label only, not a suppression decision.
            return {
                "mission_relevance": "LOW_CONFIDENCE",
                "relevance_reason": "Mission config unavailable — relevance not scored beyond deterministic filter.",
                "novelty": "NEW_DEVELOPMENT",
            }

        category = _category_match(text, _CONFIG)
        tier = _proximity_tier(event, text, _CONFIG)
        op_relevance = float(getattr(event, "operational_relevance", 0.0) or 0.0)
        systemic_kw = _CONFIG.get("systemic_value_override", {}).get("keywords", [])
        systemic_hit = any(kw.lower() in text for kw in systemic_kw)

        strength = op_relevance * float(tier.get("weight", 0.05))
        if category:
            strength *= 1.2
        strength = min(1.0, strength)

        # 2026-09-05 fix (found via Phase 3 eval-set sampling against real
        # historical rows): operational_relevance is a classifier
        # confidence/signal-strength field, not a mission-fit signal — a
        # generic AU-tagged human-interest story (ferry sinks off Guyana,
        # a politician blocked from entering a country) can carry
        # operational_relevance>=0.35 from classifier.py's own heuristics
        # while matching NONE of the mission's named priority categories
        # (mission §5/§8: a closed list of named operational-resilience/
        # cyber/infra/banking areas, not "anything AU-tagged above a
        # floor"). Confirmed against 38 real sampled rows: without this
        # gate, ~15 pure human-interest/markets-commentary items scored
        # RELEVANT purely on operational_relevance+AU-geography. A
        # category keyword match (or an explicit systemic-value override
        # hit) is now REQUIRED for RELEVANT — strength alone can still
        # push a category-matched item's confidence up, but can no longer
        # substitute for matching the mission at all.
        is_relevant = (category is not None or systemic_hit) and strength >= _RELEVANT_STRENGTH_FLOOR
        mission_relevance = "RELEVANT" if is_relevant else "LOW_CONFIDENCE"

        category_bit = f"matches priority category '{category['label']}'" if category else "no specific priority-category keyword match"
        systemic_bit = "; systemic-value override keyword hit" if systemic_hit else ""
        reason = (
            f"{category_bit}{systemic_bit}; proximity tier {tier['tier']} (weight {tier.get('weight')}); "
            f"operational_relevance={op_relevance:.2f}; combined strength={strength:.2f}"
        )

        return {
            "mission_relevance": mission_relevance,
            "relevance_reason": reason,
            "novelty": "NEW_DEVELOPMENT",
        }

    except Exception as exc:  # noqa: BLE001 — relevance gate must never block persistence
        logger.exception("assess_relevance failed for %r", getattr(event, "raw_title", "")[:60])
        return {
            "mission_relevance": "LOW_CONFIDENCE",
            "relevance_reason": f"relevance_gate_error: {exc}",
            "novelty": "NEW_DEVELOPMENT",
        }
