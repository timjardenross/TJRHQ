"""
Phase A pipeline enrichment — the seam that adds source-tier, fuzzy-dedup
clustering, and 10-dimension scoring to the live collection path
(scheduler._daily_collection_job), then persists via save_event(..., phase_a=).

Kept as a standalone, guarded step so the critical daily job can fall back to a
plain save if anything here fails. Design notes:

  * Scoring uses the Analyst's HEURISTIC path (use_llm=False) — a daily batch of
    30+ signals must not fire an LLM call per signal. Narrative LLM work stays in
    the fortnightly brief job.
  * The ranker's composite rank_score stays authoritative; the Analyst only adds
    score_breakdown / relevance_score / risk_rating (ratified separation).
  * Canonicals are saved first so near-duplicate members can reference the real
    canonical event_id (migration 0077 canonical_signal_id).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


def source_tier_for(event: Any) -> Optional[int]:
    from intelligence.classification.source_tier import classify_source_tier
    url = getattr(event, "canonical_url", None)
    return classify_source_tier(url) if url else 4


def _score_fields(event: Any, analyst) -> dict:
    score = analyst.score_event(event)
    return {
        "score_breakdown": score.score_breakdown,
        "relevance_score": score.relevance_score,
        "risk_rating": score.risk_rating,
    }


def cluster_events(events: list) -> list:
    """Fuzzy-cluster a batch of events. Returns SignalCluster list keyed by
    the events' batch index (as string id)."""
    from intelligence.classification.deduplicator import SignalDeduplicator
    signals = [
        {"id": str(i),
         "title": getattr(e, "raw_title", "") or "",
         "summary": getattr(e, "raw_summary", "") or ""}
        for i, e in enumerate(events)
    ]
    return SignalDeduplicator().cluster_signals(signals)


def enrich_and_save(events: list, store, analyst=None) -> dict:
    """Enrich a ranked-event batch with Phase A fields and persist.

    Saves cluster canonicals first (signal_status=SCORED), then near-duplicate
    members (signal_status=DUPLICATE, canonical_signal_id set). Returns counts.
    """
    if not events:
        return {"canonical": 0, "duplicate": 0, "failed": 0}

    if analyst is None:
        from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst
        analyst = IntelligenceAnalyst(use_llm=False)  # heuristic-only for batch

    clusters = cluster_events(events)
    stats = {"canonical": 0, "duplicate": 0, "failed": 0}
    idx_to_event_id: dict[int, Optional[str]] = {}

    # 1) canonicals first
    for cluster in clusters:
        ci = int(cluster.canonical_id)
        ev = events[ci]
        pa = {"source_tier": source_tier_for(ev), "signal_status": "SCORED"}
        try:
            pa.update(_score_fields(ev, analyst))
        except Exception as exc:  # scoring must never block persistence
            log.warning("Phase A scoring failed for %s: %s", getattr(ev, "raw_title", "")[:60], exc)
        try:
            eid = store.save_event(ev, phase_a=pa)
        except Exception as exc:
            log.warning("save_event (canonical) failed: %s", exc)
            eid = None
        idx_to_event_id[ci] = eid
        if eid:
            stats["canonical"] += 1
        else:
            stats["failed"] += 1

    # 2) near-duplicate members
    for cluster in clusters:
        canon_event_id = idx_to_event_id.get(int(cluster.canonical_id))
        for member in cluster.member_ids:
            mi = int(member)
            ev = events[mi]
            pa = {
                "source_tier": source_tier_for(ev),
                "signal_status": "DUPLICATE",
                "canonical_signal_id": canon_event_id,
                "cluster_similarity": cluster.similarities.get(member),
            }
            try:
                if store.save_event(ev, phase_a=pa):
                    stats["duplicate"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                log.warning("save_event (duplicate) failed: %s", exc)
                stats["failed"] += 1

    return stats
