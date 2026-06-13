"""
Weekly Health Intelligence Synthesis — WP2

Reads the last 7 days of captains_log_entries from Supabase,
produces a structured HealthWeeklySynthesis, and persists it to health_insights.

Usage (standalone):
    python core/health/weekly_synthesis.py

Usage (from API):
    from core.health.weekly_synthesis import run_synthesis
    result = run_synthesis()

Outputs:
  - Persisted row in health_insights (Supabase)
  - Optional update to memory/Health-Summary.md
  - Returns dict matching the health_insights schema additions
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
    MIN_DAYS_FOR_TREND as _TREND_MIN,
)

MIN_DAYS_FOR_SYNTHESIS = 3   # degrade gracefully if < this many entries
# MIN_DAYS_FOR_TREND imported from trend_utils as _TREND_MIN


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

    # Summary sentence
    lines += ["", "### Assessment"]
    if not risk_flags and positive_flags:
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

    Returns the synthesised insight dict (matches health_insights schema).
    Persists to health_insights table if Supabase is configured.
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
            "narrative_summary": f"Insufficient data: only {n} entries in the last {days} days (minimum {MIN_DAYS_FOR_SYNTHESIS} required).",
            "synthesis_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_table": "analytics_health_daily",
        }

    # ── Numeric stats ────────────────────────────────────────────────────────
    pain_values = [float(e["pain_score"]) for e in entries if e.get("pain_score") is not None]
    sleep_values = [float(e["sleep_hours"]) for e in entries if e.get("sleep_hours") is not None]

    pain_avg = round(sum(pain_values) / len(pain_values), 1) if pain_values else None
    sleep_avg = round(sum(sleep_values) / len(sleep_values), 1) if sleep_values else None

    pain_trend = compute_pain_trend(pain_values)
    sleep_trend = compute_sleep_trend(sleep_values)

    energy_modal = _modal([e["energy"] for e in entries if e.get("energy")])
    mood_modal = _modal([e["mood"] for e in entries if e.get("mood")])

    # ── Capacity scores ──────────────────────────────────────────────────────
    capacity_scores = []
    for e in entries:
        score, _ = compute_capacity_score(e)
        if score is not None:
            capacity_scores.append(score)

    capacity_avg = round(sum(capacity_scores) / len(capacity_scores), 1) if capacity_scores else None
    capacity_trend_vals = [float(s) for s in capacity_scores]
    capacity_trend = compute_capacity_trend(capacity_trend_vals)

    # ── Flags ────────────────────────────────────────────────────────────────
    risk_flags = _detect_risk_flags(entries)
    positive_flags = _detect_positive_flags(entries, pain_trend)
    decisions = _extract_decisions(entries)
    auto_status = _compute_auto_health_status(risk_flags, positive_flags, pain_avg, capacity_avg)

    # ── Narrative ────────────────────────────────────────────────────────────
    narrative = _build_narrative(
        entries, pain_avg, pain_trend, sleep_avg, sleep_trend,
        energy_modal, mood_modal, capacity_avg, auto_status,
        risk_flags, positive_flags, decisions, week_start,
    )

    # ── Build insight row ────────────────────────────────────────────────────
    insight = {
        "week_start": week_start,
        "source_table": "analytics_health_daily",
        "days_logged": n,
        "pain_scores": pain_values,
        "pain_avg": pain_avg,
        "pain_trend": pain_trend,
        "sleep_avg": sleep_avg,
        "sleep_trend": sleep_trend,
        "energy_modal": energy_modal,
        "mood_modal": mood_modal,
        "capacity_avg": capacity_avg,
        "capacity_trend": capacity_trend,
        "risk_flags": risk_flags,
        "positive_flags": positive_flags,
        "auto_health_status": auto_status,
        "decisions_extracted": decisions,
        "narrative_summary": narrative,
        "synthesis_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── Persist to Supabase ──────────────────────────────────────────────────
    try:
        supabase_upsert("health_insights", insight, on_conflict="week_start")
    except Exception as exc:
        insight["_persist_error"] = str(exc)

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
