"""
Operating Pattern Intelligence — WP4
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Analyses personal operating patterns:
- Mission activity by weekday
- Decision activity by weekday
- Pain vs productivity patterns
- Energy vs productivity patterns
- Most effective / most constrained operating days
- Answers: "Does the Captain perform more mission work on low-pain days?"

Public API:
    compute_operating_patterns(health_entries, mission_dates, decision_dates) -> dict
    compute_operating_patterns_from_sources() -> dict
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "intelligence"))

try:
    from supabase_client import supabase_get, is_configured
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_health(days: int = 90) -> list[dict[str, Any]]:
    if not _SUPABASE_OK or not is_configured():
        return []
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        return supabase_get(
            f"captains_log_entries?log_date=gte.{since}&order=log_date.asc&limit={days}"
        )
    except Exception:
        return []


def _load_mission_dates_from_supabase() -> dict[str, int]:
    """Returns date_str -> mission_update_count."""
    day_map: dict[str, int] = defaultdict(int)
    if not _SUPABASE_OK or not is_configured():
        return day_map
    try:
        missions = supabase_get("missions?order=updated_at.desc&limit=500")
        for m in missions:
            upd = (m.get("updated_at") or "")[:10]
            if upd:
                day_map[upd] += 1
    except Exception:
        pass
    return day_map


def _load_decision_dates() -> list[str]:
    """Returns list of date strings for each decision log."""
    decisions_dir = _REPO_ROOT / "logs" / "decisions"
    dates = []
    for f in decisions_dir.glob("*.json"):
        # Filename: YYYYMMDD-HHMMSS-... extract date
        name = f.stem
        try:
            raw_date = name[:8]
            d = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
            dates.append(d.isoformat())
        except (ValueError, IndexError):
            try:
                data = json.loads(f.read_text())
                ts = data.get("timestamp", "")[:10]
                if ts:
                    dates.append(ts)
            except Exception:
                pass
    return dates


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------

_ENERGY_NUM = {"low": 1, "moderate": 2, "high": 3}


def _enc_energy(v: Any) -> int | None:
    if v is None:
        return None
    return _ENERGY_NUM.get(str(v).lower().strip())


def _pain(e: dict) -> float | None:
    v = e.get("pain_score")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _weekday(day_str: str) -> str | None:
    try:
        return _WEEKDAYS[date.fromisoformat(day_str[:10]).weekday()]
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Pattern computations
# ---------------------------------------------------------------------------

def _mission_by_weekday(
    health_entries: list[dict],
    mission_dates: dict[str, int],
) -> dict[str, dict]:
    by_dow: dict[str, list[int]] = defaultdict(list)
    for entry in health_entries:
        day = str(entry.get("log_date", ""))[:10]
        wd  = _weekday(day)
        if wd:
            by_dow[wd].append(mission_dates.get(day, 0))
    return {
        wd: {
            "n_days": len(vals),
            "avg_mission_updates": round(mean(vals), 2) if vals else 0,
            "total_mission_updates": sum(vals),
            "active_days": sum(1 for v in vals if v > 0),
        }
        for wd, vals in by_dow.items()
    }


def _decision_by_weekday(decision_dates: list[str]) -> dict[str, int]:
    by_dow: Counter = Counter()
    for d in decision_dates:
        wd = _weekday(d)
        if wd:
            by_dow[wd] += 1
    return dict(by_dow)


def _pain_vs_productivity(
    health_entries: list[dict],
    mission_dates: dict[str, int],
) -> dict[str, Any]:
    buckets: dict[str, list[int]] = {"low_pain": [], "moderate_pain": [], "high_pain": []}
    for entry in health_entries:
        day = str(entry.get("log_date", ""))[:10]
        pain = _pain(entry)
        if pain is None:
            continue
        n_missions = mission_dates.get(day, 0)
        if pain < 4:
            buckets["low_pain"].append(n_missions)
        elif pain < 7:
            buckets["moderate_pain"].append(n_missions)
        else:
            buckets["high_pain"].append(n_missions)

    result = {}
    for bucket, vals in buckets.items():
        result[bucket] = {
            "n_days": len(vals),
            "avg_mission_updates": round(mean(vals), 2) if vals else None,
        }

    low  = result["low_pain"]["avg_mission_updates"]
    high = result["high_pain"]["avg_mission_updates"]
    if low is not None and high is not None and high > 0:
        pct  = round((low - high) / high * 100, 1)
        answer = (
            f"Yes — {low:.1f} missions/day on low-pain days vs {high:.1f} on high-pain days "
            f"(+{pct}% more activity when pain<4)"
            if low > high else
            f"No clear difference — {low:.1f} vs {high:.1f} missions/day (low vs high pain)"
        )
    else:
        answer = "Insufficient data to determine pain-productivity relationship."
    result["answer"] = answer
    return result


def _energy_vs_productivity(
    health_entries: list[dict],
    mission_dates: dict[str, int],
) -> dict[str, Any]:
    buckets: dict[str, list[int]] = {"Low": [], "Moderate": [], "High": []}
    for entry in health_entries:
        day    = str(entry.get("log_date", ""))[:10]
        energy = str(entry.get("energy") or "").capitalize()
        if energy not in buckets:
            continue
        n = mission_dates.get(day, 0)
        buckets[energy].append(n)

    return {
        level: {
            "n_days": len(vals),
            "avg_mission_updates": round(mean(vals), 2) if vals else None,
        }
        for level, vals in buckets.items()
    }


def _rank_weekdays(
    mission_by_dow: dict[str, dict],
    decision_by_dow: dict[str, int],
) -> dict[str, Any]:
    combined: list[tuple[str, float]] = []
    for wd in _WEEKDAYS:
        m = mission_by_dow.get(wd, {}).get("avg_mission_updates", 0) or 0
        d = decision_by_dow.get(wd, 0)
        score = m + (d * 0.5)  # decisions weighted at half mission value
        combined.append((wd, score))

    combined.sort(key=lambda x: x[1], reverse=True)
    most_effective    = [wd for wd, s in combined[:2] if s > 0]
    most_constrained  = [wd for wd, s in combined[-2:] if s == 0 or combined[-1][1] < combined[0][1] * 0.3]

    return {
        "ranked_weekdays": [{"day": wd, "productivity_score": round(s, 2)} for wd, s in combined],
        "most_effective_days": most_effective,
        "most_constrained_days": most_constrained,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_operating_patterns(
    health_entries: list[dict[str, Any]],
    mission_dates: dict[str, int],
    decision_dates: list[str],
) -> dict[str, Any]:
    """
    Compute personal operating patterns from provided data.
    All three arguments can be empty; results degrade gracefully.
    """
    if len(health_entries) < 5:
        return {
            "status": "insufficient_data",
            "n_health_entries": len(health_entries),
            "note": "Minimum 5 health entries required for operating pattern analysis.",
            "patterns": {},
            "findings": [],
        }

    mission_by_dow   = _mission_by_weekday(health_entries, mission_dates)
    decision_by_dow  = _decision_by_weekday(decision_dates)
    pain_productivity = _pain_vs_productivity(health_entries, mission_dates)
    energy_productivity = _energy_vs_productivity(health_entries, mission_dates)
    rankings = _rank_weekdays(mission_by_dow, decision_by_dow)

    findings = _build_findings(pain_productivity, energy_productivity, rankings, mission_by_dow)

    return {
        "status": "ok",
        "n_health_entries": len(health_entries),
        "n_decision_records": len(decision_dates),
        "n_mission_days_tracked": len(mission_dates),
        "patterns": {
            "mission_activity_by_weekday": mission_by_dow,
            "decision_activity_by_weekday": decision_by_dow,
            "pain_vs_productivity": pain_productivity,
            "energy_vs_productivity": energy_productivity,
            "weekday_rankings": rankings,
        },
        "most_effective_days": rankings["most_effective_days"],
        "most_constrained_days": rankings["most_constrained_days"],
        "findings": findings,
    }


def compute_operating_patterns_from_sources(days: int = 90) -> dict[str, Any]:
    """Convenience wrapper that fetches all data from configured sources."""
    health        = _load_health(days)
    mission_dates = _load_mission_dates_from_supabase()
    decision_dates = _load_decision_dates()
    return compute_operating_patterns(health, mission_dates, decision_dates)


def _build_findings(
    pain_prod: dict,
    energy_prod: dict,
    rankings: dict,
    mission_by_dow: dict,
) -> list[str]:
    findings = []

    # Pain productivity answer
    if pain_prod.get("answer"):
        findings.append(f"PAIN-PRODUCTIVITY: {pain_prod['answer']}")

    # Energy productivity
    low  = (energy_prod.get("Low")  or {}).get("avg_mission_updates")
    high = (energy_prod.get("High") or {}).get("avg_mission_updates")
    if low is not None and high is not None:
        diff = round(high - low, 2)
        findings.append(
            f"ENERGY-PRODUCTIVITY: High energy → {high:.1f} missions/day vs Low → {low:.1f} "
            f"({'+' if diff >= 0 else ''}{diff:.1f} delta)"
        )

    # Best/worst days
    if rankings["most_effective_days"]:
        findings.append(f"BEST OPERATING DAYS: {', '.join(rankings['most_effective_days'])}")
    if rankings["most_constrained_days"]:
        findings.append(f"MOST CONSTRAINED DAYS: {', '.join(rankings['most_constrained_days'])}")

    # Top mission day
    top = max(mission_by_dow.items(), key=lambda x: x[1].get("avg_mission_updates", 0), default=None)
    if top and top[1].get("avg_mission_updates", 0) > 0:
        findings.append(
            f"PEAK MISSION DAY: {top[0]} (avg {top[1]['avg_mission_updates']} mission updates)"
        )

    return findings
