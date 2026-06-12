"""
Persistence layer for the OR Intelligence Agent.
Thin wrapper over the existing Supabase PostgREST pattern used throughout
the platform (mirrors tools/supabase/client.py conventions).
"""

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional

from intelligence.config import SUPABASE_URL, SUPABASE_KEY
from intelligence.models import (
    ClassifiedEvent, RankedEvent, ResilienceBrief,
    SourceRecord, SourceHealth
)

log = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _post(table: str, payload: dict, on_conflict: Optional[str] = None) -> Optional[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase not configured — skipping persist for %s", table)
        return None

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = _headers()
    prefer = "return=representation,resolution=merge-duplicates"
    if on_conflict:
        prefer += f",on_conflict={on_conflict}"
    headers["Prefer"] = prefer

    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result[0] if isinstance(result, list) else result
    except Exception as exc:
        log.error("Supabase insert failed (%s): %s", table, exc)
        return None


def _get(path: str) -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("Supabase query failed (%s): %s", path, exc)
        return []


# ─── Source Registry ──────────────────────────────────────────────────────────

def load_source_registry() -> list[SourceRecord]:
    rows = _get("intelligence_source_registry?active=eq.true&order=priority_rank.asc")
    sources = []
    for r in rows:
        sources.append(SourceRecord(
            source_id=r["source_id"],
            source_name=r["source_name"],
            category=r["category"],
            priority_rank=r["priority_rank"],
            url=r["url"],
            source_type=r["source_type"],
            jurisdiction=r["jurisdiction"],
            confidence_weight=float(r.get("confidence_weight", 0.8)),
            active=r.get("active", True),
            rss_url=r.get("rss_url"),
            api_endpoint=r.get("api_endpoint"),
            notes=r.get("notes"),
        ))
    return sources


def load_source_registry_all() -> list[dict]:
    """Return raw dicts for API responses."""
    return _get("intelligence_source_registry?order=priority_rank.asc,category.asc")


# ─── Source Health ────────────────────────────────────────────────────────────

def save_source_health(health: SourceHealth) -> None:
    _post("intelligence_source_health", {
        "source_id": health.source_id,
        "checked_at": health.checked_at.isoformat(),
        "status": health.status,
        "items_retrieved": health.items_retrieved,
        "latency_ms": health.latency_ms,
        "error_message": health.error_message,
        "http_status": health.http_status,
    })


def load_latest_source_health() -> list[dict]:
    """Return most recent health row per source for dashboard display."""
    rows = _get(
        "intelligence_source_health"
        "?order=checked_at.desc&limit=500"
    )
    seen: dict[str, dict] = {}
    for row in rows:
        sid = row["source_id"]
        if sid not in seen:
            seen[sid] = row
    return list(seen.values())


# ─── Events ───────────────────────────────────────────────────────────────────

def event_hash_exists(dedup_hash: str) -> bool:
    rows = _get(f"intelligence_events?dedup_hash=eq.{dedup_hash}&limit=1")
    return len(rows) > 0


def save_event(event: RankedEvent) -> Optional[str]:
    """Persist a ranked event. Returns event_id or None on failure."""
    row = {
        "source_id": event.source_id,
        "raw_title": event.raw_title,
        "raw_summary": event.raw_summary,
        "canonical_url": event.canonical_url,
        "published_at": event.published_at.isoformat() if event.published_at else None,
        "collected_at": event.collected_at.isoformat(),
        "event_type": event.event_type,
        "geography": event.geography,
        "sector": event.sector,
        "operational_relevance": float(event.operational_relevance),
        "customer_impact": event.customer_impact,
        "banking_relevance": event.banking_relevance,
        "cps230_relevance": event.cps230_relevance,
        "dependency_risk": event.dependency_risk,
        "confidence": float(event.confidence),
        "rank_score": float(event.rank_score),
        "dedup_hash": event.dedup_hash,
        "suppressed": event.suppressed,
        "suppression_reason": event.suppression_reason,
    }
    result = _post("intelligence_events", row, on_conflict="dedup_hash")
    if result:
        return result.get("event_id")
    return None


def link_events_to_brief(event_ids: list[str], brief_id: str) -> None:
    """Update brief_id on included events. Uses individual PATCH calls."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    for eid in event_ids:
        url = f"{SUPABASE_URL}/rest/v1/intelligence_events?event_id=eq.{eid}"
        headers = {**_headers(), "Prefer": "return=minimal"}
        body = json.dumps({"brief_id": brief_id}).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as exc:
            log.warning("Could not link event %s to brief %s: %s", eid, brief_id, exc)


def load_recent_events(days: int = 14, limit: int = 200) -> list[dict]:
    from datetime import timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return _get(
        f"intelligence_events"
        f"?collected_at=gte.{since}"
        f"&suppressed=eq.false"
        f"&order=rank_score.desc"
        f"&limit={limit}"
    )


# ─── Briefs ───────────────────────────────────────────────────────────────────

def save_brief(brief: ResilienceBrief) -> Optional[str]:
    """Persist a ResilienceBrief. Returns brief_id or None on failure."""
    import dataclasses

    def _serialise(obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    top_events_json = [
        {
            "event_id": e.event_id,
            "title": e.title,
            "location": e.location,
            "event_type": e.event_type,
            "risk_rating": e.risk_rating,
            "summary": e.summary,
            "operational_impact": e.operational_impact,
            "so_what": e.so_what,
            "status": e.status,
            "source_name": e.source_name,
            "canonical_url": e.canonical_url,
            "rank_score": e.rank_score,
        }
        for e in brief.top_events
    ]

    row = {
        "brief_id": brief.brief_id,
        "generated_at": brief.generated_at.isoformat(),
        "period_start": brief.period_start.strftime("%Y-%m-%d"),
        "period_end": brief.period_end.strftime("%Y-%m-%d"),
        "sources_checked": brief.sources_checked,
        "sources_available": brief.sources_available,
        "sources_failed": brief.sources_failed,
        "sources_stale": brief.sources_stale,
        "events_evaluated": brief.events_evaluated,
        "events_included": brief.events_included,
        "events_suppressed": brief.events_suppressed,
        "executive_snapshot": brief.executive_snapshot,
        "emerging_themes": brief.emerging_themes,
        "forward_watch": brief.forward_watch,
        "cps230_implications": brief.cps230_implications,
        "bottom_line": brief.bottom_line,
        "top_events": top_events_json,
        "overall_risk": brief.overall_risk,
        "llm_used": brief.llm_used,
        "provider_used": brief.provider_used,
        "confidence": float(brief.confidence) if brief.confidence else None,
        "narrative_available": brief.narrative_available,
        "trigger_type": brief.trigger_type,
    }
    result = _post("intelligence_briefs", row)
    if result:
        return result.get("brief_id")
    return None


def load_latest_brief() -> Optional[dict]:
    rows = _get("intelligence_briefs?order=generated_at.desc&limit=1")
    return rows[0] if rows else None


def load_brief_archive(limit: int = 20, offset: int = 0) -> list[dict]:
    return _get(
        f"intelligence_briefs"
        f"?order=generated_at.desc"
        f"&limit={limit}"
        f"&offset={offset}"
    )
