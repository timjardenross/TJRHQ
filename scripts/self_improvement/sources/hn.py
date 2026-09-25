"""
Hacker News (Algolia) adapter (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 1): "practitioner signal — what
engineers are actually adopting or complaining about." The points
threshold is the noise filter at search time; `value` below then grades
by the actual point count, per the doc's own scoring table (§4).

Dedup note (doc §2's HN row): when a story links to a GitHub repo, this
sets `source` to that canonical repo URL rather than the HN thread URL —
`opportunity_store.new_fingerprint()` hashes `discovery_source:source:title`,
so this is what lets an HN-discovered repo collapse onto the same GitHub
candidate discovered independently, instead of creating a second
opportunity for the same repo.
"""

import json
import re
import urllib.parse
from typing import Any

from . import common

HN_SEARCH_BASE = "https://hn.algolia.com/api/v1/search"
HN_ITEM_BASE = "https://hn.algolia.com/api/v1/items"
DEFAULT_MIN_POINTS = 50


def _value_from_points(points: int) -> str:
    if points >= 500:
        return "high"
    if points >= 200:
        return "medium"
    return "low"


def _hit_to_candidate(hit: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    title = hit.get("title")
    object_id = hit.get("objectID")
    if not title or not object_id:
        return None
    points = hit.get("points") or 0
    story_url = hit.get("url")
    hn_thread_url = f"https://news.ycombinator.com/item?id={object_id}"

    return {
        **common.base_candidate(topic),
        "title": title,
        "source": story_url or hn_thread_url,
        "summary": hit.get("story_text") or f"Hacker News discussion, {points} points, {hit.get('num_comments', 0)} comments.",
        "evidence_strength": "weak",  # practitioner discussion, not the project's own evidence
        "fit": "moderate",
        "value": _value_from_points(points),
        "complexity": "moderate",  # unknown without the linked project's own evidence; Phase 3 enrichment may sharpen this
        "provenance": [{
            "source": "hn",
            "location": hn_thread_url,
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "hn_object_id": object_id,
                "points": points,
                "num_comments": hit.get("num_comments"),
                "story_url": story_url,
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
    min_points: int = DEFAULT_MIN_POINTS,
) -> list[dict[str, Any]]:
    params = {
        "query": query, "tags": "story", "numericFilters": f"points>{min_points}",
        "hitsPerPage": max_per_search,
    }
    url = f"{HN_SEARCH_BASE}?{urllib.parse.urlencode(params)}"
    result = common.get_json(url, timeout)
    if not result:
        return []
    hits = (result.get("hits") or [])[:max_per_search]
    candidates = []
    for hit in hits:
        candidate = _hit_to_candidate(hit, topic, retrieved_at)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_top_comment(hn_object_id: str, *, max_chars: int, timeout: int) -> str | None:
    """Best-effort: the first top-level comment's text, HTML-stripped and
    truncated. Used by external_enrichment.py, not by search() itself —
    fetching every story's comment tree at discovery time would multiply
    the request count search() is bounded by."""
    url = f"{HN_ITEM_BASE}/{hn_object_id}"
    result = common.get_json(url, timeout)
    if not result:
        return None
    for child in result.get("children") or []:
        text = child.get("text")
        if text:
            stripped = re.sub(r"<[^>]+>", " ", text)
            return " ".join(stripped.split())[:max_chars]
    return None
