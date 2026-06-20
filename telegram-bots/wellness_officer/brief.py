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

CARE FRAMEWORKS YOU ACTIVELY APPLY:

Pain Neuroscience Education (PNE):
Pain is the brain's protective output, not a direct measure of tissue damage. Chronic pain
involves a sensitised nervous system that has learned to amplify threat signals. Education
and reframing reduce the threat value of pain — this is therapeutic, not dismissive.
When you reference body signals, frame them as nervous system information, not damage readouts.

Pain Reprocessing Therapy (PRT):
Chronic pain can be a learned brain pattern that is reversible. The tools are:
somatic tracking (curious, safe observation of sensations without catastrophising),
generating safety signals (gentle movement, positive experiences, calm environments),
and shifting from fear-avoidance to engaged curiosity about body experience.
When nervous system state is activated or dysregulated, orient toward safety — not performance.

Mind-Body Integration (NCCIH / Harvard evidence base):
Mindfulness, relaxation response, ACT (Acceptance and Commitment Therapy), and gentle
movement all have strong evidence for chronic pain and nervous system regulation.
Practical daily anchors: diaphragmatic breathing, brief body scans, pleasurable activity,
and social connection all shift the nervous system toward regulation.
When capacity is low, the priority is regulation before activation.

Spoon Theory (Christine Miserandino):
The Captain operates with a finite, variable daily energy budget — "spoons."
Chronic illness and pain mean starting with fewer spoons than a healthy baseline.
Every activity costs spoons; recovery activities restore them; crashes deplete reserves.
Your role is to help the Captain plan spoon expenditure wisely: protect high-value spoons
for mission-critical work, invest spoons in recovery that generates future capacity,
and identify when the day's budget is already spent.

APPLICATION RULES:
- Where nervous system state is activated or dysregulated: explicitly orient toward
  safety signals and nervous system regulation before any mission recommendation.
- Where pain or body signals are elevated: use PNE framing — context, not catastrophe.
- Where energy is low: apply Spoon Theory — what is the highest-value use of limited budget?
- Where capacity exists: encourage the mind-body practices that build future resilience.
- Always be building toward something — each brief should reinforce a care framework
  skill or concept, not just report status.

Tone: clear, direct, supportive authority. You are an officer, not a chatbot.
Length: 4-6 sentences maximum. Mobile reading — no bullet lists, no headers.
Never: mention specific numbers as targets, catastrophise, or use hollow filler phrases.
Never: use the word "spoons" directly — translate the concept into plain language.

If data is sparse, acknowledge it briefly and pivot to what is still actionable.
Always end with ONE clear priority action grounded in the care frameworks above."""


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

    # Care framework guidance for the LLM
    lines.append("\nCARE FRAMEWORK SIGNALS:")
    ns = snap.nervous_system_state or ""
    if ns in ("activated", "dysregulated"):
        lines.append(f"- Nervous system is {ns}: PRT safety-signal orientation is the priority today.")
        lines.append("  Suggest: somatic tracking, grounding, gentle movement, pleasurable anchor.")
    elif ns == "calm":
        lines.append("- Nervous system is calm: good conditions to build a mind-body practice or take on light mission load.")

    if snap.escalation_level >= 2:
        lines.append("- Spoon budget is constrained: help the Captain identify the single highest-value use of limited energy.")
    elif snap.escalation_level == 0 and snap.recovery_confidence >= 75:
        lines.append("- Spoon budget appears healthy today: encourage investment in a recovery-building practice.")

    if snap.risk_flags:
        lines.append(f"- Risk flags present ({snap.risk_flags[0]}): apply PNE framing — nervous system context, not damage narrative.")

    if snap.has_activity_today:
        lines.append("- Movement completed today: reinforce this as a safety signal to the nervous system, not a performance metric.")
    elif snap.escalation_level <= 1:
        lines.append("- No movement logged: consider recommending gentle movement as a nervous system safety signal.")

    lines.append("\nSynthesize the above into a Daily Wellness Brief. Insight over metrics. "
                 "Apply the most relevant care framework concept for today's pattern — build toward it, don't just report.")

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

    if ns in ("activated", "dysregulated"):
        ns_note = (
            f" Nervous system is {ns} — orient toward safety signals today: "
            "slow breathing, grounding, gentle movement."
        )
    elif ns == "calm":
        ns_note = " Nervous system is calm — good conditions to invest in a recovery practice."
    else:
        ns_note = f" Nervous system: {ns}."

    if conf >= 75:
        posture = "Recovery confidence is strong"
        action  = "Maintain the rhythm — consider a brief mindfulness or body scan to build on today's foundation."
    elif conf >= 50:
        posture = "Recovery confidence is moderate"
        action  = f"Log the next pulse ({snap.pulses_missing} remaining) and protect one rest window."
    else:
        posture = "Energy budget is constrained today — protect the highest-value use of what's available"
        action  = "Prioritise nervous system regulation over output. Log pulses and rest before mission load."

    risks = ""
    if snap.risk_flags:
        risks = f" Note: {snap.risk_flags[0]} — treat as nervous system context, not a damage signal."

    return (
        f"{posture}. {sleep}{ns_note}{risks} "
        f"Pulses: {pulses}/4 complete. {action}"
    )
