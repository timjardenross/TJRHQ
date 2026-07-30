"""Captain's Inbox — Governance Integration (WP3B)

Bridges the captured_items pipeline with GovernanceContextService.
Invokes the assessment, formats the result for the DB cache columns,
and returns an update dict (does not write to DB itself — orchestrator owns writes).

Cache policy:
  - Assessment result stored in governance_assessment_json (JSONB)
  - Cache expires after 24 hours (governance_cache_expires_at)
  - If cache is still valid, returns cached values (no re-assessment)
  - Cache is invalidated externally via event_listeners.py when artefacts change
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24


def _cache_is_valid(item: dict) -> bool:
    """Return True if the cached governance assessment is still fresh."""
    expires_at = item.get("governance_cache_expires_at")
    if not expires_at:
        return False
    try:
        dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < dt
    except Exception:
        return False


def apply_governance_assessment(item: dict[str, Any]) -> dict[str, Any]:
    """
    Run (or use cached) governance assessment for item.
    Returns a dict of column updates for captured_items.
    Never raises — returns governance_status='failed' on any error.
    """
    # Return cached result if still valid
    if _cache_is_valid(item):
        log.debug("[governance-integration] Cache hit for item %s", item.get("id"))
        return {}  # No updates needed; existing cache columns are current

    entity = {
        "title": item.get("title", ""),
        "summary": item.get("summary") or item.get("raw_text", ""),
        "raw_text": item.get("raw_text", ""),
    }
    context = {
        "classification": item.get("classification"),
        "item_type": item.get("item_type"),
    }

    try:
        from core.coordination.governance_service import GovernanceContextService
        svc = GovernanceContextService()
        assessment = svc.assess_governance(entity, context)
    except Exception as exc:
        log.warning("[governance-integration] Service call failed: %s", exc)
        return {"governance_status": "failed"}

    conflicts = assessment.get("conflicts", [])
    max_severity = _max_severity(conflicts)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=_CACHE_TTL_HOURS)

    return {
        "governance_assessment_json": assessment,
        "governance_assessment_at": now.isoformat(),
        "governance_cache_expires_at": expires.isoformat(),
        "governance_status": _map_status(assessment.get("status", "unknown")),
        "governance_conflict_count": len(conflicts),
        "governance_max_severity": max_severity,
        "requires_governance_review": len(conflicts) > 0,
    }


def _map_status(assessment_status: str) -> str:
    mapping = {
        "assessed": "aligned",
        "conflicts_detected": "conflicts",
        "unknown": "unknown",
    }
    return mapping.get(assessment_status, "unknown")


def _max_severity(conflicts: list[dict]) -> str | None:
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    if not conflicts:
        return None
    severities = [c.get("severity", "low") for c in conflicts]
    return max(severities, key=lambda s: severity_rank.get(s, 0))
