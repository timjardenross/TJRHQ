"""Insight Outcomes (MSN-0329 Phase 4: Intelligence Optimisation & Expansion).

Persists every Insight/Recommendation the Cognitive Core pipeline
generates, and records what happened to it afterwards. This is the one
piece of infrastructure Phase 4's objectives 2, 3, and 5 all depend on
and none of them can happen without: continuous measurement, evidence-
based prompt/threshold tuning, and confidence scoring built from
observed performance all require a durable history to measure against.
Phase 3 produced exactly one real insight and had nowhere to record
whether it was ever acted on — this closes that gap.

Non-blocking, like every other Supabase-touching module in this
platform (`event_bus.py`, `audit_service.py`): never raises, degrades
to a no-op when Supabase is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.platform.insight_engine import Insight
from core.platform.captain_brief_contract import Recommendation

log = logging.getLogger(__name__)

_VALID_OUTCOMES = {"useful", "not_useful", "incorrect", "pending"}


def record_insight(insight: Insight, recommendation: Optional[Recommendation] = None) -> Optional[str]:
    """Persist a generated Insight (and its Recommendation, if the
    Reasoning Engine produced one) to `insight_outcomes`, outcome
    defaulting to 'pending'. Returns the new row's id if persisted,
    None otherwise (including when Supabase is disabled) — matches
    `event_bus.publish_event()`'s own return contract exactly."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[insight-outcomes] Supabase disabled; insight not persisted")
            return None

        payload: dict[str, Any] = {
            "generated_at": insight.generated_at,
            "source_kind": insight.source_kind,
            "source_domains": insight.source_domains,
            "evidence_chain": insight.evidence_chain,
            "observation": insight.observation,
            "why_it_matters": insight.why_it_matters,
            "potential_impact": insight.potential_impact,
            "insight_confidence": insight.confidence,
            "aggregation_key": insight.aggregation_key,
        }
        if recommendation is not None:
            payload.update({
                "recommended_action": recommendation.description,
                "alternatives": recommendation.alternatives,
                "trade_offs": recommendation.trade_offs,
                "expected_outcome": recommendation.expected_outcome,
                "recommendation_confidence": recommendation.confidence,
            })

        result = client.insert("insight_outcomes", payload, returning=True)
        if not result.ok or not result.data:
            log.warning("[insight-outcomes] write failed: %s", result.error)
            return None
        # Chief Engineer 2026-08-09 EOD alert verification: 'insight_outcomes'
        # had zero record_heartbeat() call sites despite this being the
        # canonical, single write function every caller goes through.
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat("insight_outcomes", status="ok", detail=f"source_kind={insight.source_kind}")
        except Exception:
            pass
        return result.data[0].get("id")
    except Exception as exc:
        log.warning("[insight-outcomes] record_insight failed (non-blocking): %s", exc)
        return None


def record_outcome(insight_id: str, outcome: str, note: Optional[str] = None) -> bool:
    """Records what actually happened to a previously-persisted insight
    — 'useful', 'not_useful', or 'incorrect'. This is the field every
    Phase 4 measurement objective is built on; without real calls to
    this function accumulating over time, confidence scoring/evidence-
    based tuning have nothing to work from."""
    if outcome not in _VALID_OUTCOMES:
        log.warning("[insight-outcomes] invalid outcome %r, not recorded", outcome)
        return False
    try:
        from datetime import datetime, timezone
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        raw = client.raw_client
        if raw is None:
            return False
        raw.table("insight_outcomes").update({
            "outcome": outcome,
            "outcome_note": note,
            "outcome_recorded_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", insight_id).execute()
        return True
    except Exception as exc:
        log.warning("[insight-outcomes] record_outcome failed (non-blocking): %s", exc)
        return False


def fetch_outcome_history(limit: int = 100) -> list[dict[str, Any]]:
    """Poll-based read, matching `event_bus.poll_events()`'s own
    convention. Returns [] on any error or when Supabase is disabled —
    an empty history is an honest starting state, not an error."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        raw = client.raw_client
        if raw is None:
            return []
        result = raw.table("insight_outcomes").select("*").order("generated_at", desc=True).limit(limit).execute()
        return list(result.data or [])
    except Exception as exc:
        log.warning("[insight-outcomes] fetch_outcome_history failed (non-blocking): %s", exc)
        return []


__all__ = ["record_insight", "record_outcome", "fetch_outcome_history"]
