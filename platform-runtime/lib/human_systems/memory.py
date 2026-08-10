"""Human Systems — Memory Integration (HSF-001 §Memory, §9).

Persists the framework's proactive output and the Captain's feedback so the
system can personalise over time: which patterns recur, which interventions
help, and which recommendations the Captain found unhelpful.

Writes are *non-blocking* — if Supabase is unavailable the calls degrade
silently (the framework keeps working without memory), matching the existing
CommanderSupabaseClient contract used across the bot.

Tables (see core/infrastructure/supabase/migrations/0125_human_systems.sql):
  - human_systems_recommendations  — every proactive recommendation issued
  - human_systems_feedback         — Captain's usefulness feedback
  - human_systems_patterns         — significant patterns / preferences / triggers
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REC_TABLE = "human_systems_recommendations"
FEEDBACK_TABLE = "human_systems_feedback"
PATTERN_TABLE = "human_systems_patterns"
FRICTION_TABLE = "human_systems_friction"


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return None
        return client
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("[human-systems.memory] Supabase unavailable: %s", exc)
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_recommendation(
    *,
    kind: str,
    domain: str,
    output_class: str,
    summary: str,
    source: str = "system",
    user_id: str | None = None,
) -> bool:
    """Persist a recommendation/push that was surfaced to the Captain.

    Non-blocking: returns False (without raising) when memory is unavailable.
    """
    client = _client()
    if client is None:
        return False
    payload = {
        "issued_on": date.today().isoformat(),
        "kind": kind,
        "domain": domain,
        "output_class": output_class,
        "summary": summary[:1000],
        "source": source,
        "user_id": user_id,
        "created_at": _now(),
    }
    try:
        result = client.insert(REC_TABLE, payload)
        return bool(getattr(result, "ok", False))
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems.memory] record_recommendation failed: %s", exc)
        return False


# Pilot feedback taxonomy → boolean usefulness mapping (migration 0021).
_CATEGORY_USEFUL = {"helpful": True, "neutral": None, "not_helpful": False}


def record_feedback(
    *,
    summary: str,
    category: str = "helpful",
    note: str | None = None,
    domain: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Persist the Captain's feedback on a recommendation.

    ``category`` ∈ {helpful, neutral, not_helpful} (the Validation Pilot
    taxonomy). Neutral and not-helpful feedback are stored too, so the system can
    measure capacity impact and avoid repeating unhelpful guidance.
    """
    client = _client()
    if client is None:
        return False
    category = category if category in _CATEGORY_USEFUL else "helpful"
    payload = {
        "given_on": date.today().isoformat(),
        "summary": summary[:1000],
        "category": category,
        "useful": _CATEGORY_USEFUL[category],
        "note": (note or "")[:1000] or None,
        "domain": domain,
        "user_id": user_id,
        "created_at": _now(),
    }
    try:
        result = client.insert(FEEDBACK_TABLE, payload)
        return bool(getattr(result, "ok", False))
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems.memory] record_feedback failed: %s", exc)
        return False


def record_pattern(
    *,
    pattern_type: str,
    description: str,
    domain: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Persist a significant pattern, preference, effective intervention, or trigger.

    pattern_type ∈ {pattern, preference, intervention, trigger, rejected}.
    """
    client = _client()
    if client is None:
        return False
    payload = {
        "observed_on": date.today().isoformat(),
        "pattern_type": pattern_type,
        "description": description[:1000],
        "domain": domain,
        "user_id": user_id,
        "created_at": _now(),
    }
    try:
        result = client.insert(PATTERN_TABLE, payload)
        return bool(getattr(result, "ok", False))
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems.memory] record_pattern failed: %s", exc)
        return False


def record_friction(*, friction_key: str, description: str, lever: str, confidence: float) -> bool:
    """Persist a detected friction finding to the register (HSF-002 WP4). Non-blocking."""
    client = _client()
    if client is None:
        return False
    payload = {
        "observed_on": date.today().isoformat(),
        "friction_key": friction_key,
        "description": description[:1000],
        "lever": lever[:1000],
        "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "created_at": _now(),
    }
    try:
        result = client.insert(FRICTION_TABLE, payload)
        return bool(getattr(result, "ok", False))
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems.memory] record_friction failed: %s", exc)
        return False


def get_recent_patterns(limit: int = 10) -> list[dict]:
    """Return recent stored patterns/preferences for personalisation. Empty on failure."""
    client = _client()
    if client is None or client.raw_client is None:
        return []
    try:
        result = (
            client.raw_client.table(PATTERN_TABLE)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(result.data or [])
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems.memory] get_recent_patterns failed: %s", exc)
        return []


def get_effective_interventions(limit: int = 10) -> list[dict]:
    """Return interventions the Captain previously marked useful. Empty on failure."""
    client = _client()
    if client is None or client.raw_client is None:
        return []
    try:
        result = (
            client.raw_client.table(FEEDBACK_TABLE)
            .select("*")
            .eq("useful", True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(result.data or [])
    except Exception as exc:  # pragma: no cover
        log.warning("[human-systems.memory] get_effective_interventions failed: %s", exc)
        return []
