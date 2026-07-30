"""
Operating Picture Engine — USS TJR MSN-0200 (P1E).

Synthesises a single executive picture from:
  - Health & recovery (captains_log_entries + recovery_confidence_today)
  - Active missions (blocked, P0/P1, recent state changes)
  - Intelligence signals (latest brief — risks, opportunities)

Exposed via GET /api/v1/intelligence/operating-picture (cache TTL 5 min).

Answers: "What do I need to know right now?"
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("operating-picture")

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


# ── Supabase helper ───────────────────────────────────────────────────────────

def _sb_get(table: str, query: str = "") -> list[dict]:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return []
    url = f"{_SUPABASE_URL}/rest/v1/{table}{'?' + query if query else ''}"
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.warning("Supabase fetch failed (%s): %s", table, exc)
        return []


# ── Section builders ──────────────────────────────────────────────────────────

def _build_health_section() -> dict:
    today = date.today().isoformat()

    # Captain's log entry
    log_rows = _sb_get(
        "captains_log_entries",
        f"log_date=eq.{today}&limit=1"
        f"&select=capacity_score,energy,pain_score,sleep_hours,health_status,overall_note",
    )
    log_entry = log_rows[0] if log_rows else None

    # Recovery confidence view
    conf_rows = _sb_get(
        "recovery_confidence_today",
        "limit=1&select=confidence_pct,band,nervous_system_state",
    )
    confidence = conf_rows[0] if conf_rows else None

    # Latest pulse
    pulse_rows = _sb_get(
        "recovery_pulses",
        f"created_at=gte.{today}T00:00:00Z&order=created_at.desc&limit=1"
        f"&select=pulse_type,pain_score,energy,mood,readiness,created_at",
    )
    latest_pulse = pulse_rows[0] if pulse_rows else None

    cap_score = log_entry.get("capacity_score") if log_entry else None

    def _band(score) -> str:
        try:
            s = int(score)
        except (TypeError, ValueError):
            return "unknown"
        if s >= 80:
            return "high"
        if s >= 60:
            return "moderate"
        if s >= 40:
            return "reduced"
        return "low"

    return {
        "capacity_score": cap_score,
        "capacity_band": _band(cap_score),
        "pain_score": log_entry.get("pain_score") if log_entry else None,
        "energy": log_entry.get("energy") if log_entry else None,
        "sleep_hours": log_entry.get("sleep_hours") if log_entry else None,
        "health_status": log_entry.get("health_status") if log_entry else None,
        "recovery_confidence_pct": confidence.get("confidence_pct") if confidence else None,
        "recovery_band": confidence.get("band") if confidence else None,
        "nervous_system_state": confidence.get("nervous_system_state") if confidence else None,
        "latest_pulse": latest_pulse,
        "log_available": log_entry is not None,
    }


def _build_missions_section() -> dict:
    all_active = _sb_get(
        "missions",
        "status=not.in.(Closed,Archived,Idea)&order=priority.asc,updated_at.desc"
        "&limit=20&select=mission_id,title,status,priority,department,updated_at",
    )

    blocked = [m for m in all_active if m.get("status") == "Blocked"]
    p0_p1 = [m for m in all_active if m.get("priority") in ("P0", "P1")]
    awaiting = [m for m in all_active if "Awaiting" in (m.get("status") or "")]

    # Recent state transitions (last 24h)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    transitions = _sb_get(
        "mission_state_transitions",
        f"changed_at=gte.{since}&order=changed_at.desc&limit=10"
        f"&select=mission_id,from_status,to_status,changed_at",
    )

    return {
        "total_active": len(all_active),
        "blocked_count": len(blocked),
        "blocked": blocked[:5],
        "high_priority": p0_p1[:5],
        "awaiting_review": awaiting[:3],
        "recent_changes_24h": transitions[:5],
    }


def _build_intelligence_section() -> dict:
    # Latest ORI brief
    briefs = _sb_get("intelligence_briefs", "order=generated_at.desc&limit=1")
    brief = briefs[0] if briefs else None

    # Recent signals (last 24h)
    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    signals = _sb_get(
        "intelligence_events",
        f"collected_at=gte.{since_24h}&suppressed=eq.false"
        f"&order=rank_score.desc&limit=10"
        f"&select=raw_title,event_type,geography,risk_rating,rank_score,collected_at",
    )

    high_signals = [s for s in signals if s.get("risk_rating") == "HIGH"]
    medium_signals = [s for s in signals if s.get("risk_rating") == "MEDIUM"]

    return {
        "latest_brief": {
            "brief_id": brief.get("brief_id") if brief else None,
            "generated_at": brief.get("generated_at") if brief else None,
            "overall_risk": brief.get("overall_risk") if brief else None,
            "executive_snapshot": (brief.get("executive_snapshot") or "")[:500] if brief else None,
            "emerging_themes": (brief.get("emerging_themes") or [])[:5] if brief else [],
            "bottom_line": brief.get("bottom_line") if brief else None,
        } if brief else None,
        "signals_24h": {
            "total": len(signals),
            "high": len(high_signals),
            "medium": len(medium_signals),
            "top_signals": signals[:5],
        },
        "has_new_high_signals": len(high_signals) > 0,
    }


def _derive_situation_summary(health: dict, missions: dict, intelligence: dict) -> str:
    """Rule-based situation summary — no LLM required."""
    parts = []

    cap = health.get("capacity_score")
    if cap is not None:
        band = health.get("capacity_band", "unknown")
        parts.append(f"Capacity {band} ({cap})")

    pain = health.get("pain_score")
    if pain and int(pain) >= 6:
        parts.append(f"pain elevated ({pain}/10)")

    blocked = missions.get("blocked_count", 0)
    if blocked:
        parts.append(f"{blocked} mission{'s' if blocked > 1 else ''} blocked")

    high_sigs = intelligence.get("signals_24h", {}).get("high", 0)
    if high_sigs:
        parts.append(f"{high_sigs} high-risk intelligence signal{'s' if high_sigs > 1 else ''}")

    risk = (intelligence.get("latest_brief") or {}).get("overall_risk")
    if risk and risk.upper() != "LOW":
        parts.append(f"OR risk {risk}")

    if not parts:
        return "No significant flags. Proceed as planned."
    return ". ".join(p.capitalize() for p in parts) + "."


# ── Public API ────────────────────────────────────────────────────────────────

def get_operating_picture() -> dict:
    """
    Return the current Operating Picture.

    Dict shape:
        generated_at       ISO timestamp
        situation_summary  One-sentence executive summary
        health             Health & recovery section
        missions           Mission status section
        intelligence       OR intelligence section
        attention_flags    List of items requiring immediate Captain attention
    """
    health = _build_health_section()
    missions = _build_missions_section()
    intelligence = _build_intelligence_section()

    # Attention flags — items that need the Captain's eyes right now
    flags = []

    cap = health.get("capacity_score")
    if cap is not None:
        try:
            if int(cap) < 40:
                flags.append({"type": "health", "severity": "high",
                              "message": f"Capacity critically low ({cap}) — consider reducing mission load"})
        except (TypeError, ValueError):
            pass

    pain = health.get("pain_score")
    try:
        if pain and int(pain) >= 7:
            flags.append({"type": "health", "severity": "high",
                          "message": f"Pain score elevated ({pain}/10) — recovery protocol active"})
    except (TypeError, ValueError):
        pass

    if missions.get("blocked_count", 0) >= 3:
        flags.append({"type": "missions", "severity": "medium",
                      "message": f"{missions['blocked_count']} missions blocked — unblocking action needed"})

    if intelligence.get("has_new_high_signals"):
        high = intelligence["signals_24h"]["high"]
        flags.append({"type": "intelligence", "severity": "high",
                      "message": f"{high} high-risk OR signal(s) in last 24h — review intelligence brief"})

    not_logged = not health.get("log_available")
    if not_logged:
        flags.append({"type": "health", "severity": "low",
                      "message": "No health log for today — consider logging morning pulse"})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "situation_summary": _derive_situation_summary(health, missions, intelligence),
        "health": health,
        "missions": missions,
        "intelligence": intelligence,
        "attention_flags": flags,
    }


if __name__ == "__main__":
    import sys
    picture = get_operating_picture()
    print(json.dumps(picture, indent=2, default=str))
