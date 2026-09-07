"""
Phase A pipeline enrichment — the seam that adds source-tier, fuzzy-dedup
clustering, and 10-dimension scoring to the live collection path
(scheduler._daily_collection_job), then persists via save_event(..., phase_a=).

Kept as a standalone, guarded step so the critical daily job can fall back to a
plain save if anything here fails. Design notes:

  * Scoring defaults to HEURISTIC path (use_llm=False) — a daily batch of
    30+ signals must not fire an LLM call per signal. Narrative LLM work stays in
    the fortnightly brief job.
  * Shadow-mode (Issue 14): when shadow_mode=True, runs both heuristic and LLM
    paths in parallel, logs both, uses heuristic as authoritative. Collects
    comparative data for Issue 15 evaluation harness without changing behavior.
  * The ranker's composite rank_score stays authoritative; the Analyst only adds
    score_breakdown / relevance_score / risk_rating (ratified separation).
  * Canonicals are saved first so near-duplicate members can reference the real
    canonical event_id (migration 0077 canonical_signal_id).
  * OSINT Ingestion Quality & Relevance Mission (2026-09-05): also computes
    mission_relevance/relevance_reason/novelty (relevance_gate.py, Phase 4/6)
    and disposition/disposition_reason (disposition.py, Phase 8). Shadow-mode
    only — these are new inspectable columns, they do not change suppressed/
    signal_status/rank_score or anything any consumer currently reads.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


def source_tier_for(event: Any) -> Optional[int]:
    from intelligence.classification.source_tier import classify_source_tier
    url = getattr(event, "canonical_url", None)
    return classify_source_tier(url) if url else 4


def _event_to_signal(event: Any) -> dict:
    return {
        "title": getattr(event, "raw_title", ""),
        "summary": getattr(event, "raw_summary", "") or "",
        "sector": getattr(event, "sector", ""),
        "event_type": getattr(event, "event_type", ""),
        "geography": getattr(event, "geography", ""),
        "customer_impact": getattr(event, "customer_impact", "low"),
        "banking_relevance": getattr(event, "banking_relevance", "low"),
        "cps230_relevance": getattr(event, "cps230_relevance", False),
        "dependency_risk": getattr(event, "dependency_risk", False),
        "operational_relevance": getattr(event, "operational_relevance", 0.0),
    }


def _score_fields(
    event: Any, analyst, shadow_mode: bool = False, selective_augmentation: bool = False,
) -> dict:
    """
    Score an event. If shadow_mode=True, runs both paths and stores provenance.
    Always uses heuristic as authoritative (Issue 14). If selective_augmentation
    is on (and shadow_mode isn't — shadow mode already covers every signal),
    ambiguous heuristic scores get one extra LLM call and the LLM result
    becomes authoritative on success (Issue 16 — see selective_augmentation.py
    for the provisional-threshold caveat).
    """
    if shadow_mode and hasattr(analyst, "score_dual_path"):
        # Shadow-mode (Issue 14): run both paths, store both, use heuristic
        result = analyst.score_dual_path(
            _event_to_signal(event), event_id=getattr(event, "event_id", None),
        )
        # Return heuristic as authoritative, but store LLM results + provenance
        return {
            # Authoritative (heuristic) — Issue 14 keeps these as primary
            "score_breakdown": result.heuristic.score_breakdown,
            "relevance_score": result.heuristic.relevance_score,
            "risk_rating": result.heuristic.risk_rating,
            "score_method": "heuristic",  # Issue 20 disclosure
            # Shadow-mode parallel results (Issue 14)
            "llm_score_breakdown": result.llm.score_breakdown if result.llm else None,
            "llm_relevance_score": result.llm.relevance_score if result.llm else None,
            "llm_risk_rating": result.llm.risk_rating if result.llm else None,
            "llm_provider": result.llm.provider if result.llm else None,
            # Issue 20 provenance
            "score_provenance": result.provenance,
        }

    # Standard mode (non-shadow): heuristic first
    score = analyst.score_event(event)
    method = "heuristic"

    if selective_augmentation:
        from intelligence.ingestion.selective_augmentation import augment_if_ambiguous
        score, augmented = augment_if_ambiguous(score, _event_to_signal(event), analyst)
        if augmented:
            method = "llm"

    return {
        "score_breakdown": score.score_breakdown,
        "relevance_score": score.relevance_score,
        "risk_rating": score.risk_rating,
        "score_method": method,
        "score_provenance": {"method": method},
    }


def _relevance_and_disposition_fields(event: Any, pa: dict, *, is_duplicate: bool = False) -> dict:
    """OSINT Ingestion Quality & Relevance Mission Phase 4/6/8. Never raises —
    both underlying modules already guard internally, but this seam must
    survive even if their imports fail (e.g. a malformed config file)."""
    try:
        from intelligence.classification.relevance_gate import assess_relevance
        relevance = assess_relevance(event)
    except Exception as exc:  # noqa: BLE001
        log.warning("assess_relevance failed for %s: %s", getattr(event, "raw_title", "")[:60], exc)
        relevance = {"mission_relevance": None, "relevance_reason": None, "novelty": None}

    if is_duplicate:
        # Cluster membership is a stronger novelty signal than the
        # suppression-reason-based guess relevance_gate makes — a fuzzy-
        # dedup duplicate is definitionally DUPLICATE regardless of what
        # should_suppress said about the canonical.
        relevance["novelty"] = "DUPLICATE"

    try:
        from intelligence.classification.disposition import technical_disposition
        disposition_input = {
            "suppressed": getattr(event, "suppressed", False),
            "suppression_reason": getattr(event, "suppression_reason", None),
            "signal_status": pa.get("signal_status"),
            "source_tier": pa.get("source_tier"),
            "confidence_level": pa.get("confidence_level"),
            "osint_confidence_level": getattr(event, "osint_confidence_level", None),
            "criticality_score": getattr(event, "criticality_score", None),
            "risk_rating": pa.get("risk_rating"),
            "operational_relevance": getattr(event, "operational_relevance", None),
            "banking_relevance": getattr(event, "banking_relevance", None),
            "cps230_relevance": getattr(event, "cps230_relevance", False),
            "rank_score": getattr(event, "rank_score", None),
        }
        disposition, disposition_reason = technical_disposition(disposition_input)
    except Exception as exc:  # noqa: BLE001
        log.warning("technical_disposition failed for %s: %s", getattr(event, "raw_title", "")[:60], exc)
        disposition, disposition_reason = None, None

    return {
        "mission_relevance": relevance.get("mission_relevance"),
        "relevance_reason": relevance.get("relevance_reason"),
        "novelty": relevance.get("novelty"),
        "disposition": disposition,
        "disposition_reason": disposition_reason,
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


def enrich_and_save(
    events: list, store, analyst=None, shadow_mode: bool = False,
    selective_augmentation: bool = False,
) -> dict:
    """Enrich a ranked-event batch with Phase A fields and persist.

    Saves cluster canonicals first (signal_status=SCORED), then near-duplicate
    members (signal_status=DUPLICATE, canonical_signal_id set).

    Args:
        events: List of RankedEvent to enrich.
        store: Persistence layer (SupabaseRepository).
        analyst: IntelligenceAnalyst instance (creates if None).
        shadow_mode: If True (Issue 14), run both heuristic and LLM paths in parallel.
        selective_augmentation: If True (Issue 16) and shadow_mode is off, route
            ambiguous heuristic scores to one LLM call each (see
            selective_augmentation.py — provisional threshold, ignored when
            shadow_mode is already on since that covers every signal).

    Returns dict with counts.
    """
    if not events:
        return {
            "canonical": 0, "duplicate": 0, "failed": 0,
            "shadow_mode": shadow_mode, "selective_augmentation": selective_augmentation,
        }

    if analyst is None:
        from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst
        from intelligence.config import SUPABASE_KEY, SUPABASE_URL
        from intelligence.governance import LLMCostGovernance

        needs_llm = shadow_mode or selective_augmentation
        # Shadow-mode / selective augmentation need cost governance + LLM
        # support. Without real credentials LLMCostGovernance is a
        # permissive no-op (no limit enforcement, log_call() silently
        # drops) — pass the same service-role creds intelligence_store
        # uses so limits/logging work.
        cost_gov = LLMCostGovernance(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY) if needs_llm else None
        analyst = IntelligenceAnalyst(
            use_llm=shadow_mode,
            shadow_mode=shadow_mode,
            cost_governor=cost_gov,
        )

    clusters = cluster_events(events)
    stats = {
        "canonical": 0, "duplicate": 0, "failed": 0,
        "shadow_mode": shadow_mode, "selective_augmentation": selective_augmentation,
    }
    idx_to_event_id: dict[int, Optional[str]] = {}

    # 1) canonicals first
    for cluster in clusters:
        ci = int(cluster.canonical_id)
        ev = events[ci]
        pa = {"source_tier": source_tier_for(ev), "signal_status": "SCORED"}
        try:
            pa.update(_score_fields(
                ev, analyst, shadow_mode=shadow_mode, selective_augmentation=selective_augmentation,
            ))
        except Exception as exc:  # scoring must never block persistence
            log.warning("Phase A scoring failed for %s: %s", getattr(ev, "raw_title", "")[:60], exc)
        pa.update(_relevance_and_disposition_fields(ev, pa, is_duplicate=False))
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
            pa.update(_relevance_and_disposition_fields(ev, pa, is_duplicate=True))
            try:
                if store.save_event(ev, phase_a=pa):
                    stats["duplicate"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                log.warning("save_event (duplicate) failed: %s", exc)
                stats["failed"] += 1

    return stats
