"""
Watchlist tracker — Phase A post-brief automation (Stage: materialisation).

After a brief publishes with curated forward-watch items, each item carries a
query {keyword, lookfor, timeframe}. In the next collection cycle the tracker
checks whether any new signal matches an item's query — i.e. whether the
forward-watch prediction materialised — and records the outcome in
watchlist_tracking (materialised=True with the matching event, or a single
materialised=False marker if nothing matched yet).

Matching is intentionally simple/explainable (keyword containment + optional
'lookfor' term), mirroring the spec's find_matching_signals. The match_score is
a light strength signal, not a precision-tuned relevance model.
"""

from __future__ import annotations

import re
from typing import Any, Optional


def _text_of(event: dict) -> str:
    parts = [
        event.get("raw_title") or event.get("title", ""),
        event.get("raw_summary") or event.get("summary", "") or "",
        event.get("analysis_summary", "") or "",
    ]
    return " ".join(p for p in parts if p).lower()


def query_matches_event(query: dict, event: dict) -> tuple[bool, float]:
    """Return (matches, score). keyword is required; lookfor is an optional
    additional constraint. Empty keyword never matches (avoids matching everything)."""
    keyword = (query.get("keyword") or "").strip().lower()
    lookfor = (query.get("lookfor") or "").strip().lower()
    if not keyword:
        return False, 0.0

    text = _text_of(event)
    if keyword not in text:
        return False, 0.0
    if lookfor and lookfor not in text:
        return False, 0.0

    # Score: keyword hit = 0.6, +0.4 if a lookfor term is also present.
    score = 0.6 + (0.4 if lookfor and lookfor in text else 0.0)
    return True, round(score, 3)


class WatchlistTracker:
    """Links watchlist items to next-cycle signals that materialise them."""

    def __init__(self, repo):
        self.repo = repo

    def track_item(self, watchlist_item: dict, candidate_events: list[dict]) -> list[dict]:
        """Check one watchlist item against candidate events; write tracking rows.

        Returns the tracking rows written (one per match, or a single
        not-materialised marker when nothing matched)."""
        item_id = watchlist_item["id"]
        query = watchlist_item.get("query") or {}

        matches = []
        for ev in candidate_events:
            ok, score = query_matches_event(query, ev)
            if ok:
                matches.append((ev, score))

        written: list[dict] = []
        if matches:
            for ev, score in matches:
                written.append(self.repo.insert_watchlist_tracking({
                    "watchlist_item_id": item_id,
                    "event_id": ev.get("event_id"),
                    "materialized": True,
                    "match_score": score,
                }))
        else:
            written.append(self.repo.insert_watchlist_tracking({
                "watchlist_item_id": item_id,
                "event_id": None,
                "materialized": False,
                "match_score": None,
            }))
        return written

    def track_brief(self, brief_id: str, candidate_events: Optional[list[dict]] = None) -> dict:
        """Track every watchlist item on a brief. Candidate events default to all
        events currently in the repository (production would scope to the cycle)."""
        items = self.repo.list_watchlist_items(brief_id)
        if candidate_events is None:
            candidate_events = self.repo.list_events()

        summary: dict[str, Any] = {"items": len(items), "materialized": 0, "pending": 0}
        for item in items:
            rows = self.track_item(item, candidate_events)
            if any(r.get("materialized") for r in rows):
                summary["materialized"] += 1
            else:
                summary["pending"] += 1
        return summary
