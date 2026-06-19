"""Wellness & Recovery Officer — Daily Brief generator (Phase 1).

Produces insight-over-metrics output. The question answered daily:
"What does the Captain need to know today about their health, wellness,
recovery, resilience, and operational readiness, and what actions would
have the greatest positive impact?"
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Callable

from .intelligence import WellnessSnapshot

log = logging.getLogger(__name__)

_WELLNESS_OFFICER_SYSTEM_PROMPT = """\
You are the Wellness & Recovery Officer aboard USS TJR, a personal command vessel.

Your commanding officer is Captain TJR (Tim Jardenross), currently operating under:
- ROS-001 v1.1 Recovery Operating System
- Stage 1: Stabilisation (building baseline recovery before Capacity Restoration)
- D-055: Captain Capacity First — recovery gates all mission work

Your role is to produce a concise Daily Wellness Brief. This is NOT a data dump.
It is an intelligent synthesis: what does this data mean for the Captain today?

Tone: clear, direct, supportive authority. You are an officer, not a chatbot.
Length: 4-6 sentences maximum. Mobile reading — no bullet lists, no headers.
Never: mention specific numbers as targets, catastrophise, or use hollow filler phrases.

If data is sparse, acknowledge it briefly and pivot to what is still actionable.
Always end with ONE clear priority action for the day — specific, not generic."""


def build_wellness_brief_prompt(snap: WellnessSnapshot) -> str:
    """Build the LLM prompt from a WellnessSnapshot."""
    today = date.today().strftime("%A, %d %B %Y")
    lines = [f"Daily Wellness Brief for {today}\n"]

    # Recovery telemetry
    lines.append(f"Recovery confidence: {snap.recovery_confidence}% — {snap.confidence_label}")
    lines.append(f"Pulses logged today: {snap.pulses_completed}/4")
    if snap.latest_energy or snap.latest_mood or snap.latest_stress:
        signals = ", ".join(filter(None, [
            f"energy={snap.latest_energy}" if snap.latest_energy else None,
            f"mood={snap.latest_mood}"     if snap.latest_mood   else None,
            f"stress={snap.latest_stress}" if snap.latest_stress else None,
        ]))
        lines.append(f"Latest signals: {signals}")

    # Daily health log
    if snap.has_daily_log:
        lines.append("")
        if snap.sleep_hours is not None:
            cpap_note = ""
            if snap.cpap_compliant is True:  cpap_note = " (CPAP compliant)"
            if snap.cpap_compliant is False: cpap_note = " (CPAP missed)"
            lines.append(f"Sleep last night: {snap.sleep_hours}h{cpap_note}")
        if snap.sleep_quality:
            lines.append(f"Sleep quality: {snap.sleep_quality}")
        if snap.nervous_system_state:
            lines.append(f"Nervous system: {snap.nervous_system_state}")
        if snap.pain_level:
            lines.append(f"Body signals: {snap.pain_level} (context only — not a metric)")
        if snap.sitting_tolerance_minutes is not None:
            lines.append(f"Sitting tolerance: {snap.sitting_tolerance_minutes} min")
    else:
        lines.append("\nNo health daily log recorded today yet.")

    # Activity today
    if snap.has_activity_today:
        acts = ", ".join(
            f"{a['activity_type']}" + (f" {a['duration_minutes']}min" if a.get('duration_minutes') else "")
            for a in snap.activities_today
        )
        lines.append(f"Activity today: {acts} (total {snap.activity_minutes_today} min)")
    else:
        lines.append("Activity today: none logged")

    # Weight
    if snap.has_weight_data:
        lines.append("")
        if snap.weight_today_kg:
            lines.append(f"Weight today: {snap.weight_today_kg} kg")
        if snap.weight_7d_avg_kg:
            lines.append(f"7-day avg: {snap.weight_7d_avg_kg} kg")
        if snap.weight_30d_change_kg is not None:
            direction = "down" if snap.weight_30d_change_kg < 0 else "up"
            lines.append(f"30-day trend: {direction} {abs(snap.weight_30d_change_kg)} kg")

    # Health insights (LLM narrative from Supabase engine)
    if snap.has_insights:
        lines.append("")
        if snap.insight_date:
            lines.append(f"Health insights (as of {snap.insight_date}):")
        if snap.llm_narrative:
            lines.append(f"Medical Officer narrative: {snap.llm_narrative}")
        if snap.risk_flags:
            lines.append(f"Risk flags: {'; '.join(snap.risk_flags)}")
        if snap.positive_flags:
            lines.append(f"Positive flags: {'; '.join(snap.positive_flags)}")
        if snap.wins_this_week:
            lines.append(f"Wins this week: {'; '.join(snap.wins_this_week)}")
        if snap.cpap_compliance_rate is not None:
            lines.append(f"CPAP compliance (7d): {snap.cpap_compliance_rate:.0%}")
        if snap.dow_pain_pattern:
            lines.append(f"Day-of-week pain pattern: {snap.dow_pain_pattern}")
    else:
        lines.append("\nNo health insights available yet.")

    lines.append(f"\nEscalation level: L{snap.escalation_level} (0=clear 1=watch 2=concern 3=critical)")
    lines.append("\nSynthesize the above into a Daily Wellness Brief. Insight over metrics.")

    return "\n".join(lines)


def generate_wellness_brief(
    snap: WellnessSnapshot,
    generate_fn: Callable[[str, str], str | None],
) -> str:
    """Generate a Wellness Brief using the provided LLM function (sync)."""
    if not snap.has_any_data:
        return (
            "No health telemetry logged yet today. "
            "Priority action: log your morning pulse to establish today's baseline."
        )

    prompt = build_wellness_brief_prompt(snap)
    result = generate_fn(prompt, _WELLNESS_OFFICER_SYSTEM_PROMPT)

    if not result:
        return _fallback_brief(snap)
    return result


async def generate_wellness_brief_async(
    snap: WellnessSnapshot,
    generate_async_fn: Callable,
) -> str:
    """Async wrapper — pass telegram_bots.llm.generate_async."""
    if not snap.has_any_data:
        return (
            "No health telemetry logged yet today. "
            "Priority action: log your morning pulse to establish today's baseline."
        )

    prompt = build_wellness_brief_prompt(snap)
    result = await generate_async_fn(prompt, _WELLNESS_OFFICER_SYSTEM_PROMPT)

    if not result:
        return _fallback_brief(snap)
    return result


def _fallback_brief(snap: WellnessSnapshot) -> str:
    """Rule-based fallback when LLM is unavailable."""
    conf = snap.recovery_confidence
    pulses = snap.pulses_completed

    if conf == 0 and pulses == 0:
        return (
            "No recovery telemetry recorded today. "
            "Baseline is unavailable — mission planning is operating blind. "
            "Priority action: log your morning pulse now."
        )

    ns = snap.nervous_system_state or "unknown"
    sleep = f"{snap.sleep_hours}h sleep · " if snap.sleep_hours else ""

    if conf >= 75:
        posture = "Recovery confidence is strong"
        action  = "Maintain current recovery rhythm — pulses are working."
    elif conf >= 50:
        posture = "Recovery confidence is moderate"
        action  = f"Log the next pulse ({snap.pulses_missing} remaining) to maintain momentum."
    else:
        posture = "Recovery confidence is low — capacity is constrained"
        action  = "Protect rest windows and log pulses before taking on new mission load."

    risks = ""
    if snap.risk_flags:
        risks = f" Risk flags present: {snap.risk_flags[0]}."

    return (
        f"{posture}. {sleep}Nervous system: {ns}.{risks} "
        f"Pulses: {pulses}/4 complete. {action}"
    )
