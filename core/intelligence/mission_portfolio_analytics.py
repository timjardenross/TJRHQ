"""
Mission Analytics Foundation — WP7
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Provides mission portfolio analytics:
- Cycle time analysis (created → closed)
- Completion rate analysis
- Mission ageing analysis
- Throughput trends (missions closed per week)
- Closure quality metrics

Data sources:
- Supabase missions table (with migration 0013 closed_at, mission_type, priority)
- outputs/daily_brief.json (fallback)
- Mission-Index.md (fallback)

Public API:
    compute_mission_analytics() -> dict
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

try:
    from supabase_client import supabase_get, is_configured
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False

_TERMINAL_STATUSES = {"Closed", "Archived", "COMPLETED", "CANCELLED", "DEFERRED"}
_ACTIVE_STATUSES   = {"Designed", "Implemented", "Tested",
                      "Awaiting Number One Review", "Validated",
                      "Awaiting XO Approval", "ACTIVE", "IN_REVIEW"}
_BLOCKED_STATUSES  = {"Blocked", "BLOCKED"}


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _fetch_missions_supabase() -> list[dict[str, Any]]:
    if not _SUPABASE_OK or not is_configured():
        return []
    try:
        return supabase_get("missions?order=created_at.asc&limit=500")
    except Exception:
        return []


def _load_missions_fallback() -> list[dict[str, Any]]:
    """Load from outputs/daily_brief.json when Supabase unavailable."""
    brief_path = _REPO_ROOT / "outputs" / "daily_brief.json"
    if not brief_path.exists():
        return []
    try:
        data = json.loads(brief_path.read_text())
        missions = []
        for item in data.get("top_priorities", []):
            missions.append({
                "id":         item.get("mission_id"),
                "title":      item.get("title"),
                "status":     item.get("status", "ACTIVE"),
                "priority":   item.get("priority"),
                "created_at": None,
                "updated_at": data.get("timestamp"),
                "closed_at":  None,
            })
        return missions
    except Exception:
        return []


def _load_all_missions() -> list[dict[str, Any]]:
    missions = _fetch_missions_supabase()
    if not missions:
        missions = _load_missions_fallback()
    return missions


# ---------------------------------------------------------------------------
# Derived fields
# ---------------------------------------------------------------------------

def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _days_open(m: dict) -> int | None:
    created = _parse_date(m.get("created_at"))
    if not created:
        return None
    closed = _parse_date(m.get("closed_at"))
    end = closed or date.today()
    return (end - created).days


def _is_terminal(m: dict) -> bool:
    return str(m.get("status", "")).strip() in _TERMINAL_STATUSES


def _is_active(m: dict) -> bool:
    return not _is_terminal(m) and str(m.get("status", "")).strip() not in _BLOCKED_STATUSES


def _is_blocked(m: dict) -> bool:
    return str(m.get("status", "")).strip() in _BLOCKED_STATUSES


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _cycle_time_analysis(missions: list[dict]) -> dict[str, Any]:
    """Analyse cycle times for closed missions."""
    closed = [m for m in missions if _is_terminal(m)]
    cycle_times = [
        dt for m in closed
        if (dt := _days_open(m)) is not None and dt >= 0
    ]

    if not cycle_times:
        return {
            "n_closed": len(closed),
            "cycle_times_available": 0,
            "note": "No closed missions with created_at data available.",
        }

    return {
        "n_closed": len(closed),
        "cycle_times_available": len(cycle_times),
        "avg_days": round(mean(cycle_times), 1),
        "median_days": round(median(cycle_times), 1),
        "min_days": min(cycle_times),
        "max_days": max(cycle_times),
        "pct_closed_under_30d": round(
            sum(1 for d in cycle_times if d <= 30) / len(cycle_times) * 100, 1
        ),
        "pct_closed_under_7d": round(
            sum(1 for d in cycle_times if d <= 7) / len(cycle_times) * 100, 1
        ),
    }


def _completion_rate_analysis(missions: list[dict]) -> dict[str, Any]:
    """Overall and by-priority completion rates."""
    total  = len(missions)
    closed = sum(1 for m in missions if _is_terminal(m))
    active = sum(1 for m in missions if _is_active(m))
    blocked = sum(1 for m in missions if _is_blocked(m))

    overall_rate = round(closed / total * 100, 1) if total else None

    # By priority
    by_priority: dict[str, dict] = {}
    for priority in ("P0", "P1", "P2", "P3"):
        subset = [m for m in missions if str(m.get("priority", "")).upper() == priority]
        if subset:
            p_closed = sum(1 for m in subset if _is_terminal(m))
            by_priority[priority] = {
                "total": len(subset),
                "closed": p_closed,
                "completion_rate": round(p_closed / len(subset) * 100, 1),
            }

    # By type
    by_type: dict[str, dict] = defaultdict(lambda: {"total": 0, "closed": 0})
    for m in missions:
        t = str(m.get("mission_type", "unclassified") or "unclassified")
        by_type[t]["total"] += 1
        if _is_terminal(m):
            by_type[t]["closed"] += 1

    return {
        "total_missions": total,
        "closed": closed,
        "active": active,
        "blocked": blocked,
        "overall_completion_rate": overall_rate,
        "by_priority": by_priority,
        "by_type": {k: {**v, "rate": round(v["closed"] / v["total"] * 100, 1) if v["total"] else 0}
                    for k, v in by_type.items()},
    }


def _ageing_analysis(missions: list[dict]) -> dict[str, Any]:
    """Flag aged active missions."""
    active_missions = [m for m in missions if not _is_terminal(m)]
    ages = [
        {"id": m.get("id"), "title": m.get("title"), "days_open": dt,
         "priority": m.get("priority"), "status": m.get("status")}
        for m in active_missions
        if (dt := _days_open(m)) is not None
    ]
    ages.sort(key=lambda x: x["days_open"], reverse=True)

    stale_30 = [a for a in ages if a["days_open"] >= 30]
    stale_90 = [a for a in ages if a["days_open"] >= 90]

    return {
        "total_active": len(active_missions),
        "with_age_data": len(ages),
        "avg_age_days": round(mean(a["days_open"] for a in ages), 1) if ages else None,
        "stale_30d_count": len(stale_30),
        "stale_90d_count": len(stale_90),
        "oldest_missions": ages[:5],
        "stale_30d": stale_30,
    }


def _throughput_analysis(missions: list[dict]) -> dict[str, Any]:
    """Missions closed per week over last 12 weeks."""
    today = date.today()
    weekly: dict[str, int] = defaultdict(int)

    for m in missions:
        if not _is_terminal(m):
            continue
        closed_at = _parse_date(m.get("closed_at"))
        if not closed_at:
            continue
        week_start = (closed_at - timedelta(days=closed_at.weekday())).isoformat()
        weekly[week_start] += 1

    # Only last 12 weeks
    cutoff = today - timedelta(weeks=12)
    recent_weeks = {
        k: v for k, v in weekly.items()
        if date.fromisoformat(k) >= cutoff
    }

    values = list(recent_weeks.values())
    return {
        "weeks_with_closures": len(recent_weeks),
        "avg_closures_per_week": round(mean(values), 2) if values else 0,
        "total_recent_closures": sum(values),
        "weekly_breakdown": dict(sorted(recent_weeks.items())),
        "note": "Only available when migration 0013 closed_at is populated.",
    }


def _closure_quality_analysis(missions: list[dict]) -> dict[str, Any]:
    """Distribution of outcome_rating for closed missions."""
    rated = [m for m in missions if _is_terminal(m) and m.get("outcome_rating") is not None]
    if not rated:
        return {
            "rated_missions": 0,
            "note": "No closure quality ratings available. Rate missions at closure via outcome_rating field.",
        }

    ratings = [int(m["outcome_rating"]) for m in rated]
    dist = Counter(ratings)
    return {
        "rated_missions": len(rated),
        "avg_rating": round(mean(ratings), 2),
        "rating_distribution": {str(k): v for k, v in sorted(dist.items())},
        "excellent_rate": round(sum(1 for r in ratings if r >= 4) / len(ratings) * 100, 1),
        "poor_rate":      round(sum(1 for r in ratings if r <= 2) / len(ratings) * 100, 1),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_mission_analytics() -> dict[str, Any]:
    """
    Compute full mission portfolio analytics.
    Degrades gracefully when schema fields are absent.
    """
    missions = _load_all_missions()

    if not missions:
        return {
            "status": "no_data",
            "note": "No missions found from Supabase or fallback sources.",
            "analytics": {},
            "findings": [],
        }

    cycle_time   = _cycle_time_analysis(missions)
    completion   = _completion_rate_analysis(missions)
    ageing       = _ageing_analysis(missions)
    throughput   = _throughput_analysis(missions)
    quality      = _closure_quality_analysis(missions)
    type_dist    = Counter(
        str(m.get("mission_type", "unclassified") or "unclassified")
        for m in missions
    )
    status_dist  = Counter(str(m.get("status", "unknown")) for m in missions)

    findings = _build_findings(cycle_time, completion, ageing, throughput, quality)

    return {
        "status": "ok",
        "total_missions": len(missions),
        "analytics": {
            "cycle_time":        cycle_time,
            "completion_rate":   completion,
            "ageing":            ageing,
            "throughput":        throughput,
            "closure_quality":   quality,
            "type_distribution": dict(type_dist.most_common()),
            "status_distribution": dict(status_dist.most_common()),
        },
        "findings": findings,
    }


def _build_findings(
    cycle_time: dict,
    completion: dict,
    ageing: dict,
    throughput: dict,
    quality: dict,
) -> list[str]:
    findings = []

    rate = completion.get("overall_completion_rate")
    if rate is not None:
        findings.append(
            f"COMPLETION RATE: {rate}% ({completion['closed']}/{completion['total_missions']} missions closed)"
        )

    avg_cycle = cycle_time.get("avg_days")
    if avg_cycle:
        findings.append(f"CYCLE TIME: Avg {avg_cycle} days (median {cycle_time.get('median_days')} days) to close")

    stale = ageing.get("stale_30d_count", 0)
    if stale:
        findings.append(f"AGEING: {stale} missions open >30 days")

    stale_90 = ageing.get("stale_90d_count", 0)
    if stale_90:
        findings.append(f"CHRONIC STALE: {stale_90} missions open >90 days — escalation review recommended")

    avg_close = throughput.get("avg_closures_per_week")
    if avg_close:
        findings.append(f"THROUGHPUT: {avg_close} missions closed/week (recent 12 weeks)")

    avg_q = quality.get("avg_rating")
    if avg_q:
        findings.append(f"CLOSURE QUALITY: Avg {avg_q}/5 from {quality['rated_missions']} rated closures")

    blocked = completion.get("blocked", 0)
    if blocked:
        findings.append(f"BLOCKED: {blocked} missions currently blocked")

    return findings
