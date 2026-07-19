"""
Weekly Health Intelligence Synthesis — WP2 / Sprint A

Reads the last 7 days of captains_log_entries from Supabase,
produces a structured HealthWeeklySynthesis with:
  - Deterministic metrics (averages, trends, risk/positive flags)
  - 30-day baseline comparison (Sprint A)
  - Deterministic correlation findings (Sprint A)
  - LLM-generated intelligence narrative (Sprint A)

Falls back gracefully at every layer (missing data, LLM unavailable, Supabase down).

Usage (standalone):
    python core/health/weekly_synthesis.py

Usage (from API):
    from core.health.weekly_synthesis import run_synthesis
    result = run_synthesis()

Outputs:
  - Persisted row in health_insights (Supabase — requires migration 0008 for new columns)
  - Optional update to memory/Health-Summary.md
  - Returns enriched dict (all fields always present in return value)
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow sibling imports
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_get, supabase_upsert, is_configured
from capacity_score import compute_capacity_score
from trend_utils import (
    compute_pain_trend,
    compute_sleep_trend,
    compute_capacity_trend,
    encode_energy,
    encode_mood,
    day_of_week_pattern,
    MIN_DAYS_FOR_TREND as _TREND_MIN,
)
from health_llm import HealthLLMProvider, parse_llm_narrative

MIN_DAYS_FOR_SYNTHESIS = 3   # degrade gracefully if < this many entries
MIN_DAYS_FOR_BASELINE  = 14  # minimum entries in 30d window to report a baseline
# MIN_DAYS_FOR_TREND imported from trend_utils as _TREND_MIN

# Columns persisted to Supabase health_insights — filtered before upsert to prevent
# PostgREST 400 errors when migration 0008 has not yet been applied.
_LEGACY_DB_COLS = frozenset({
    "period_start", "period_end", "insight_type", "summary", "week_start",
    "source_table", "days_logged", "pain_scores", "pain_avg", "pain_trend",
    "sleep_avg", "sleep_trend", "energy_modal", "mood_modal", "capacity_avg",
    "capacity_trend", "risk_flags", "positive_flags", "auto_health_status",
    "decisions_extracted", "narrative_summary", "synthesis_version",
    "generated_by", "generated_at",
})
# Columns added by migration 0008 — included when available
_MIGRATION_008_COLS = frozenset({
    "baseline_30d", "baseline_comparison", "deterministic_findings",
    "cpap_compliance_rate", "wins_this_week", "intention_delivery",
    "llm_narrative", "llm_provider", "narrative_available",
})
# Columns added by migration 0009 (Sprint C)
_MIGRATION_009_COLS = frozenset({
    "pain_location_analysis", "mood_trend_30d",
    "recovery_status", "physical_capacity_analysis",
    "dow_pain_pattern", "dow_energy_pattern",
})


# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------

def _fetch_week_entries(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch entries from the unified analytics view (WP-2).
    Falls back to captains_log_entries if the view does not yet exist."""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    try:
        rows = supabase_get(
            f"analytics_health_daily"
            f"?log_date=gte.{since}"
            f"&order=log_date.asc"
            f"&limit={days}"
        )
        return rows
    except Exception:
        # Fallback to captains_log_entries if view not yet deployed
        rows = supabase_get(
            f"captains_log_entries"
            f"?log_date=gte.{since}"
            f"&order=log_date.asc"
            f"&limit={days}"
        )
        return rows


def _modal(values: List[str]) -> Optional[str]:
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Sprint A: 30-day baseline retrieval and comparison
# ---------------------------------------------------------------------------

def _fetch_baseline_entries(days: int = 30) -> List[Dict[str, Any]]:
    """Fetch up to `days` days of entries for baseline computation."""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    try:
        rows = supabase_get(
            f"analytics_health_daily"
            f"?log_date=gte.{since}"
            f"&order=log_date.asc"
            f"&limit={days}"
        )
        return rows
    except Exception:
        try:
            rows = supabase_get(
                f"captains_log_entries"
                f"?log_date=gte.{since}"
                f"&order=log_date.asc"
                f"&limit={days}"
            )
            return rows
        except Exception:
            return []


def _baseline_mean(
    entries: List[Dict[str, Any]],
    field: str,
    encode_fn=None,
) -> Optional[float]:
    """
    Compute mean of `field` across entries.
    If `encode_fn` is provided (e.g. encode_energy), applies it to string values.
    Returns None if fewer than MIN_DAYS_FOR_BASELINE non-null values exist.
    """
    values = []
    for e in entries:
        raw = e.get(field)
        if raw is None:
            continue
        try:
            values.append(encode_fn(raw) if encode_fn else float(raw))
        except (TypeError, ValueError):
            continue
    if len(values) < MIN_DAYS_FOR_BASELINE:
        return None
    return round(sum(values) / len(values), 2)


def _classify_vs_baseline(
    current: Optional[float],
    baseline: Optional[float],
    higher_is_better: bool,
    threshold_pct: float = 0.10,
) -> str:
    """
    Compare current period value to baseline.
    threshold_pct: proportion of baseline that counts as 'above'/'below'.
    Returns: 'above_baseline' | 'below_baseline' | 'aligned' | 'insufficient_data'
    """
    if current is None or baseline is None or baseline == 0:
        return "insufficient_data"
    delta_pct = (current - baseline) / abs(baseline)
    if delta_pct > threshold_pct:
        return "above_baseline" if higher_is_better else "below_baseline"
    if delta_pct < -threshold_pct:
        return "below_baseline" if higher_is_better else "above_baseline"
    return "aligned"


def _compute_baselines(
    baseline_entries: List[Dict[str, Any]],
    current_pain_avg: Optional[float],
    current_sleep_avg: Optional[float],
    current_capacity_avg: Optional[float],
    current_energy_modal: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Compute 30-day baselines and classify current week against them.

    Returns:
        baseline_30d: dict of baseline averages
        baseline_comparison: dict of 'above_baseline'/'below_baseline'/'aligned'/'insufficient_data'
    """
    pain_bl  = _baseline_mean(baseline_entries, "pain_score")
    sleep_bl = _baseline_mean(baseline_entries, "sleep_hours")
    cap_scores = []
    for e in baseline_entries:
        score, _ = compute_capacity_score(e)
        if score is not None:
            cap_scores.append(float(score))
    cap_bl = round(sum(cap_scores) / len(cap_scores), 1) if len(cap_scores) >= MIN_DAYS_FOR_BASELINE else None
    energy_encoded = [encode_energy(e["energy"]) for e in baseline_entries if e.get("energy")]
    energy_bl = (round(sum(energy_encoded) / len(energy_encoded), 2)
                 if len(energy_encoded) >= MIN_DAYS_FOR_BASELINE else None)

    baseline_30d = {
        "pain_avg": pain_bl,
        "sleep_avg": sleep_bl,
        "capacity_avg": cap_bl,
        "energy_avg_encoded": energy_bl,
        "n_days": len(baseline_entries),
    }

    current_energy_encoded = encode_energy(current_energy_modal) if current_energy_modal else None

    baseline_comparison = {
        "pain":     _classify_vs_baseline(current_pain_avg, pain_bl, higher_is_better=False),
        "sleep":    _classify_vs_baseline(current_sleep_avg, sleep_bl, higher_is_better=True),
        "capacity": _classify_vs_baseline(current_capacity_avg, cap_bl, higher_is_better=True),
        "energy":   _classify_vs_baseline(current_energy_encoded, energy_bl, higher_is_better=True),
    }

    return baseline_30d, baseline_comparison


# ---------------------------------------------------------------------------
# Sprint A: Deterministic correlation findings
# ---------------------------------------------------------------------------

def _analyse_cpap(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyse CPAP compliance and next-day energy impact.

    Returns dict with:
      compliance_rate: float (0–1) or None
      compliance_n: int
      compliance_total: int
      next_day_energy_with_cpap: str modal or None
      next_day_energy_without_cpap: str modal or None
      finding: str human-readable finding or None
    """
    cpap_nights_by_energy: Dict[bool, List[str]] = {True: [], False: []}
    compliance_flags: List[bool] = []

    sorted_entries = sorted(entries, key=lambda x: x.get("log_date", ""))

    for i, e in enumerate(sorted_entries):
        raw = e.get("cpap_status")
        if raw is None:
            continue

        # Normalise cpap_status to bool
        if isinstance(raw, bool):
            used = raw
        elif isinstance(raw, str):
            used = raw.strip().lower() in ("yes", "true", "1")
        else:
            used = bool(raw)
        compliance_flags.append(used)

        # Lag-1: check next entry is consecutive date
        if i + 1 < len(sorted_entries):
            next_e = sorted_entries[i + 1]
            try:
                d_curr = date.fromisoformat(str(e["log_date"]))
                d_next = date.fromisoformat(str(next_e["log_date"]))
                if (d_next - d_curr).days == 1 and next_e.get("energy"):
                    cpap_nights_by_energy[used].append(next_e["energy"].capitalize())
            except (KeyError, ValueError):
                pass

    if not compliance_flags:
        return {
            "compliance_rate": None, "compliance_n": 0, "compliance_total": 0,
            "next_day_energy_with_cpap": None, "next_day_energy_without_cpap": None,
            "finding": None,
        }

    compliance_n = sum(1 for f in compliance_flags if f)
    compliance_total = len(compliance_flags)
    compliance_rate = round(compliance_n / compliance_total, 2)

    with_cpap_modal   = _modal(cpap_nights_by_energy[True])
    without_cpap_modal = _modal(cpap_nights_by_energy[False])

    n_with    = len(cpap_nights_by_energy[True])
    n_without = len(cpap_nights_by_energy[False])

    finding = None
    if compliance_total >= 3:
        pct = int(compliance_rate * 100)
        finding = f"CPAP compliance: {compliance_n}/{compliance_total} nights ({pct}%)."
        # Require n≥3 per group before reporting next-day energy comparison (n=1 is misleading)
        if (with_cpap_modal and without_cpap_modal and with_cpap_modal != without_cpap_modal
                and n_with >= 3 and n_without >= 3):
            finding += (
                f" Next-day energy modal: {with_cpap_modal} after CPAP nights"
                f" vs. {without_cpap_modal} after non-CPAP nights"
                f" (n={n_with} vs n={n_without})."
            )
        elif with_cpap_modal and n_with >= 3:
            finding += f" Next-day energy (CPAP nights, n={n_with}): {with_cpap_modal}."

    return {
        "compliance_rate": compliance_rate,
        "compliance_n": compliance_n,
        "compliance_total": compliance_total,
        "next_day_energy_with_cpap": with_cpap_modal,
        "next_day_energy_without_cpap": without_cpap_modal,
        "finding": finding,
    }


def _analyse_sleep_quality(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare sleep_quality against sleep_hours.
    Flags entries where the Captain slept sufficient hours but quality was poor/fair.

    Returns dict with finding string or None.
    """
    long_but_poor: List[str] = []
    quality_dist: Dict[str, int] = {}
    quality_avg_hours: Dict[str, List[float]] = {}

    for e in entries:
        q = (e.get("sleep_quality") or "").strip().lower()
        h = e.get("sleep_hours")
        if not q:
            continue
        quality_dist[q] = quality_dist.get(q, 0) + 1
        if h is not None:
            try:
                h = float(h)
                quality_avg_hours.setdefault(q, []).append(h)
                if q in ("poor", "fair") and h >= 6.5:
                    long_but_poor.append(e.get("log_date", ""))
            except (TypeError, ValueError):
                pass

    avg_by_quality = {
        q: round(sum(hrs) / len(hrs), 1)
        for q, hrs in quality_avg_hours.items()
        if hrs
    }
    total_with_quality = sum(quality_dist.values())

    finding = None
    if total_with_quality >= 3:
        if long_but_poor:
            finding = (
                f"Sleep quality gap: {len(long_but_poor)} night(s) with ≥6.5h sleep rated "
                f"Poor/Fair ({', '.join(long_but_poor)}). Duration is present but quality is not."
            )
        elif "good" in quality_dist:
            good_pct = int(quality_dist["good"] / total_with_quality * 100)
            finding = f"Sleep quality: {good_pct}% of logged nights rated Good."

    return {
        "quality_distribution": quality_dist,
        "avg_hours_by_quality": avg_by_quality,
        "nights_long_but_poor_quality": long_but_poor,
        "finding": finding,
    }


def _analyse_intention_delivery(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare tomorrows_priority (day N) against what_happened (day N+1).
    Computes: how many days had intentions set and how many had a next-day log.

    Returns:
      days_with_intention: int
      days_with_next_entry: int
      pairs: list of {date, intention, next_date, delivered} dicts
      finding: str or None
    """
    sorted_entries = sorted(entries, key=lambda x: x.get("log_date", ""))
    pairs = []
    days_with_intention = 0

    for i, e in enumerate(sorted_entries):
        intention = (e.get("tomorrows_priority") or "").strip()
        if not intention:
            continue
        days_with_intention += 1

        next_log = None
        if i + 1 < len(sorted_entries):
            next_e = sorted_entries[i + 1]
            try:
                d_curr = date.fromisoformat(str(e["log_date"]))
                d_next = date.fromisoformat(str(next_e["log_date"]))
                if (d_next - d_curr).days == 1:
                    next_log = (next_e.get("what_happened") or "").strip()
            except (KeyError, ValueError):
                pass

        pairs.append({
            "date": e.get("log_date", ""),
            "intention": intention,
            "next_date": sorted_entries[i + 1].get("log_date", "") if i + 1 < len(sorted_entries) else None,
            "delivered": next_log,
        })

    days_with_next_entry = sum(1 for p in pairs if p["delivered"])

    finding = None
    if days_with_intention > 0:
        pair_lines = []
        for p in pairs:
            pair_lines.append(f"[{p['date']}] Intended: {p['intention'][:80]}")
        finding = (
            f"Intentions set {days_with_intention} day(s) this week; "
            f"{days_with_next_entry} had a next-day log entry available.\n"
            + "\n".join(f"  • {pl}" for pl in pair_lines)
        )

    return {
        "days_with_intention": days_with_intention,
        "days_with_next_entry": days_with_next_entry,
        "pairs": pairs,
        "finding": finding,
    }


def _extract_wins(entries: List[Dict[str, Any]], n: int = 3) -> List[str]:
    """Extract non-empty wins entries, returning up to n most recent."""
    wins = []
    for e in sorted(entries, key=lambda x: x.get("log_date", ""), reverse=True):
        text = (e.get("wins") or "").strip()
        if text:
            wins.append(f"[{e.get('log_date', '')}] {text}")
        if len(wins) >= n:
            break
    return list(reversed(wins))  # chronological order


def _analyse_statuses(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute distribution and modal for work_status and personal_status."""
    work_dist: Dict[str, int] = {}
    personal_dist: Dict[str, int] = {}
    for e in entries:
        ws = (e.get("work_status") or "").strip()
        ps = (e.get("personal_status") or "").strip()
        if ws:
            work_dist[ws] = work_dist.get(ws, 0) + 1
        if ps:
            personal_dist[ps] = personal_dist.get(ps, 0) + 1

    return {
        "work_status_dist": work_dist,
        "work_status_modal": _modal(list(work_dist.keys()) * 1),  # simple modal via distribution
        "personal_status_dist": personal_dist,
        "personal_status_modal": _modal(list(personal_dist.keys()) * 1),
    }


# ---------------------------------------------------------------------------
# Sprint C: WP2 — Pain Location Intelligence (G-007)
# ---------------------------------------------------------------------------

def _analyse_pain_location(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Frequency analysis of pain_location field across provided entries.

    Normalises case and strips whitespace. Treats empty/None as 'unspecified'.
    Returns: location_counts, most_common, finding.
    """
    counts: Dict[str, int] = {}
    for e in entries:
        raw = (e.get("pain_location") or "").strip()
        loc = raw.lower() if raw else "unspecified"
        counts[loc] = counts.get(loc, 0) + 1

    # Exclude 'unspecified' from the finding
    named = {k: v for k, v in counts.items() if k != "unspecified"}
    if not named:
        return {"location_counts": counts, "most_common": None, "finding": None}

    most_common = max(named, key=lambda k: named[k])
    total_named = sum(named.values())
    pct = int(named[most_common] / total_named * 100) if total_named else 0

    finding = None
    if len(named) == 1:
        finding = f"Pain location: {most_common} reported on all {total_named} logged day(s)."
    elif named[most_common] > 1:
        finding = (
            f"Primary pain location: {most_common} ({named[most_common]}/{total_named} days, {pct}%)."
        )
        other = [k for k in named if k != most_common]
        if other:
            finding += f" Also reported: {', '.join(other)}."

    return {
        "location_counts": counts,
        "most_common": most_common,
        "finding": finding,
    }


# ---------------------------------------------------------------------------
# Sprint C: WP5 — Mood Longitudinal Analysis (G-013)
# ---------------------------------------------------------------------------

def _analyse_mood_longitudinal(
    entries: List[Dict[str, Any]],
    baseline_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Trend mood across the current week and 30-day history.

    Returns: mood_trend_7d, mood_trend_30d, mood_distribution_30d, finding.
    """
    def _mood_values(rows: List[Dict]) -> List[float]:
        result = []
        for e in rows:
            raw = (e.get("mood") or "").strip().lower()
            if raw in ("low", "stable", "positive"):
                result.append(encode_mood(raw))
        return result

    week_vals = _mood_values(entries)
    hist_vals = _mood_values(baseline_entries) if baseline_entries else []

    from trend_utils import compute_trend
    mood_trend_7d  = compute_trend(week_vals, higher_is_better=True) if len(week_vals) >= _TREND_MIN else "insufficient_data"
    mood_trend_30d = compute_trend(hist_vals, higher_is_better=True) if len(hist_vals) >= _TREND_MIN else "insufficient_data"

    dist_30d: Dict[str, int] = {}
    for e in (baseline_entries or []):
        raw = (e.get("mood") or "").strip().lower()
        if raw in ("low", "stable", "positive"):
            dist_30d[raw] = dist_30d.get(raw, 0) + 1

    finding = None
    if mood_trend_30d not in ("insufficient_data",):
        label = {"improving": "improving ↑", "worsening": "declining ↓", "stable": "stable →"}.get(mood_trend_30d, mood_trend_30d)
        finding = f"Mood 30-day trend: {label}."
        if dist_30d:
            modal = max(dist_30d, key=lambda k: dist_30d[k])
            finding += f" Most common mood: {modal} ({dist_30d[modal]}/{sum(dist_30d.values())} days)."

    return {
        "mood_trend_7d": mood_trend_7d,
        "mood_trend_30d": mood_trend_30d,
        "mood_distribution_30d": dist_30d,
        "finding": finding,
    }


# ---------------------------------------------------------------------------
# Sprint C: WP9 — Physical Capacity Trend (G-020)
# ---------------------------------------------------------------------------

_PHYS_CAP_SCORE = {"better": 1, "same": 0, "worse": -1}


def _analyse_physical_capacity_trend(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyse Better/Same/Worse physical_capacity trajectory.

    Converts to +1/0/-1, computes cumulative direction and current streak.
    Returns: trajectory ('improving'|'declining'|'stable'|'insufficient_data'),
             streak (consecutive same-direction entries), distribution, finding.
    """
    scored: List[Tuple[str, int]] = []
    dist: Dict[str, int] = {}
    for e in sorted(entries, key=lambda x: x.get("log_date", "")):
        raw = (e.get("physical_capacity") or "").strip().lower()
        if raw in _PHYS_CAP_SCORE:
            scored.append((e.get("log_date", ""), _PHYS_CAP_SCORE[raw]))
            dist[raw] = dist.get(raw, 0) + 1

    if len(scored) < 2:
        return {"trajectory": "insufficient_data", "streak": 0, "distribution": dist, "finding": None}

    values = [s for _, s in scored]
    total = sum(values)
    trajectory = "improving" if total > 0 else ("declining" if total < 0 else "stable")

    # Streak: consecutive non-improving or non-declining from the tail
    streak_val = values[-1]
    streak = 0
    for v in reversed(values):
        if v == streak_val:
            streak += 1
        else:
            break

    streak_dir = {1: "improving", 0: "stable", -1: "declining"}.get(streak_val, "stable")

    finding = None
    if len(scored) >= 3:
        if trajectory == "declining":
            finding = f"Physical capacity declining over {len(scored)} logged days (net score: {total})."
        elif trajectory == "improving":
            finding = f"Physical capacity improving over {len(scored)} logged days (net score: +{total})."
        if streak >= 2 and streak_dir != "stable":
            streak_text = f" Current streak: {streak} consecutive {streak_dir} days."
            finding = (finding or "") + streak_text

    return {
        "trajectory": trajectory,
        "streak": streak,
        "streak_direction": streak_dir,
        "distribution": dist,
        "finding": finding,
    }


# ---------------------------------------------------------------------------
# Sprint C: WP7 — Recovery Monitoring (G-016)
# ---------------------------------------------------------------------------

_RECOVERY_STATUSES = ("Active Recovery", "Stable", "Declining", "Acute", "Insufficient Data")


def _classify_recovery_status(
    pain_trend: str,
    capacity_trend: str,
    energy_modal: Optional[str],
    physical_capacity_trajectory: str,
    pain_avg: Optional[float],
    n: int,
) -> Dict[str, Any]:
    """
    Classify the Captain's recovery state using existing trend signals.

    Logic:
      Acute:           pain_avg >= 7 OR capacity_trend == 'worsening' + energy Low
      Declining:       pain_trend == 'worsening' OR capacity_trend == 'worsening'
      Active Recovery: pain_trend == 'improving' AND capacity_trend in ('improving','stable')
      Stable:          all trends stable or insufficient data but no acute signals
      Insufficient Data: n < 3

    Returns: status, rationale (list of contributing signals), finding.
    """
    if n < 3:
        return {"status": "Insufficient Data", "rationale": ["fewer than 3 log entries"], "finding": None}

    signals: List[str] = []
    acute = False

    # Acute check — either high absolute pain or compounding worsening signals
    energy_low = (energy_modal or "").lower() == "low"
    if pain_avg is not None and pain_avg >= 7.0:
        signals.append(f"pain avg {pain_avg}/10 ≥ 7 (acute threshold)")
        acute = True
    if capacity_trend == "worsening" and energy_low:
        signals.append("capacity declining + low energy")
        acute = True

    if acute:
        status = "Acute"
    elif pain_trend == "worsening" or capacity_trend == "worsening":
        status = "Declining"
        signals.append(f"pain trend: {pain_trend}, capacity trend: {capacity_trend}")
    elif pain_trend == "improving" and capacity_trend in ("improving", "stable"):
        status = "Active Recovery"
        signals.append(f"pain improving, capacity {capacity_trend}")
        if physical_capacity_trajectory == "improving":
            signals.append("physical capacity also improving")
    else:
        status = "Stable"
        signals.append("no acute or declining signals detected")

    finding = f"Recovery status: {status}."
    if signals:
        finding += f" Signals: {'; '.join(signals)}."

    return {"status": status, "rationale": signals, "finding": finding}


# ---------------------------------------------------------------------------
# Sprint C: WP4 helper — build dated value lists from entries
# ---------------------------------------------------------------------------

def _extract_dated_values(
    entries: List[Dict[str, Any]],
    field: str,
    encode_fn=None,
) -> List[Tuple[str, float]]:
    """Extract (log_date, numeric_value) pairs from entries, optionally encoding strings."""
    pairs: List[Tuple[str, float]] = []
    for e in sorted(entries, key=lambda x: x.get("log_date", "")):
        date_str = e.get("log_date", "")
        raw = e.get(field)
        if raw is None:
            continue
        try:
            val = encode_fn(raw) if encode_fn else float(raw)
            pairs.append((date_str, val))
        except (ValueError, TypeError):
            continue
    return pairs


def _build_deterministic_findings(
    cpap: Dict[str, Any],
    sleep_quality: Dict[str, Any],
    intention: Dict[str, Any],
    baseline_comparison: Dict[str, str],
    pain_avg: Optional[float],
    baseline_30d: Dict[str, Any],
    pain_location: Optional[Dict[str, Any]] = None,
    mood_longitudinal: Optional[Dict[str, Any]] = None,
    recovery: Optional[Dict[str, Any]] = None,
    phys_cap: Optional[Dict[str, Any]] = None,
    dow_pain: Optional[Dict[str, Any]] = None,
    dow_energy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Collect all deterministic findings into a list of human-readable strings."""
    findings: List[str] = []

    # Baseline comparison findings
    pain_bl = baseline_30d.get("pain_avg")
    if pain_avg is not None and pain_bl is not None:
        pct_diff = round((pain_avg - pain_bl) / pain_bl * 100) if pain_bl else 0
        direction = baseline_comparison.get("pain", "insufficient_data")
        if direction == "below_baseline":
            findings.append(
                f"PAIN BELOW BASELINE: avg {pain_avg}/10 vs. 30-day baseline {pain_bl}/10 "
                f"({abs(pct_diff)}% better than baseline)."
            )
        elif direction == "above_baseline":
            findings.append(
                f"PAIN ABOVE BASELINE: avg {pain_avg}/10 vs. 30-day baseline {pain_bl}/10 "
                f"({abs(pct_diff)}% above baseline)."
            )

    # CPAP finding
    if cpap.get("finding"):
        findings.append(cpap["finding"])

    # Sleep quality finding
    if sleep_quality.get("finding"):
        findings.append(sleep_quality["finding"])

    # Intention-delivery finding
    if intention.get("finding"):
        findings.append(intention["finding"])

    # Sprint C findings
    if pain_location and pain_location.get("finding"):
        findings.append(pain_location["finding"])
    if mood_longitudinal and mood_longitudinal.get("finding"):
        findings.append(mood_longitudinal["finding"])
    if recovery and recovery.get("finding"):
        findings.append(recovery["finding"])
    if phys_cap and phys_cap.get("finding"):
        findings.append(phys_cap["finding"])
    if dow_pain and dow_pain.get("finding"):
        findings.append(f"Pain {dow_pain['finding']}")
    if dow_energy and dow_energy.get("finding"):
        findings.append(f"Energy {dow_energy['finding']}")

    return findings


# ---------------------------------------------------------------------------
# Sprint A: LLM prompt construction
# ---------------------------------------------------------------------------

def _build_llm_prompt(
    week_start: str,
    n: int,
    pain_avg: Optional[float],
    pain_trend: str,
    sleep_avg: Optional[float],
    sleep_trend: str,
    energy_modal: Optional[str],
    mood_modal: Optional[str],
    capacity_avg: Optional[float],
    risk_flags: List[str],
    positive_flags: List[str],
    decisions: List[Dict[str, str]],
    baseline_30d: Dict[str, Any],
    baseline_comparison: Dict[str, str],
    deterministic_findings: List[str],
    wins: List[str],
    intention: Dict[str, Any],
    cpap: Dict[str, Any],
    statuses: Dict[str, Any],
) -> str:
    """Build the structured prompt for health LLM narrative generation."""

    def _trend_arrow(t: str) -> str:
        return {"improving": "↓ improving", "worsening": "↑ worsening",
                "stable": "→ stable", "insufficient_data": "— insufficient data"}.get(t, t)

    def _fmt(v, suffix=""): return f"{v}{suffix}" if v is not None else "no data"

    lines = [
        f"WEEKLY HEALTH DATA (week of {week_start}):",
        f"Days logged: {n}/7",
        f"Pain: avg {_fmt(pain_avg, '/10')}, trend: {_trend_arrow(pain_trend)}",
        f"Sleep: avg {_fmt(sleep_avg, 'h')}, trend: {_trend_arrow(sleep_trend)}",
        f"Energy: modal {energy_modal or 'unknown'}",
        f"Mood: modal {mood_modal or 'unknown'}",
        f"Operational capacity: avg {_fmt(capacity_avg, '%')}",
    ]

    if cpap.get("compliance_rate") is not None:
        lines.append(
            f"CPAP: {cpap['compliance_n']}/{cpap['compliance_total']} nights "
            f"({int(cpap['compliance_rate'] * 100)}% compliance)"
        )

    if statuses.get("work_status_dist"):
        dist = ", ".join(f"{k}:{v}" for k, v in statuses["work_status_dist"].items())
        lines.append(f"Work status distribution: {dist}")
    if statuses.get("personal_status_dist"):
        dist = ", ".join(f"{k}:{v}" for k, v in statuses["personal_status_dist"].items())
        lines.append(f"Personal status distribution: {dist}")

    # 30-day baselines
    lines.append("")
    lines.append("30-DAY BASELINES:")
    bl = baseline_30d
    n_bl = bl.get("n_days", 0)
    if n_bl >= MIN_DAYS_FOR_BASELINE:
        pain_bl = bl.get("pain_avg")
        sleep_bl = bl.get("sleep_avg")
        cap_bl = bl.get("capacity_avg")
        lines.append(f"Based on {n_bl} logged days in the past 30 days:")
        if pain_bl is not None:
            cmp = baseline_comparison.get("pain", "?")
            lines.append(f"  Pain: {pain_bl}/10 baseline → this week is {cmp.replace('_', ' ')}")
        if sleep_bl is not None:
            cmp = baseline_comparison.get("sleep", "?")
            lines.append(f"  Sleep: {sleep_bl}h baseline → this week is {cmp.replace('_', ' ')}")
        if cap_bl is not None:
            cmp = baseline_comparison.get("capacity", "?")
            lines.append(f"  Capacity: {cap_bl}% baseline → this week is {cmp.replace('_', ' ')}")
    else:
        lines.append(f"Insufficient baseline data ({n_bl} days — need {MIN_DAYS_FOR_BASELINE}+).")

    # Risk and positive flags
    if risk_flags:
        lines.append("")
        lines.append("RISK FLAGS THIS WEEK:")
        for f in risk_flags:
            lines.append(f"  - {f}")
    if positive_flags:
        lines.append("")
        lines.append("POSITIVE FLAGS THIS WEEK:")
        for f in positive_flags:
            lines.append(f"  - {f}")

    # Deterministic findings
    if deterministic_findings:
        lines.append("")
        lines.append("DETERMINISTIC FINDINGS:")
        for f in deterministic_findings:
            lines.append(f"  - {f}")

    # Wins
    if wins:
        lines.append("")
        lines.append("WINS RECORDED THIS WEEK:")
        for w in wins:
            lines.append(f"  {w}")

    # Intentions vs delivery
    pairs_with_both = [p for p in intention.get("pairs", []) if p.get("intention") and p.get("delivered")]
    if pairs_with_both:
        lines.append("")
        lines.append("INTENTIONS vs DELIVERY (sample pairs):")
        for p in pairs_with_both[:3]:
            lines.append(f"  [{p['date']}] Intended: {p['intention'][:120]}")
            lines.append(f"  [{p['next_date']}] Next day: {p['delivered'][:120]}")

    # Decisions
    if decisions:
        lines.append("")
        lines.append("DECISIONS RECORDED THIS WEEK:")
        for d in decisions:
            lines.append(f"  [{d['date']}] {d['text'][:120]}")

    lines.append("")
    lines.append(
        "Respond with a JSON object containing exactly these keys:\n"
        "{\n"
        '  "situation": "<2-3 sentence summary of this week\'s health picture>",\n'
        '  "patterns_noticed": ["<specific pattern supported by the data>", ...],\n'
        '  "what_it_means": "<interpretation of these patterns for capacity and recovery>",\n'
        '  "recommended_focus": ["<actionable recommendation 1>", "<actionable recommendation 2>"],\n'
        '  "watch_items": ["<thing to watch in the next 7 days>", ...]\n'
        "}\n\n"
        "Only include patterns clearly supported by the data above. "
        "If data is insufficient for a pattern, note the limitation instead of speculating. "
        "Be specific — cite numbers and dates from the data rather than general statements."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sprint A: Combined narrative builder
# ---------------------------------------------------------------------------

def _build_combined_narrative(
    week_start: str,
    n: int,
    auto_status: str,
    pain_avg: Optional[float],
    pain_trend: str,
    sleep_avg: Optional[float],
    sleep_trend: str,
    energy_modal: Optional[str],
    mood_modal: Optional[str],
    capacity_avg: Optional[float],
    risk_flags: List[str],
    positive_flags: List[str],
    decisions: List[Dict[str, str]],
    baseline_30d: Dict[str, Any],
    baseline_comparison: Dict[str, str],
    deterministic_findings: List[str],
    wins: List[str],
    llm_narrative: Optional[Dict[str, Any]],
) -> str:
    """
    Build the final weekly narrative combining deterministic structure with LLM intelligence.
    Falls back to purely deterministic format when llm_narrative is None.
    """
    trend_arrow = lambda t: {"improving": "↓ improving", "worsening": "↑ worsening",
                             "stable": "→ stable", "insufficient_data": "— insufficient data"}.get(t, t)
    fmt = lambda v, s="": f"{v}{s}" if v is not None else "no data"

    lines = [
        f"## Weekly Health Intelligence Brief — w/c {week_start}",
        f"",
        f"**Days logged:** {n}/7 | **Auto status:** {auto_status}",
        f"",
        "### Situation",
    ]

    if llm_narrative and llm_narrative.get("situation"):
        lines.append(llm_narrative["situation"])
    else:
        lines.append(f"- **Pain:** avg {fmt(pain_avg, '/10')} ({trend_arrow(pain_trend)})")
        lines.append(f"- **Sleep:** avg {fmt(sleep_avg, 'h')} ({trend_arrow(sleep_trend)})")
        if energy_modal:
            lines.append(f"- **Energy:** modal {energy_modal}")
        if mood_modal:
            lines.append(f"- **Mood:** modal {mood_modal}")
        if capacity_avg is not None:
            lines.append(f"- **Operational capacity:** avg {capacity_avg}%")

    # Baseline comparison section
    bl_n = baseline_30d.get("n_days", 0)
    if bl_n >= MIN_DAYS_FOR_BASELINE:
        lines += ["", "### 30-Day Baseline Comparison"]
        pain_bl = baseline_30d.get("pain_avg")
        sleep_bl = baseline_30d.get("sleep_avg")
        cap_bl = baseline_30d.get("capacity_avg")
        if pain_avg is not None and pain_bl is not None:
            cmp_str = baseline_comparison.get("pain", "insufficient_data").replace("_", " ")
            pct = round(abs((pain_avg - pain_bl) / pain_bl * 100)) if pain_bl else 0
            lines.append(f"- **Pain:** {pain_avg}/10 vs. {pain_bl}/10 baseline — **{cmp_str}** ({pct}% diff)")
        if sleep_avg is not None and sleep_bl is not None:
            cmp_str = baseline_comparison.get("sleep", "insufficient_data").replace("_", " ")
            pct = round(abs((sleep_avg - sleep_bl) / sleep_bl * 100)) if sleep_bl else 0
            lines.append(f"- **Sleep:** {sleep_avg}h vs. {sleep_bl}h baseline — **{cmp_str}** ({pct}% diff)")
        if capacity_avg is not None and cap_bl is not None:
            cmp_str = baseline_comparison.get("capacity", "insufficient_data").replace("_", " ")
            pct = round(abs((capacity_avg - cap_bl) / cap_bl * 100)) if cap_bl else 0
            lines.append(f"- **Capacity:** {capacity_avg}% vs. {cap_bl}% baseline — **{cmp_str}** ({pct}% diff)")

    # Deterministic findings
    if deterministic_findings:
        lines += ["", "### Findings"]
        for f in deterministic_findings:
            lines.append(f"- {f}")

    # Patterns from LLM
    if llm_narrative and llm_narrative.get("patterns_noticed"):
        lines += ["", "### Patterns Noticed"]
        for p in llm_narrative["patterns_noticed"]:
            lines.append(f"- {p}")

    # Risk indicators
    if risk_flags:
        lines += ["", "### Risk Indicators"]
        for f in risk_flags:
            lines.append(f"- ⚠️ {f}")

    # Positive indicators
    if positive_flags:
        lines += ["", "### Positive Indicators"]
        for f in positive_flags:
            lines.append(f"- ✅ {f}")

    # Wins
    if wins:
        lines += ["", "### Wins This Week"]
        for w in wins:
            lines.append(f"- {w}")

    # What it means (LLM)
    if llm_narrative and llm_narrative.get("what_it_means"):
        lines += ["", "### Intelligence Assessment"]
        lines.append(llm_narrative["what_it_means"])

    # Recommended focus (LLM)
    if llm_narrative and llm_narrative.get("recommended_focus"):
        lines += ["", "### Recommended Focus"]
        for r in llm_narrative["recommended_focus"]:
            lines.append(f"1. {r}")
    else:
        # Deterministic fallback assessment
        lines += ["", "### Assessment"]
        if n < 5:
            lines.append(
                f"Limited data this week ({n}/7 days logged). "
                "Assessment confidence is low — monitor next week."
            )
        elif not risk_flags and positive_flags:
            lines.append("A positive week. Key indicators trending favourably.")
        elif risk_flags and not positive_flags:
            lines.append("A challenging week. Risk indicators present — review capacity and rest requirements.")
        elif risk_flags and positive_flags:
            lines.append("A mixed week. Some positive signals alongside areas requiring attention.")
        else:
            lines.append("Week completed. No strong signals in either direction — monitor next week.")

    # Watch items (LLM)
    if llm_narrative and llm_narrative.get("watch_items"):
        lines += ["", "### Watch Next 7 Days"]
        for w in llm_narrative["watch_items"]:
            lines.append(f"- 👁 {w}")

    # Decisions
    if decisions:
        lines += ["", "### Decisions Recorded This Week"]
        for d in decisions:
            lines.append(f"- [{d['date']}] {d['text']}")

    if llm_narrative:
        lines += ["", f"*Intelligence narrative generated by LLM.*"]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Risk and positive flag detection
# ---------------------------------------------------------------------------

def _detect_risk_flags(entries: List[Dict[str, Any]]) -> List[str]:
    flags: List[str] = []

    pain_scores = [e["pain_score"] for e in entries if e.get("pain_score") is not None]
    sleep_hours = [float(e["sleep_hours"]) for e in entries if e.get("sleep_hours") is not None]

    # 3+ consecutive days pain >= 7
    consecutive_high = 0
    max_consecutive = 0
    for e in sorted(entries, key=lambda x: x["log_date"]):
        p = e.get("pain_score")
        if p is not None and p >= 7:
            consecutive_high += 1
            max_consecutive = max(max_consecutive, consecutive_high)
        else:
            consecutive_high = 0
    if max_consecutive >= 3:
        flags.append(f"HIGH_PAIN_STREAK: {max_consecutive} consecutive days pain ≥7")

    # Average pain >= 6
    if pain_scores and (sum(pain_scores) / len(pain_scores)) >= 6:
        avg = round(sum(pain_scores) / len(pain_scores), 1)
        flags.append(f"HIGH_PAIN_AVERAGE: weekly avg pain {avg}/10")

    # 2+ days sleep < 5h
    poor_sleep_days = sum(1 for h in sleep_hours if h < 5)
    if poor_sleep_days >= 2:
        flags.append(f"POOR_SLEEP: {poor_sleep_days} days with <5h sleep")

    # 3+ days energy Low
    low_energy_days = sum(1 for e in entries if e.get("energy") == "Low")
    if low_energy_days >= 3:
        flags.append(f"LOW_ENERGY_STREAK: {low_energy_days} days with Low energy")

    # Multiple Red health_status days
    red_days = sum(1 for e in entries if e.get("health_status") == "Red")
    if red_days >= 2:
        flags.append(f"HEALTH_STATUS_RED: {red_days} days self-assessed Red")

    # Worsening physical capacity (3+ Worse days)
    worse_days = sum(1 for e in entries if e.get("physical_capacity") == "Worse")
    if worse_days >= 3:
        flags.append(f"CAPACITY_DECLINE: {worse_days} days physical capacity Worse")

    return flags


def _detect_positive_flags(entries: List[Dict[str, Any]], pain_trend_str: str) -> List[str]:
    flags: List[str] = []

    pain_scores = [e["pain_score"] for e in entries if e.get("pain_score") is not None]
    sleep_hours = [float(e["sleep_hours"]) for e in entries if e.get("sleep_hours") is not None]

    if pain_trend_str == "improving":
        flags.append("PAIN_IMPROVING: pain scores trending downward this week")

    # Average pain <= 3
    if pain_scores and (sum(pain_scores) / len(pain_scores)) <= 3:
        avg = round(sum(pain_scores) / len(pain_scores), 1)
        flags.append(f"LOW_PAIN_WEEK: weekly avg pain {avg}/10")

    # 4+ days sleep >= 6h
    good_sleep_days = sum(1 for h in sleep_hours if h >= 6)
    if good_sleep_days >= 4:
        flags.append(f"GOOD_SLEEP: {good_sleep_days} days with ≥6h sleep")

    # 3+ days energy High or Moderate
    high_energy_days = sum(1 for e in entries if e.get("energy") in ("High", "Moderate"))
    if high_energy_days >= 5:
        flags.append(f"SUSTAINED_ENERGY: {high_energy_days} days Moderate or High energy")

    # 3+ Green health status days
    green_days = sum(1 for e in entries if e.get("health_status") == "Green")
    if green_days >= 3:
        flags.append(f"HEALTH_STATUS_GREEN: {green_days} days self-assessed Green")

    # Wins captured on most days
    win_days = sum(1 for e in entries if (e.get("wins") or "").strip())
    if win_days >= 4:
        flags.append(f"WINS_CAPTURED: wins recorded on {win_days} of {len(entries)} days")

    return flags


# ---------------------------------------------------------------------------
# Decision extraction
# ---------------------------------------------------------------------------

def _extract_decisions(entries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Extract non-empty decisions_made entries, returning [{date, text}].
    No parsing or splitting — preserves the raw free-text value.
    """
    decisions = []
    for e in sorted(entries, key=lambda x: x["log_date"]):
        text = (e.get("decisions_made") or "").strip()
        if text:
            decisions.append({"date": e["log_date"], "text": text})
    return decisions


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------

def _build_narrative(
    entries: List[Dict[str, Any]],
    pain_avg: Optional[float],
    pain_trend: str,
    sleep_avg: Optional[float],
    sleep_trend: str,
    energy_modal: Optional[str],
    mood_modal: Optional[str],
    capacity_avg: Optional[float],
    auto_status: str,
    risk_flags: List[str],
    positive_flags: List[str],
    decisions: List[Dict[str, str]],
    week_start: str,
) -> str:
    """Deterministic template narrative — used as fallback when LLM is unavailable."""
    n = len(entries)
    lines = [
        f"## Weekly Health Intelligence Brief — w/c {week_start}",
        f"",
        f"**Days logged:** {n}/7 | **Auto status:** {auto_status}",
        f"",
        "### Situation",
    ]

    pain_str = f"{pain_avg}/10" if pain_avg is not None else "no data"
    trend_arrow = {"improving": "↓ improving", "worsening": "↑ worsening", "stable": "→ stable",
                   "insufficient_data": "— insufficient data"}.get(pain_trend, pain_trend)
    lines.append(f"- **Pain:** avg {pain_str} ({trend_arrow})")

    sleep_str = f"{sleep_avg}h" if sleep_avg is not None else "no data"
    sleep_arrow = {"improving": "↑ improving", "worsening": "↓ worsening", "stable": "→ stable",
                   "insufficient_data": "— insufficient data"}.get(sleep_trend, sleep_trend)
    lines.append(f"- **Sleep:** avg {sleep_str} ({sleep_arrow})")

    if energy_modal:
        lines.append(f"- **Energy:** modal {energy_modal}")
    if mood_modal:
        lines.append(f"- **Mood:** modal {mood_modal}")
    if capacity_avg is not None:
        lines.append(f"- **Operational capacity:** avg {capacity_avg}%")

    if risk_flags:
        lines += ["", "### Risk Indicators"]
        for flag in risk_flags:
            lines.append(f"- ⚠️ {flag}")

    if positive_flags:
        lines += ["", "### Positive Indicators"]
        for flag in positive_flags:
            lines.append(f"- ✅ {flag}")

    if decisions:
        lines += ["", "### Decisions Recorded This Week"]
        for d in decisions:
            lines.append(f"- [{d['date']}] {d['text']}")

    lines += ["", "### Assessment"]
    if n < 5:
        lines.append(
            f"Limited data this week ({n}/7 days logged). "
            "Assessment confidence is low — monitor next week."
        )
    elif not risk_flags and positive_flags:
        lines.append("A positive week. Key indicators trending favourably.")
    elif risk_flags and not positive_flags:
        lines.append("A challenging week. Risk indicators present — review capacity and rest requirements.")
    elif risk_flags and positive_flags:
        lines.append("A mixed week. Some positive signals alongside areas requiring attention.")
    else:
        lines.append("Week completed. No strong signals in either direction — monitor next week.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Auto health status
# ---------------------------------------------------------------------------

def _compute_auto_health_status(
    risk_flags: List[str],
    positive_flags: List[str],
    pain_avg: Optional[float],
    capacity_avg: Optional[float],
) -> str:
    if pain_avg is not None and pain_avg >= 7:
        return "Red"
    if len(risk_flags) >= 3:
        return "Red"
    if len(risk_flags) >= 1 or (pain_avg is not None and pain_avg >= 4):
        return "Amber"
    if capacity_avg is not None and capacity_avg < 55:
        return "Red"
    if capacity_avg is not None and capacity_avg < 80:
        return "Amber"
    if positive_flags and not risk_flags:
        return "Green"
    return "Amber"


# ---------------------------------------------------------------------------
# Health-Summary.md updater
# ---------------------------------------------------------------------------

def _update_health_summary_md(narrative: str, week_start: str) -> None:
    summary_path = _REPO_ROOT / "memory" / "Health-Summary.md"
    if not summary_path.exists():
        return

    raw = summary_path.read_text(encoding="utf-8")

    # Replace or append the Weekly Health Intelligence Brief section
    section_header = "## Weekly Health Intelligence Brief"
    marker = "## 8. Weekly Health Reflection Template"

    new_section = f"\n{narrative}\n\n---\n"

    if section_header in raw:
        # Replace existing brief section
        before, _, after = raw.partition(section_header)
        # Find the next ## heading or end
        next_heading_idx = after.find("\n## ")
        if next_heading_idx != -1:
            after = after[next_heading_idx:]
        else:
            after = ""
        raw = before + narrative + "\n\n---\n" + after
    elif marker in raw:
        before, _, after = raw.partition(marker)
        raw = before + new_section + marker + after
    else:
        raw = raw.rstrip("\n") + "\n\n" + narrative + "\n"

    summary_path.write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main synthesis function
# ---------------------------------------------------------------------------

def run_synthesis(days: int = 7, update_health_summary: bool = True) -> Dict[str, Any]:
    """
    Run weekly synthesis over the last `days` days of captains_log_entries.

    Sprint A additions:
      - 30-day baseline fetch and comparison
      - CPAP, sleep quality, intention-delivery deterministic findings
      - LLM-generated intelligence narrative (with fallback to template)

    Returns the enriched synthesis dict.
    Persists to health_insights table if Supabase is configured.
    New columns (baseline_30d, llm_narrative, etc.) require migration 0008.
    Optionally updates Health-Summary.md.

    Raises RuntimeError if Supabase is not configured and there is no data.
    """
    if not is_configured():
        raise RuntimeError("Supabase not configured — cannot run synthesis")

    entries = _fetch_week_entries(days)

    week_start = (date.today() - timedelta(days=days - 1)).isoformat()
    n = len(entries)

    if n < MIN_DAYS_FOR_SYNTHESIS:
        return {
            "week_start": week_start,
            "days_logged": n,
            "auto_health_status": "Unknown",
            "narrative_summary": (
                f"Insufficient data: only {n} entries in the last {days} days "
                f"(minimum {MIN_DAYS_FOR_SYNTHESIS} required)."
            ),
            "synthesis_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_table": "analytics_health_daily",
            "narrative_available": False,
            "llm_narrative": None,
            "llm_provider": None,
            "baseline_30d": None,
            "baseline_comparison": None,
            "deterministic_findings": [],
        }

    # ── Numeric stats ────────────────────────────────────────────────────────
    pain_values  = [float(e["pain_score"])  for e in entries if e.get("pain_score")  is not None]
    sleep_values = [float(e["sleep_hours"]) for e in entries if e.get("sleep_hours") is not None]

    pain_avg  = round(sum(pain_values)  / len(pain_values),  1) if pain_values  else None
    sleep_avg = round(sum(sleep_values) / len(sleep_values), 1) if sleep_values else None

    pain_trend  = compute_pain_trend(pain_values)
    sleep_trend = compute_sleep_trend(sleep_values)

    energy_modal = _modal([e["energy"] for e in entries if e.get("energy")])
    mood_modal   = _modal([e["mood"]   for e in entries if e.get("mood")])

    # ── Capacity scores ──────────────────────────────────────────────────────
    capacity_scores = []
    for e in entries:
        score, _ = compute_capacity_score(e)
        if score is not None:
            capacity_scores.append(score)

    capacity_avg = round(sum(capacity_scores) / len(capacity_scores), 1) if capacity_scores else None
    capacity_trend = compute_capacity_trend([float(s) for s in capacity_scores])

    # ── Flags ────────────────────────────────────────────────────────────────
    risk_flags     = _detect_risk_flags(entries)
    positive_flags = _detect_positive_flags(entries, pain_trend)
    decisions      = _extract_decisions(entries)
    auto_status    = _compute_auto_health_status(risk_flags, positive_flags, pain_avg, capacity_avg)

    # ── Sprint A: 30-day baseline ────────────────────────────────────────────
    baseline_entries = _fetch_baseline_entries(days=30)
    baseline_30d, baseline_comparison = _compute_baselines(
        baseline_entries, pain_avg, sleep_avg, capacity_avg, energy_modal,
    )

    # ── Sprint A: Deterministic findings ─────────────────────────────────────
    cpap           = _analyse_cpap(entries)
    sleep_quality  = _analyse_sleep_quality(entries)
    intention      = _analyse_intention_delivery(entries)
    wins           = _extract_wins(entries, n=3)
    statuses       = _analyse_statuses(entries)

    # ── Sprint C: New intelligence functions ─────────────────────────────────
    pain_location    = _analyse_pain_location(baseline_entries or entries)
    mood_longitudinal = _analyse_mood_longitudinal(entries, baseline_entries)
    phys_cap         = _analyse_physical_capacity_trend(entries)
    recovery         = _classify_recovery_status(
        pain_trend=pain_trend,
        capacity_trend=capacity_trend,
        energy_modal=energy_modal,
        physical_capacity_trajectory=phys_cap.get("trajectory", "insufficient_data"),
        pain_avg=pain_avg,
        n=n,
    )
    # Day-of-week patterns (uses all baseline history for meaningful sample)
    dated_pain   = _extract_dated_values(baseline_entries or entries, "pain_score")
    dated_energy = _extract_dated_values(baseline_entries or entries, "energy", encode_fn=encode_energy)
    dow_pain   = day_of_week_pattern(dated_pain,   higher_is_better=False)
    dow_energy = day_of_week_pattern(dated_energy, higher_is_better=True)

    deterministic_findings = _build_deterministic_findings(
        cpap, sleep_quality, intention, baseline_comparison, pain_avg, baseline_30d,
        pain_location=pain_location,
        mood_longitudinal=mood_longitudinal,
        recovery=recovery,
        phys_cap=phys_cap,
        dow_pain=dow_pain,
        dow_energy=dow_energy,
    )

    # ── Sprint A: LLM narrative ──────────────────────────────────────────────
    llm_narrative: Optional[Dict[str, Any]] = None
    llm_provider: Optional[str] = None

    try:
        llm_prompt = _build_llm_prompt(
            week_start=week_start, n=n,
            pain_avg=pain_avg, pain_trend=pain_trend,
            sleep_avg=sleep_avg, sleep_trend=sleep_trend,
            energy_modal=energy_modal, mood_modal=mood_modal,
            capacity_avg=capacity_avg,
            risk_flags=risk_flags, positive_flags=positive_flags,
            decisions=decisions,
            baseline_30d=baseline_30d, baseline_comparison=baseline_comparison,
            deterministic_findings=deterministic_findings,
            wins=wins, intention=intention, cpap=cpap, statuses=statuses,
        )
        provider = HealthLLMProvider()
        raw_text, llm_provider = provider.generate(llm_prompt)
        if raw_text:
            llm_narrative = parse_llm_narrative(raw_text)
    except Exception as exc:
        # Non-fatal — synthesis continues with deterministic fallback
        import logging
        logging.getLogger(__name__).warning("LLM narrative generation failed: %s", exc)

    # ── Narrative (combined or deterministic fallback) ────────────────────────
    narrative = _build_combined_narrative(
        week_start=week_start, n=n, auto_status=auto_status,
        pain_avg=pain_avg, pain_trend=pain_trend,
        sleep_avg=sleep_avg, sleep_trend=sleep_trend,
        energy_modal=energy_modal, mood_modal=mood_modal,
        capacity_avg=capacity_avg,
        risk_flags=risk_flags, positive_flags=positive_flags,
        decisions=decisions,
        baseline_30d=baseline_30d, baseline_comparison=baseline_comparison,
        deterministic_findings=deterministic_findings,
        wins=wins,
        llm_narrative=llm_narrative,
    )

    # ── Build insight row ────────────────────────────────────────────────────
    period_end = (date.fromisoformat(week_start) + timedelta(days=6)).isoformat()
    insight: Dict[str, Any] = {
        # Required NOT NULL columns (health_insights schema)
        "period_start": week_start,
        "period_end":   period_end,
        "insight_type": "weekly_summary",
        "summary":      (narrative or "")[:500],
        # Core analytics columns (migration 0005)
        "week_start":   week_start,
        "source_table": "analytics_health_daily",
        "days_logged":  n,
        "pain_scores":  pain_values,
        "pain_avg":     pain_avg,
        "pain_trend":   pain_trend,
        "sleep_avg":    sleep_avg,
        "sleep_trend":  sleep_trend,
        "energy_modal": energy_modal,
        "mood_modal":   mood_modal,
        "capacity_avg": capacity_avg,
        "capacity_trend": capacity_trend,
        "risk_flags":   risk_flags,
        "positive_flags": positive_flags,
        "auto_health_status": auto_status,
        "decisions_extracted": decisions,
        "narrative_summary": narrative,
        "synthesis_version": "3.0",
        "generated_by": "weekly_synthesis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Sprint A additions (migration 0008)
        "baseline_30d":           baseline_30d,
        "baseline_comparison":    baseline_comparison,
        "deterministic_findings": deterministic_findings,
        "cpap_compliance_rate":   cpap.get("compliance_rate"),
        "wins_this_week":         wins,
        "intention_delivery":     {
            "days_with_intention": intention["days_with_intention"],
            "days_with_next_entry": intention["days_with_next_entry"],
        },
        "llm_narrative":     llm_narrative,
        "llm_provider":      llm_provider,
        "narrative_available": llm_narrative is not None,
        # Sprint C additions (migration 0009)
        "pain_location_analysis":  pain_location,
        "mood_trend_30d":          {
            "mood_trend_7d": mood_longitudinal["mood_trend_7d"],
            "mood_trend_30d": mood_longitudinal["mood_trend_30d"],
            "distribution": mood_longitudinal["mood_distribution_30d"],
        },
        "recovery_status":         recovery.get("status"),
        "physical_capacity_analysis": {
            "trajectory": phys_cap.get("trajectory"),
            "streak": phys_cap.get("streak"),
            "streak_direction": phys_cap.get("streak_direction"),
            "distribution": phys_cap.get("distribution"),
        },
        "dow_pain_pattern":        dow_pain if dow_pain.get("status") == "ok" else None,
        "dow_energy_pattern":      dow_energy if dow_energy.get("status") == "ok" else None,
    }

    # ── Persist to Supabase ──────────────────────────────────────────────────
    # Three-stage fallback: try migration 0009 columns → migration 0008 → legacy only
    _all_db_cols = _LEGACY_DB_COLS | _MIGRATION_008_COLS | _MIGRATION_009_COLS
    full_payload   = {k: v for k, v in insight.items() if k in _all_db_cols}
    legacy_payload = {k: v for k, v in insight.items() if k in _LEGACY_DB_COLS}
    try:
        supabase_upsert(
            "health_insights", full_payload,
            on_conflict="period_start,period_end,insight_type",
        )
    except Exception:
        try:
            supabase_upsert(
                "health_insights", legacy_payload,
                on_conflict="period_start,period_end,insight_type",
            )
        except Exception as exc:
            insight["_persist_error"] = str(exc)

    # STARSHIP-REDESIGN.md §4.1: internal jobs are domains too. Best-effort.
    try:
        sys.path.insert(0, str(_REPO_ROOT / "core" / "platform"))
        from heartbeat import record_heartbeat
        if insight.get("_persist_error"):
            record_heartbeat("weekly_health_synthesis", status="failed",
                              error_message=insight["_persist_error"])
        else:
            record_heartbeat("weekly_health_synthesis", status="ok",
                              detail=f"period={week_start}")
    except Exception as _hb_exc:
        pass

    # ── Update Health-Summary.md ─────────────────────────────────────────────
    if update_health_summary:
        try:
            _update_health_summary_md(narrative, week_start)
        except Exception:
            pass

    return insight


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run weekly health intelligence synthesis")
    parser.add_argument("--days", type=int, default=7, help="Days to synthesise (default 7)")
    parser.add_argument("--no-update-md", action="store_true", help="Skip Health-Summary.md update")
    args = parser.parse_args()

    result = run_synthesis(days=args.days, update_health_summary=not args.no_update_md)
    print(json.dumps(result, indent=2, default=str))
