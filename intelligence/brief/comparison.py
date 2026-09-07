"""
Deterministic current-vs-prior brief comparison (Section 13).

Classifies each of today's top events as NEW / ESCALATED / IMPROVED /
UNCHANGED_BUT_MATERIAL against the prior canonical brief's stored
top_events, plus which of the prior brief's top events are NO_LONGER_MATERIAL
today. Matching is by title similarity (difflib) plus event_type — no LLM
call, no invented history: every classification is traceable to the two
stored top_events lists it was computed from (Section 22/26).

This is intentionally a bounded first version (Section 13): it only compares
each day's top ~5 events, not the full event history. A deeper
signal-level/day-over-day tracking system is FUTURE work.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional

_TITLE_MATCH_THRESHOLD = 0.55
_RISK_ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2, "UNKNOWN": -1}


def _norm_title(title: str) -> str:
    return " ".join((title or "").lower().split())


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm_title(a), _norm_title(b)).ratio()


def _best_match(event: dict, candidates: list[dict]) -> Optional[dict]:
    best, best_score = None, 0.0
    for c in candidates:
        score = _similar(event.get("title", ""), c.get("title", ""))
        if event.get("event_type") and event.get("event_type") == c.get("event_type"):
            score += 0.1
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= _TITLE_MATCH_THRESHOLD else None


def compute_comparison(current_top_events: list[dict], prior_top_events: Optional[list[dict]]) -> Optional[dict]:
    """
    current_top_events / prior_top_events: lists shaped like
    intelligence_briefs.top_events (title, event_type, risk_rating, ...).
    Returns None if there is no prior brief to compare against (first brief
    ever, or the prior row predates this uplift and has no top_events).
    """
    if not prior_top_events:
        return None

    current_top_events = current_top_events or []
    result = {
        "new": [], "escalated": [], "improved": [],
        "unchanged_but_material": [], "no_longer_material": [],
    }

    matched_prior_titles: set[str] = set()

    for event in current_top_events:
        match = _best_match(event, prior_top_events)
        if not match:
            result["new"].append({"title": event.get("title"), "risk_rating": event.get("risk_rating")})
            continue

        matched_prior_titles.add(_norm_title(match.get("title", "")))
        cur_risk = _RISK_ORDER.get((event.get("risk_rating") or "").upper(), -1)
        prior_risk = _RISK_ORDER.get((match.get("risk_rating") or "").upper(), -1)

        entry = {
            "title": event.get("title"),
            "risk_rating": event.get("risk_rating"),
            "prior_risk_rating": match.get("risk_rating"),
        }
        if cur_risk > prior_risk:
            result["escalated"].append(entry)
        elif cur_risk < prior_risk:
            result["improved"].append(entry)
        else:
            result["unchanged_but_material"].append(entry)

    for prior_event in prior_top_events:
        if _norm_title(prior_event.get("title", "")) not in matched_prior_titles:
            result["no_longer_material"].append({
                "title": prior_event.get("title"), "risk_rating": prior_event.get("risk_rating"),
            })

    return result
