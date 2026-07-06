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


def _publish_core_event(event_type: str, **kwargs) -> None:
    """SUOC Wave 3/MSN-0210K: thin-index mirror into the shared Event Bus
    (core_events). Best-effort, non-blocking — never raises, never affects
    intelligence_events/intelligence_briefs persistence, which remains the
    real source of truth for this domain exactly as before."""
    try:
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.platform.event_bus import publish_event
        publish_event(event_type, domain="operational-resilience-intelligence", source="intelligence_store", **kwargs)
    except Exception:
        pass


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
    if health.status == "failed":
        _publish_core_event(
            "intelligence.source.failed",
            linked_entities=[health.source_id],
            recommended_action=health.error_message,
        )


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


def event_canonical_url_exists(canonical_url: str) -> bool:
    """Check if any persisted event already has this canonical URL (cross-run dedup)."""
    import urllib.parse
    encoded = urllib.parse.quote(canonical_url, safe="")
    rows = _get(f"intelligence_events?canonical_url=eq.{encoded}&limit=1")
    return len(rows) > 0


def event_title_date_exists(normalised_title: str, date_str: str) -> bool:
    """Fallback cross-run dedup when canonical_url is null — match on title+date."""
    import urllib.parse
    enc_title = urllib.parse.quote(normalised_title, safe="")
    rows = _get(
        f"intelligence_events"
        f"?raw_title=ilike.{enc_title}"
        f"&published_at=gte.{date_str}T00:00:00"
        f"&published_at=lt.{date_str}T23:59:59"
        f"&limit=1"
    )
    return len(rows) > 0


def save_event(event: RankedEvent, ori: Optional[dict] = None) -> Optional[str]:
    """Persist a ranked event. Returns event_id or None on failure.

    `ori` optionally supplies the WP4 enrichment columns for digest-sourced
    events (source_document_id, source_ref, brief_date, organisation,
    regulatory_topic, resilience_themes, watch_item_status, executive_relevance).
    Existing callers pass no `ori` and behaviour is unchanged.
    """
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
    if ori:
        bd = ori.get("brief_date")
        row.update({
            "source_document_id":  ori.get("source_document_id"),
            "source_ref":          ori.get("source_ref"),
            "brief_date":          bd.isoformat() if hasattr(bd, "isoformat") else bd,
            "organisation":        ori.get("organisation"),
            "regulatory_topic":    ori.get("regulatory_topic"),
            "resilience_themes":   ori.get("resilience_themes"),
            "watch_item_status":   ori.get("watch_item_status"),
            "executive_relevance": ori.get("executive_relevance"),
        })
    result = _post("intelligence_events", row, on_conflict="dedup_hash")
    if result:
        event_id = result.get("event_id")
        _publish_core_event(
            "intelligence.signal.ranked",
            importance=round(row["rank_score"]),
            confidence=round(row["confidence"] * 100),
            relevance=round(row["operational_relevance"] * 100),
            linked_entities=[event_id] if event_id else [],
        )
        return event_id
    return None


# ─── ORI Source Documents (WP3/WP5 — preserve raw briefs) ──────────────────────

def document_version_exists(file_path: str, content_sha: str) -> bool:
    """Dedup Gate 1: has this exact file version already been imported?"""
    if not content_sha:
        return False
    rows = _get(
        f"ori_source_documents?file_path=eq.{file_path}"
        f"&content_sha=eq.{content_sha}&limit=1"
    )
    return len(rows) > 0


def save_source_document(doc: dict) -> Optional[str]:
    """Persist a raw brief document. Returns document_id or None on failure.

    Expects keys: source_id, file_name, file_path, blob_url, brief_date,
    content_sha, format_version, region, classification, raw_front_matter,
    raw_markdown, parse_warnings.
    """
    bd = doc.get("brief_date")
    row = dict(doc)
    if hasattr(bd, "isoformat"):
        row["brief_date"] = bd.isoformat()
    result = _post("ori_source_documents", row, on_conflict="file_path,content_sha")
    if result:
        return result.get("document_id")
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
        brief_id = result.get("brief_id")
        _publish_core_event(
            "intelligence.brief.generated",
            confidence=round(brief.confidence * 100) if brief.confidence else None,
            linked_documents=[brief_id] if brief_id else [],
            # MSN-0328 Wave 3: Telegram's /brief reads this brief's rich
            # content (bottom_line/overall_risk/themes) directly from
            # intelligence_briefs today. Attaching it here means the
            # canonical pipeline's event carries the same substance,
            # not just "a brief exists" -- required for Telegram to
            # converge without losing what it currently shows.
            metrics={
                "overall_risk": brief.overall_risk,
                "bottom_line": brief.bottom_line,
                "emerging_themes": brief.emerging_themes,
                "forward_watch": brief.forward_watch,
                "brief_id": brief_id,
            },
        )
        return brief_id
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
