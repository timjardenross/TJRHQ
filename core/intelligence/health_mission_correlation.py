"""
Health × Mission Correlation Engine — WP2
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Correlates health state with mission activity:
- Pain vs mission activity / completion
- Energy vs mission activity / completion
- Sleep vs mission throughput
- CPAP vs productivity
- Readiness score vs mission activity

Data sources:
- captains_log_entries (Supabase) — health fields per date
- missions (Supabase) — updated_at timestamps
- outputs/daily_brief.json — fallback mission list

Public API:
    compute_health_mission_correlations() -> dict
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

try:
    from supabase_client import supabase_get, is_configured
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def _fetch_health_entries(days: int = 90) -> list[dict[str, Any]]:
    if not _SUPABASE_OK or not is_configured():
        return []
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = supabase_get(
            f"captains_log_entries?log_date=gte.{since}&order=log_date.asc&limit={days}"
        )
        return rows
    except Exception:
        try:
            return supabase_get(
                f"analytics_health_daily?log_date=gte.{since}&order=log_date.asc&limit={days}"
            )
        except Exception:
            return []


def _fetch_mission_dates() -> dict[str, list[str]]:
    """Returns dict of date_str -> list of mission_ids updated on that date."""
    day_map: dict[str, list[str]] = defaultdict(list)

    if _SUPABASE_OK and is_configured():
        try:
            missions = supabase_get("missions?order=updated_at.desc&limit=500")
            for m in missions:
                upd = m.get("updated_at") or ""
                if upd:
                    day = upd[:10]
                    day_map[day].append(m.get("id", "?"))
        except Exception:
            pass

    # Fallback: daily_brief.json top_priorities updated timestamps
    brief_path = _REPO_ROOT / "outputs" / "daily_brief.json"
    if not day_map and brief_path.exists():
        try:
            data = json.loads(brief_path.read_text())
            for item in data.get("top_priorities", []):
                # Use "timestamp" from the brief itself as proxy
                ts = data.get("timestamp", "")[:10]
                if ts:
                    day_map[ts].append(item.get("mission_id", "?"))
        except Exception:
            pass

    return day_map


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

_ENERGY_NUM = {"low": 1, "moderate": 2, "high": 3}
_MOOD_NUM   = {"low": 1, "stable": 2, "positive": 3}


def _enc_energy(v: Any) -> int | None:
    if v is None:
        return None
    return _ENERGY_NUM.get(str(v).lower().strip())


def _enc_mood(v: Any) -> int | None:
    if v is None:
        return None
    return _MOOD_NUM.get(str(v).lower().strip())


def _pain(e: dict) -> float | None:
    v = e.get("pain_score")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _sleep(e: dict) -> float | None:
    v = e.get("sleep_hours")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _cpap_used(e: dict) -> bool | None:
    raw = e.get("cpap_status") or e.get("cpap_used")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    return str(raw).lower().strip() in ("yes", "true", "1")


# ---------------------------------------------------------------------------
# Correlation computation
# ---------------------------------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom_x = sum((x - mx) ** 2 for x in xs) ** 0.5
    denom_y = sum((y - my) ** 2 for y in ys) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return None
    return round(num / (denom_x * denom_y), 3)


def _interpret(r: float | None) -> str:
    if r is None:
        return "insufficient_data"
    a = abs(r)
    direction = "positive" if r > 0 else "negative"
    if a >= 0.7:
        return f"strong_{direction}"
    if a >= 0.4:
        return f"moderate_{direction}"
    if a >= 0.2:
        return f"weak_{direction}"
    return "negligible"


def _mission_count_by_date(mission_dates: dict[str, list[str]], day: str) -> int:
    return len(mission_dates.get(day, []))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_health_mission_correlations(days: int = 90) -> dict[str, Any]:
    """
    Compute correlations between health state and mission activity.

    Returns structured dict with per-correlation results and narrative findings.
    """
    health = _fetch_health_entries(days)
    mission_dates = _fetch_mission_dates()

    if len(health) < 3:
        return {
            "status": "insufficient_data",
            "n_health_entries": len(health),
            "note": f"Minimum 3 health entries required; found {len(health)}.",
            "correlations": {},
            "findings": [],
        }

    # ── Build paired arrays ─────────────────────────────────────────────────
    paired: list[dict[str, Any]] = []
    for entry in health:
        day = str(entry.get("log_date", ""))[:10]
        if not day:
            continue
        n_missions = _mission_count_by_date(mission_dates, day)
        # Lag-1: next day mission activity
        next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat() if day else None
        n_missions_next = _mission_count_by_date(mission_dates, next_day) if next_day else 0

        paired.append({
            "date": day,
            "pain": _pain(entry),
            "energy": _enc_energy(entry.get("energy")),
            "sleep": _sleep(entry),
            "cpap": _cpap_used(entry),
            "mood": _enc_mood(entry.get("mood")),
            "n_missions": n_missions,
            "n_missions_next": n_missions_next,
            "active": n_missions > 0,
        })

    def _pairs(x_key: str, y_key: str) -> tuple[list[float], list[float]]:
        xs, ys = [], []
        for p in paired:
            x, y = p.get(x_key), p.get(y_key)
            if x is not None and y is not None:
                xs.append(float(x))
                ys.append(float(y))
        return xs, ys

    correlations: dict[str, dict] = {}

    # Pain × mission activity (same day)
    xs, ys = _pairs("pain", "n_missions")
    r = _pearson(xs, ys)
    correlations["pain_vs_mission_activity"] = {
        "r": r, "interpretation": _interpret(r), "n": len(xs),
        "note": "Negative r → higher pain, fewer mission updates",
    }

    # Energy × mission activity
    xs, ys = _pairs("energy", "n_missions")
    r = _pearson(xs, ys)
    correlations["energy_vs_mission_activity"] = {
        "r": r, "interpretation": _interpret(r), "n": len(xs),
        "note": "Positive r → higher energy, more mission updates",
    }

    # Sleep × next-day mission activity (lag 1)
    xs, ys = _pairs("sleep", "n_missions_next")
    r = _pearson(xs, ys)
    correlations["sleep_vs_next_day_mission_activity"] = {
        "r": r, "interpretation": _interpret(r), "n": len(xs),
        "note": "Lag-1: sleep hours tonight vs mission updates tomorrow",
    }

    # CPAP × next-day mission activity
    cpap_pairs = [(p["cpap"], p["n_missions_next"]) for p in paired
                  if p["cpap"] is not None and p["n_missions_next"] is not None]
    if len(cpap_pairs) >= 3:
        cpap_activity = {True: [], False: []}
        for used, n in cpap_pairs:
            cpap_activity[used].append(n)
        with_cpap    = round(mean(cpap_activity[True]), 2) if cpap_activity[True] else None
        without_cpap = round(mean(cpap_activity[False]), 2) if cpap_activity[False] else None
        correlations["cpap_vs_next_day_productivity"] = {
            "avg_missions_with_cpap": with_cpap,
            "avg_missions_without_cpap": without_cpap,
            "n": len(cpap_pairs),
            "interpretation": (
                "cpap_positive" if (with_cpap and without_cpap and with_cpap > without_cpap)
                else "cpap_neutral_or_negative" if (with_cpap and without_cpap)
                else "insufficient_data"
            ),
            "note": "Average mission updates following CPAP vs non-CPAP nights",
        }

    # Mood × mission activity
    xs, ys = _pairs("mood", "n_missions")
    r = _pearson(xs, ys)
    correlations["mood_vs_mission_activity"] = {
        "r": r, "interpretation": _interpret(r), "n": len(xs),
        "note": "Positive r → better mood, more mission activity",
    }

    # ── Pain low vs high days — mission activity comparison ─────────────────
    low_pain_days  = [p for p in paired if p["pain"] is not None and p["pain"] < 4]
    high_pain_days = [p for p in paired if p["pain"] is not None and p["pain"] >= 7]

    low_pain_activity  = round(mean(p["n_missions"] for p in low_pain_days), 2) if low_pain_days else None
    high_pain_activity = round(mean(p["n_missions"] for p in high_pain_days), 2) if high_pain_days else None

    pain_productivity_answer = None
    if low_pain_activity is not None and high_pain_activity is not None:
        diff = round(low_pain_activity - high_pain_activity, 2)
        pct  = round(diff / max(high_pain_activity, 0.01) * 100, 1)
        pain_productivity_answer = (
            f"Yes — Captain updates {diff:.1f} more missions on low-pain days (pain<4) "
            f"vs high-pain days (pain≥7): avg {low_pain_activity} vs {high_pain_activity} "
            f"(+{pct}% more activity on low-pain days)"
            if diff > 0 else
            f"No significant difference — {low_pain_activity} vs {high_pain_activity} missions/day "
            f"on low vs high pain days"
        )

    # ── Narrative findings ───────────────────────────────────────────────────
    findings = _generate_findings(correlations, pain_productivity_answer, len(health), len(mission_dates))

    return {
        "status": "ok",
        "n_health_entries": len(health),
        "n_mission_days": len(mission_dates),
        "n_paired": len(paired),
        "correlations": correlations,
        "low_pain_avg_missions": low_pain_activity,
        "high_pain_avg_missions": high_pain_activity,
        "pain_productivity_question": "Does the Captain perform more mission work on low-pain days?",
        "pain_productivity_answer": pain_productivity_answer,
        "findings": findings,
    }


def _generate_findings(
    corr: dict[str, dict],
    pain_answer: str | None,
    n_health: int,
    n_mission_days: int,
) -> list[str]:
    findings = []
    if pain_answer:
        findings.append(f"PAIN-PRODUCTIVITY: {pain_answer}")

    for key, label in [
        ("pain_vs_mission_activity", "PAIN→ACTIVITY"),
        ("energy_vs_mission_activity", "ENERGY→ACTIVITY"),
        ("sleep_vs_next_day_mission_activity", "SLEEP→NEXT-DAY ACTIVITY"),
    ]:
        c = corr.get(key, {})
        r = c.get("r")
        interp = c.get("interpretation", "")
        n = c.get("n", 0)
        if r is not None and n >= 3:
            findings.append(f"{label}: r={r} ({interp}, n={n})")

    cpap = corr.get("cpap_vs_next_day_productivity", {})
    if cpap.get("interpretation") not in (None, "insufficient_data"):
        findings.append(
            f"CPAP→PRODUCTIVITY: avg {cpap.get('avg_missions_with_cpap')} missions after CPAP nights "
            f"vs {cpap.get('avg_missions_without_cpap')} without ({cpap.get('interpretation')})"
        )

    if n_health < 14:
        findings.append(f"NOTE: Only {n_health} health entries. Correlations improve with >14 days.")
    if n_mission_days < 5:
        findings.append("NOTE: Mission date data sparse — correlations may understate relationships.")

    return findings
