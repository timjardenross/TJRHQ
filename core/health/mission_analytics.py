"""
Mission Time-to-Completion Analytics — WP8 / Sprint C (G-019)

Analyses mission lifecycle durations and completion patterns from the
Supabase missions table.

Note: The missions table uses updated_at as the completion timestamp for
completed missions (no dedicated closed_at column exists as of migration 0009).
Time-to-completion is therefore: updated_at - created_at for completed rows.

Usage:
    from core.health.mission_analytics import analyse_missions
    result = analyse_missions()
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_get, is_configured

log = logging.getLogger(__name__)

MIN_COMPLETED_FOR_ANALYTICS = 3


def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # Handle both Z and +00:00 suffixes
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_to_label(hours: float) -> str:
    if hours < 24:
        return f"{round(hours, 1)}h"
    days = hours / 24
    return f"{round(days, 1)}d"


def analyse_missions() -> Dict[str, Any]:
    """
    Fetch all missions and compute time-to-completion analytics.

    Returns dict with:
        total_missions:         int
        completed:              int
        pending:                int
        analytics_available:    bool
        avg_hours:              float or None
        median_hours:           float or None
        avg_label:              str or None
        median_label:           str or None
        by_task_type:           {type: {avg_hours, n, avg_label}}
        fastest_mission:        {title, hours, task_type} or None
        slowest_mission:        {title, hours, task_type} or None
        findings:               List[str]
        status:                 'ok' | 'insufficient_data' | 'error'
    """
    if not is_configured():
        return _empty("Supabase not configured")

    try:
        missions = supabase_get("missions?limit=500&order=created_at.asc")
    except Exception as exc:
        log.warning("missions fetch failed: %s", exc)
        return _empty(f"Fetch error: {exc}")

    completed = [m for m in missions if m.get("status") == "completed"]
    pending   = [m for m in missions if m.get("status") != "completed"]

    durations: List[float] = []
    by_type: Dict[str, List[float]] = {}
    mission_details: List[Dict] = []

    for m in completed:
        created = _parse_dt(m.get("created_at"))
        updated = _parse_dt(m.get("updated_at"))
        if not created or not updated:
            continue
        hours = (updated - created).total_seconds() / 3600
        if hours < 0:
            continue
        durations.append(hours)
        task_type = (m.get("task_type") or "unknown").strip()
        by_type.setdefault(task_type, []).append(hours)
        mission_details.append({
            "title":     (m.get("title") or m.get("mission_id") or "")[:60],
            "hours":     hours,
            "task_type": task_type,
        })

    if len(durations) < MIN_COMPLETED_FOR_ANALYTICS:
        return {
            "total_missions":     len(missions),
            "completed":          len(completed),
            "pending":            len(pending),
            "analytics_available": False,
            "avg_hours":          None,
            "median_hours":       None,
            "avg_label":          None,
            "median_label":       None,
            "by_task_type":       {},
            "fastest_mission":    None,
            "slowest_mission":    None,
            "findings": [
                f"Mission analytics: {len(completed)} completed missions "
                f"(minimum {MIN_COMPLETED_FOR_ANALYTICS} required for reliable analytics)."
            ],
            "status": "insufficient_data",
        }

    sorted_dur = sorted(durations)
    avg_hours    = sum(durations) / len(durations)
    n = len(sorted_dur)
    median_hours = (
        sorted_dur[n // 2] if n % 2 != 0
        else (sorted_dur[n // 2 - 1] + sorted_dur[n // 2]) / 2
    )

    by_type_analytics = {}
    for task_type, type_hours in by_type.items():
        type_avg = sum(type_hours) / len(type_hours)
        by_type_analytics[task_type] = {
            "n":         len(type_hours),
            "avg_hours": round(type_avg, 1),
            "avg_label": _hours_to_label(type_avg),
        }

    sorted_missions = sorted(mission_details, key=lambda m: m["hours"])
    fastest = sorted_missions[0]  if sorted_missions else None
    slowest = sorted_missions[-1] if sorted_missions else None

    findings = [
        f"Mission completion: {len(completed)} missions completed. "
        f"Average time: {_hours_to_label(avg_hours)}, median: {_hours_to_label(median_hours)}."
    ]
    if by_type_analytics:
        type_lines = [f"{t}: {v['avg_label']} avg (n={v['n']})" for t, v in by_type_analytics.items()]
        findings.append("By type: " + "; ".join(type_lines) + ".")
    if fastest and slowest and fastest["hours"] != slowest["hours"]:
        findings.append(
            f"Fastest: {fastest['title']} ({_hours_to_label(fastest['hours'])}). "
            f"Slowest: {slowest['title']} ({_hours_to_label(slowest['hours'])})."
        )

    return {
        "total_missions":      len(missions),
        "completed":           len(completed),
        "pending":             len(pending),
        "analytics_available": True,
        "avg_hours":           round(avg_hours, 1),
        "median_hours":        round(median_hours, 1),
        "avg_label":           _hours_to_label(avg_hours),
        "median_label":        _hours_to_label(median_hours),
        "by_task_type":        by_type_analytics,
        "fastest_mission":     fastest,
        "slowest_mission":     slowest,
        "findings":            findings,
        "status":              "ok",
    }


def _empty(reason: str) -> Dict[str, Any]:
    return {
        "total_missions": 0, "completed": 0, "pending": 0,
        "analytics_available": False, "avg_hours": None, "median_hours": None,
        "avg_label": None, "median_label": None, "by_task_type": {},
        "fastest_mission": None, "slowest_mission": None,
        "findings": [reason], "status": "error",
    }
