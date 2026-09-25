"""
Vendor-changelog reuse adapter (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 2): "Reuse, don't rebuild." The
intelligence source registry (tools/intelligence/seed_source_registry.py)
already has 34 `cloud_technology` sources — AWS/GitHub/Supabase/Vercel/
Next.js status and changelog feeds — continuously ingested into
Supabase's `intelligence_events` table by the existing RSS pipeline
(intelligence/ingestion/rss_adapter.py). This reads THAT table rather
than adding a second fetcher for the same feeds.

Discovery-only: this module never writes to intelligence_events, and a
missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY (e.g. running outside the
production service) degrades to no candidates, same fail-open contract
as every other source.
"""

import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

from . import common

DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_CATEGORY = "cloud_technology"


def _supabase_config() -> tuple[str, str] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    return url, key


def _event_to_candidate(event: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    title = event.get("title")
    if not title:
        return None
    return {
        **common.base_candidate(topic),
        "title": title,
        "source": event.get("url") or "",
        "summary": event.get("summary") or "(no summary)",
        "evidence_strength": "moderate",  # already-vetted intelligence source, not a raw web scrape
        "fit": "moderate",
        "value": "medium",
        "complexity": "low",  # a vendor's own status/changelog note, not a component to adopt
        "provenance": [{
            "source": "vendor_changelog",
            "location": event.get("url"),
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "intelligence_source_name": event.get("source_name"),
                "published_at": event.get("published_at"),
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
    category: str = DEFAULT_CATEGORY, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[dict[str, Any]]:
    config = _supabase_config()
    if not config:
        return []
    base_url, key = config
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    params = {
        "category": f"eq.{category}",
        "published_at": f"gte.{since}",
        "order": "published_at.desc",
        "limit": str(max_per_search),
    }
    if query:
        params["title"] = f"ilike.*{query}*"
    url = f"{base_url}/rest/v1/intelligence_events?{urllib.parse.urlencode(params)}"
    events = common.get_json(url, timeout, headers={"apikey": key, "Authorization": f"Bearer {key}"})
    if not isinstance(events, list):
        return []
    candidates = []
    for event in events[:max_per_search]:
        candidate = _event_to_candidate(event, topic, retrieved_at)
        if candidate:
            candidates.append(candidate)
    return candidates
