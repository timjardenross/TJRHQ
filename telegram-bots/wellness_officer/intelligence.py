"""Wellness & Recovery Officer — Intelligence layer (Phase 1).

Aggregates data from three Supabase sources into a WellnessSnapshot:
- recovery_confidence_today  (view — today's pulse telemetry)
- health_daily_logs          (table — sleep, pain, nervous system, energy)
- health_insights            (table — LLM narrative, risk/positive flags, wins)

No new tables required. Phase 1 is connection, not construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class WellnessSnapshot:
    # ── Recovery confidence (from recovery_confidence_today view) ──────────────
    recovery_confidence: int         = 0
    pulses_completed:    int         = 0
    pulses_missing:      int         = 4
    morning_done:        bool        = False
    midday_done:         bool        = False
    end_of_day_done:     bool        = False
    evening_done:        bool        = False
    confidence_label:    str         = "No telemetry today"
    latest_energy:         str | None  = None
    latest_nervous_system: str | None  = None
    latest_body_signals:   str | None  = None
    escalation_level:    int         = 0

    # ── Daily health log (from health_daily_logs — today's row) ───────────────
    sleep_hours:              float | None = None
    sleep_quality:            str | None   = None
    cpap_compliant:           bool | None  = None
    pain_level:               str | None   = None   # contextual, not a metric
    nervous_system_state:     str | None   = None   # calm / activated / dysregulated
    sitting_tolerance_minutes: int | None  = None
    mood_log:                 str | None   = None
    energy_log:               str | None   = None
    has_daily_log:            bool         = False

    # ── Activity logs (from activity_logs — today's entries) ─────────────────
    activities_today:     list[dict]       = field(default_factory=list)
    activity_minutes_today: int            = 0
    has_activity_today:   bool             = False

    # ── Weight (from weight_logs — latest + 7-day trend) ──────────────────────
    weight_today_kg:      float | None     = None
    weight_7d_avg_kg:     float | None     = None
    weight_30d_change_kg: float | None     = None
    has_weight_data:      bool             = False

    # ── Health insights (from health_insights — latest row) ───────────────────
    llm_narrative:        str | None       = None
    risk_flags:           list[str]        = field(default_factory=list)
    positive_flags:       list[str]        = field(default_factory=list)
    wins_this_week:       list[str]        = field(default_factory=list)
    cpap_compliance_rate: float | None     = None   # 7-day rolling
    dow_pain_pattern:     str | None       = None
    insight_date:         str | None       = None
    has_insights:         bool             = False

    @property
    def has_any_data(self) -> bool:
        return self.pulses_completed > 0 or self.has_daily_log or self.has_insights


def _parse_array(val: Any) -> list[str]:
    """Coerce Supabase array/null to list[str]."""
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str) and val:
        return [val]
    return []


def get_wellness_snapshot(supabase_client: Any | None = None) -> WellnessSnapshot:
    """Fetch today's wellness state from all three Supabase sources."""
    if supabase_client is None:
        log.warning("[wellness] No Supabase client — returning empty snapshot")
        return WellnessSnapshot()

    snap = WellnessSnapshot()
    today = date.today().isoformat()

    # ── 1. Recovery confidence ────────────────────────────────────────────────
    try:
        res = supabase_client.table("recovery_confidence_today").select("*").execute()
        if res.data:
            r = res.data[0]
            from datetime import datetime
            hour = datetime.now().hour
            conf   = r.get("recovery_confidence", 0)
            pulses = r.get("pulses_completed", 0)

            if conf == 0 and pulses == 0:
                if hour >= 14: esc = 3
                elif hour >= 9: esc = 2
                else: esc = 1
            elif conf <= 25: esc = 2
            elif conf <= 50: esc = 1
            else: esc = 0

            snap.recovery_confidence = conf
            snap.pulses_completed    = pulses
            snap.pulses_missing      = r.get("pulses_missing", 4)
            snap.morning_done        = r.get("morning_done", False)
            snap.midday_done         = r.get("midday_done", False)
            snap.end_of_day_done     = r.get("end_of_day_done", False)
            snap.evening_done        = r.get("evening_done", False)
            snap.confidence_label    = r.get("confidence_label", "Unknown")
            snap.latest_energy         = r.get("latest_energy")
            snap.latest_nervous_system = r.get("latest_nervous_system")
            snap.latest_body_signals   = r.get("latest_body_signals")
            snap.escalation_level    = esc
    except Exception as exc:
        log.error("[wellness] recovery_confidence_today query failed: %s", exc)

    # ── 2. Today's health daily log ───────────────────────────────────────────
    try:
        res = (
            supabase_client.table("health_daily_logs")
            .select(
                "log_date,sleep_hours,sleep_quality,cpap_compliant,"
                "pain_level,nervous_system_state,sitting_tolerance_minutes,"
                "mood,energy"
            )
            .eq("log_date", today)
            .limit(1)
            .execute()
        )
        if res.data:
            r = res.data[0]
            snap.sleep_hours               = r.get("sleep_hours")
            snap.sleep_quality             = r.get("sleep_quality")
            snap.cpap_compliant            = r.get("cpap_compliant")
            snap.pain_level                = r.get("pain_level")
            snap.nervous_system_state      = r.get("nervous_system_state")
            snap.sitting_tolerance_minutes = r.get("sitting_tolerance_minutes")
            snap.mood_log                  = r.get("mood")
            snap.energy_log                = r.get("energy")
            snap.has_daily_log             = True
    except Exception as exc:
        log.error("[wellness] health_daily_logs query failed: %s", exc)

    # ── 3. Today's activity logs ─────────────────────────────────────────────
    try:
        res = (
            supabase_client.table("activity_logs")
            .select("activity_type,duration_minutes,intensity,notes")
            .eq("log_date", today)
            .eq("completed", True)
            .execute()
        )
        if res.data:
            snap.activities_today       = res.data
            snap.activity_minutes_today = sum(r.get("duration_minutes") or 0 for r in res.data)
            snap.has_activity_today     = True
    except Exception as exc:
        log.error("[wellness] activity_logs query failed: %s", exc)

    # ── 4. Weight logs ────────────────────────────────────────────────────────
    try:
        res = (
            supabase_client.table("weight_logs")
            .select("log_date,weight_kg")
            .order("log_date", desc=True)
            .limit(31)
            .execute()
        )
        if res.data:
            snap.has_weight_data = True
            rows = res.data
            # Today
            if rows[0]["log_date"] == today:
                snap.weight_today_kg = float(rows[0]["weight_kg"])
            # 7-day avg
            recent = [float(r["weight_kg"]) for r in rows[:7]]
            if recent:
                snap.weight_7d_avg_kg = round(sum(recent) / len(recent), 2)
            # 30-day change (most recent vs oldest in window)
            if len(rows) >= 2:
                snap.weight_30d_change_kg = round(
                    float(rows[0]["weight_kg"]) - float(rows[-1]["weight_kg"]), 2
                )
    except Exception as exc:
        log.error("[wellness] weight_logs query failed: %s", exc)

    # ── 5. Latest health insights ─────────────────────────────────────────────
    try:
        res = (
            supabase_client.table("health_insights")
            .select(
                "insight_date,llm_narrative,risk_flags,positive_flags,"
                "wins_this_week,cpap_compliance_rate,dow_pain_pattern"
            )
            .order("insight_date", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            r = res.data[0]
            snap.llm_narrative        = r.get("llm_narrative")
            snap.risk_flags           = _parse_array(r.get("risk_flags"))
            snap.positive_flags       = _parse_array(r.get("positive_flags"))
            snap.wins_this_week       = _parse_array(r.get("wins_this_week"))
            snap.cpap_compliance_rate = r.get("cpap_compliance_rate")
            snap.dow_pain_pattern     = r.get("dow_pain_pattern")
            snap.insight_date         = r.get("insight_date")
            snap.has_insights         = True
    except Exception as exc:
        log.error("[wellness] health_insights query failed: %s", exc)

    return snap
