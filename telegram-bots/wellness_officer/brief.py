"""Wellness & Recovery Officer — Daily Brief generator.

Produces insight-over-metrics output grounded in seven care frameworks:
  1. PRT               — pain as learned brain pattern; safety signals
  2. Polyvagal Theory  — NS ladder: ventral / sympathetic / dorsal
  3. ACT               — values-based action despite symptoms
  4. Energy Portfolio  — capacity as investment capital
  5. Operational Resilience — personal governance and tolerable disruption
  6. Spoon Theory      — finite daily energy budget and pacing discipline
  7. Antifragility     — calibrated stressors that build future capacity
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable

from .intelligence import WellnessSnapshot

log = logging.getLogger(__name__)


_WELLNESS_OFFICER_SYSTEM_PROMPT = """\
You are the Wellness & Recovery Officer aboard USS TJR, a personal command vessel.

Your commanding officer is Captain TJR (Tim Jardenross), currently operating under:
- ROS-001 v1.1 Recovery Operating System
- Stage 1: Stabilisation — building baseline before Capacity Restoration
- D-055: Captain Capacity First — recovery gates all mission work

You hold seven care frameworks as active operating models. You do not recite them.
You apply whichever is most relevant to today's data, and you build the Captain's
fluency in them over time — one concept, concretely, per brief.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 1 — PAIN REPROCESSING THERAPY (PRT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Chronic pain is a learned brain output, not a damage signal. The nervous system
has been trained to amplify threat — this is reversible. The tools are:
- Somatic tracking: observe sensations with curious, safe attention (not fear)
- Safety signals: gentle movement, warmth, pleasure, calm environments
- Defusion: "I notice body signals" not "I am in pain"
- Fear-avoidance reversal: engagement with life, not protection from it
When body signals are significant, orient toward safety — not rest-at-all-costs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 2 — POLYVAGAL THEORY (Stephen Porges)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The nervous system has three states. Each needs a different response:

VENTRAL VAGAL (calm): safe, connected, engaged. Good conditions to build,
connect, and take on light mission work. Invest in practices that extend this state.

SYMPATHETIC (activated): fight/flight. Energy is mobilised but dysregulated.
Tools: rhythmic movement to discharge, slow exhale breathing (4-7-8 or box),
cold water on face, bilateral stimulation (tapping), physical grounding.
Do NOT suppress activation — discharge it.

DORSAL VAGAL (dysregulated): shutdown/freeze/collapse. The system has gone
below the window of tolerance. Tools: warmth, small pleasures, gentle social
connection, slow gentle movement, sunlight, food. Micro-doses of safety.
Co-regulation (contact with safe people) is the fastest ladder rung back up.

The goal is to climb the ladder toward ventral — not to jump straight there.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 3 — ACCEPTANCE AND COMMITMENT THERAPY (ACT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Psychological flexibility over symptom elimination. The six processes:
- Acceptance: allow symptoms without struggle (resistance amplifies pain)
- Defusion: thoughts and sensations are events to observe, not facts to obey
- Present moment: engage with what is actually here, not feared future
- Self as context: "I" am not my symptoms or my bad days
- Values: what does the Captain want their life to be about — regardless of symptoms?
- Committed action: small steps toward values even on constrained days

Key question to surface in briefs: "What's one values-aligned action possible today,
given current capacity — not despite it, but calibrated to it?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 4 — ENERGY PORTFOLIO MANAGEMENT (EPM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Daily capacity is investment capital. Think in four categories:
- HIGH-RETURN INVESTMENTS: sleep, CPAP compliance, gentle movement, social connection,
  mindfulness, pleasurable activity — these generate more capacity than they cost
- MISSION SPENDING: focused work, decisions, problem-solving — necessary but depleting
- CAPITAL PRESERVATION: rest windows, pacing, saying no — protect the baseline
- LOW-RETURN DRAINS: worry, resistance, forced productivity when capacity is low,
  perfectionism — cost spoons without producing return

When capacity is constrained, the question is not "what can I get done?" but
"what is the highest-return use of today's available capital?"
When capacity is strong, consider whether to spend on missions or reinvest in recovery.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 5 — OPERATIONAL RESILIENCE (OR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Personal resilience governance. Four pillars:
- IDENTITY/VALUES (People): the Captain's core commitments — what must be protected
- ROUTINES/SYSTEMS (Processes): pulse logging, sleep hygiene, CPAP, movement — the daily ops
- TOOLS/MONITORING (Technology): the bot, LCARS, health logs — visibility infrastructure
- RELATIONSHIPS/SUPPORT (Third Parties): co-regulation sources, care team, trusted others

Three OR concepts to apply:
- Tolerable disruption: what disruptions can the system absorb without breaching recovery posture?
- Recovery time objective: how long does it take to return to baseline after a setback?
- Stress testing: what would breach minimum viable recovery, and how close is the Captain today?

When escalation is high, apply OR lens: which pillar is failing and what's the fastest restore?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 6 — SPOON THEORY (Christine Miserandino)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The Captain operates with a finite, variable daily energy budget.
Chronic illness means starting with fewer units than a healthy baseline.
Every activity has a cost; recovery activities partially restore the budget;
crashes happen when the budget hits zero before the day ends.

Pacing discipline: plan the day's expenditure in advance. Identify the three
highest-value uses of today's budget. Protect reserve for unexpected draws.
Never use tomorrow's budget today — "borrowing" from future days causes crashes.
Do not use the word "spoons" directly — translate into plain language.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK 7 — ANTIFRAGILITY (Nassim Taleb)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fragile systems break under stress. Robust systems resist it. Antifragile systems
improve from it — in the right doses. The goal is not to eliminate all stressors
but to calibrate them: small, recoverable challenges that stimulate adaptation.

Applied here:
- Gentle movement is an antifragile stressor — it generates more capacity than it costs
- Sleep pressure (not napping too late) is antifragile — it improves sleep quality
- Small ACT commitments despite symptoms are antifragile — they train the nervous system
- Forced productivity when dysregulated is fragile — it depletes and doesn't adapt
- Pattern reading: which recent stressors built capacity? Which depleted it?

When 7-day data shows a positive trend: name the antifragile behaviour driving it.
When data shows declining trend: identify the fragile pattern to interrupt.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BRIEF CONSTRUCTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tone: clear, direct, supportive authority. Officer, not chatbot.
Length: 4-6 sentences. Mobile reading — no bullet lists, no headers.
Never: catastrophise, use hollow filler, mention specific targets, say "spoons".
Never: recite a framework by name unless it helps the Captain — show, don't tell.

One framework per brief, applied concretely to today's data.
Always end with ONE priority action — specific, values-aligned, calibrated to today's capacity.
If data is sparse, pivot immediately to what is actionable."""


def build_wellness_brief_prompt(snap: WellnessSnapshot) -> str:
    """Build the LLM prompt from a WellnessSnapshot."""
    today = date.today().strftime("%A, %d %B %Y")
    lines = [f"Daily Wellness Brief — {today}\n"]

    # ── Today's telemetry ─────────────────────────────────────────────────────
    lines.append(f"Recovery confidence: {snap.recovery_confidence}% — {snap.confidence_label}")
    lines.append(f"Pulses logged: {snap.pulses_completed}/4")

    if snap.latest_energy or snap.latest_nervous_system or snap.latest_body_signals:
        signals = ", ".join(filter(None, [
            f"capacity={snap.latest_energy}"              if snap.latest_energy         else None,
            f"nervous_system={snap.latest_nervous_system}" if snap.latest_nervous_system else None,
            f"body_signals={snap.latest_body_signals}"    if snap.latest_body_signals   else None,
        ]))
        lines.append(f"Latest pulse signals: {signals}")

    # ── Daily health log ──────────────────────────────────────────────────────
    if snap.has_daily_log:
        lines.append("")
        if snap.sleep_hours is not None:
            cpap_note = ""
            if snap.cpap_compliant is True:  cpap_note = " (CPAP compliant)"
            if snap.cpap_compliant is False: cpap_note = " (CPAP missed — OR process failure)"
            lines.append(f"Sleep: {snap.sleep_hours}h{cpap_note}")
        if snap.sleep_quality:
            lines.append(f"Sleep quality: {snap.sleep_quality}")
        if snap.nervous_system_state:
            lines.append(f"NS state (check-in): {snap.nervous_system_state}")
        if snap.pain_level:
            lines.append(f"Body signals (check-in): {snap.pain_level} — nervous system context, not damage readout")
        if snap.sitting_tolerance_minutes is not None:
            lines.append(f"Sitting tolerance: {snap.sitting_tolerance_minutes} min")
    else:
        lines.append("\nNo morning check-in recorded yet today.")

    # ── Activity ──────────────────────────────────────────────────────────────
    if snap.has_activity_today:
        acts = ", ".join(
            f"{a['activity_type']}" + (f" {a['duration_minutes']}min" if a.get('duration_minutes') else "")
            for a in snap.activities_today
        )
        lines.append(f"Movement today: {acts} ({snap.activity_minutes_today} min total) — antifragile capital invested")
    else:
        lines.append("Movement today: none logged")

    # ── Weight ────────────────────────────────────────────────────────────────
    if snap.has_weight_data and snap.weight_today_kg:
        direction = ""
        if snap.weight_30d_change_kg is not None:
            direction = f" | 30d: {'↓' if snap.weight_30d_change_kg < 0 else '↑'}{abs(snap.weight_30d_change_kg)}kg"
        lines.append(f"Weight: {snap.weight_today_kg}kg (7d avg {snap.weight_7d_avg_kg}kg{direction})")

    # ── 7-day pattern (Antifragility + EPM) ──────────────────────────────────
    if snap.pulse_history_7d:
        lines.append("")
        lines.append("7-DAY PATTERN:")
        if snap.ns_dysregulated_days_7d:
            lines.append(f"  Dysregulated NS days: {snap.ns_dysregulated_days_7d}/7 — dorsal vagal load")
        if snap.ns_activated_days_7d:
            lines.append(f"  Activated NS days: {snap.ns_activated_days_7d}/7 — sympathetic load")
        if snap.ns_calm_days_7d:
            lines.append(f"  Calm NS days: {snap.ns_calm_days_7d}/7 — ventral vagal days")
        if snap.body_significant_days_7d:
            lines.append(f"  Significant body signal days: {snap.body_significant_days_7d}/7")
        if snap.confidence_trend:
            lines.append(f"  Capacity trend (7d): {snap.confidence_trend}")

    # ── Health insights ───────────────────────────────────────────────────────
    if snap.has_insights:
        lines.append("")
        if snap.insight_date:
            lines.append(f"Medical Officer insights ({snap.insight_date}):")
        if snap.llm_narrative:
            lines.append(f"  Narrative: {snap.llm_narrative}")
        if snap.risk_flags:
            lines.append(f"  Risk flags: {'; '.join(snap.risk_flags)}")
        if snap.positive_flags:
            lines.append(f"  Positive flags: {'; '.join(snap.positive_flags)}")
        if snap.wins_this_week:
            lines.append(f"  Wins: {'; '.join(snap.wins_this_week)}")
        if snap.cpap_compliance_rate is not None:
            lines.append(f"  CPAP compliance (7d): {snap.cpap_compliance_rate:.0%}")

    # ── Care framework signal block ───────────────────────────────────────────
    lines.append("\nCARE FRAMEWORK SIGNALS FOR TODAY:")
    lines.append(f"  Escalation: L{snap.escalation_level} (0=clear 1=watch 2=concern 3=critical)")

    ns = snap.nervous_system_state or snap.latest_nervous_system or ""

    # Polyvagal: state-specific ladder guidance
    if ns == "dysregulated":
        lines.append("  POLYVAGAL: Dorsal vagal state. Do NOT push for productivity.")
        lines.append("  Ladder tools: warmth, micro-pleasures, gentle social contact, sunlight, food.")
    elif ns == "activated":
        lines.append("  POLYVAGAL: Sympathetic state. Discharge before directing.")
        lines.append("  Ladder tools: rhythmic movement, slow exhale breathing, cold water, bilateral tapping.")
    elif ns == "calm":
        lines.append("  POLYVAGAL: Ventral vagal. Good conditions for values-aligned mission work.")

    # PRT: body signal framing
    body = snap.latest_body_signals or ""
    if body == "significant" or snap.pain_level in ("high", "severe", "significant"):
        lines.append("  PRT: Body signals elevated. Apply somatic tracking — curious, safe observation.")
        lines.append("  Frame: nervous system amplification, not damage. Safety signals are the medicine.")
    elif body == "present":
        lines.append("  PRT: Body signals present but manageable. Maintain defusion stance — notice, don't fuse.")

    # ACT: values-based action prompt
    if snap.escalation_level >= 2:
        lines.append("  ACT: Capacity constrained. What is one values-aligned action possible at this level?")
        lines.append("  Accept the constraint — resistance drains more capital than the constraint itself.")
    elif snap.escalation_level == 0:
        lines.append("  ACT: Capacity available. Committed action toward a valued direction is the priority.")

    # EPM: portfolio framing
    if snap.escalation_level >= 2:
        lines.append("  EPM: Capital preservation mode. Protect rest windows. Identify highest-return use of limited budget.")
    elif snap.has_activity_today:
        lines.append("  EPM: Movement completed — high-return capital invested. Protect remaining budget for recovery.")
    else:
        lines.append("  EPM: No movement logged — consider whether gentle movement is the highest-return available action.")

    # OR: governance check
    if snap.escalation_level == 3:
        lines.append("  OR: Tolerable disruption threshold may be breached. Which pillar is failing — routines, rest, support?")
    if snap.cpap_compliant is False:
        lines.append("  OR PROCESS FAILURE: CPAP missed — this is a sleep quality and NS recovery system failure.")

    # Antifragility: pattern reading
    if snap.confidence_trend == "improving":
        lines.append("  ANTIFRAGILITY: Positive trend. Name the behaviour driving it — reinforce the antifragile pattern.")
    elif snap.confidence_trend == "declining":
        lines.append("  ANTIFRAGILITY: Declining trend. Identify the fragile pattern to interrupt before it compounds.")
    if snap.ns_dysregulated_days_7d >= 3:
        lines.append(f"  ANTIFRAGILITY: {snap.ns_dysregulated_days_7d} dysregulated days in 7 — systemic load, not a bad day.")

    lines.append("\nSynthesize into a 4-6 sentence Daily Wellness Brief. Apply ONE framework concretely to today's "
                 "pattern. End with a single specific priority action calibrated to today's capacity and NS state.")

    return "\n".join(lines)


def generate_wellness_brief(
    snap: WellnessSnapshot,
    generate_fn: Callable[[str, str], str | None],
) -> str:
    """Sync wrapper."""
    if not snap.has_any_data:
        return (
            "No health telemetry recorded yet today. "
            "Priority action: log your morning pulse to establish today's baseline."
        )
    result = generate_fn(build_wellness_brief_prompt(snap), _WELLNESS_OFFICER_SYSTEM_PROMPT)
    return result if result else _fallback_brief(snap)


async def generate_wellness_brief_async(
    snap: WellnessSnapshot,
    generate_async_fn: Callable,
) -> str:
    """Async wrapper — pass telegram_bots.llm.generate_async."""
    if not snap.has_any_data:
        return (
            "No health telemetry recorded yet today. "
            "Priority action: log your morning pulse to establish today's baseline."
        )
    result = await generate_async_fn(build_wellness_brief_prompt(snap), _WELLNESS_OFFICER_SYSTEM_PROMPT)
    return result if result else _fallback_brief(snap)


def _fallback_brief(snap: WellnessSnapshot) -> str:
    """Rule-based fallback when LLM is unavailable. Applies care frameworks directly."""
    conf   = snap.recovery_confidence
    pulses = snap.pulses_completed
    ns     = snap.nervous_system_state or snap.latest_nervous_system or "unknown"
    body   = snap.latest_body_signals or ""

    if conf == 0 and pulses == 0:
        return (
            "No recovery telemetry today — operating without a baseline. "
            "Energy budget is untracked, which means mission load decisions are blind. "
            "Priority action: log your morning pulse now to open the day's picture."
        )

    # Polyvagal ladder: NS state drives the response
    if ns == "dysregulated":
        ns_note = (
            "Nervous system is in shutdown — this is dorsal vagal state, not weakness. "
            "The path up is micro-doses of safety: warmth, food, gentle contact, sunlight."
        )
        action = "One micro-pleasure or grounding anchor before any mission activity."
    elif ns == "activated":
        ns_note = (
            "Nervous system is activated — sympathetic mobilisation. "
            "Discharge before directing: slow exhale breathing or short rhythmic movement."
        )
        action = "Five minutes of slow exhale breathing or a short walk to discharge activation."
    elif ns == "calm":
        ns_note = "Nervous system is calm — ventral vagal. Good conditions for values-aligned work."
        action  = "Invest today's available capacity in one high-return activity or committed action."
    else:
        ns_note = ""
        action  = "Log a pulse to establish today's nervous system baseline."

    # Body signals: PRT framing
    body_note = ""
    if body == "significant":
        body_note = (
            " Body signals are significant — apply curious, safe observation. "
            "This is nervous system amplification, not damage."
        )
    elif body == "present":
        body_note = " Body signals are present — maintain defusion, don't fuse with the sensation."

    # EPM: capacity framing
    if conf >= 75:
        portfolio = "Energy portfolio is strong today."
        if not snap.has_activity_today:
            action = "Invest in movement — highest-return capital available at this confidence level."
    elif conf >= 50:
        portfolio = "Energy portfolio is moderate — protect rest windows alongside mission work."
    else:
        portfolio = "Energy budget is constrained — capital preservation mode. Identify the single highest-value use."
        if ns not in ("dysregulated", "activated"):
            action = f"Protect one rest window and log the next pulse ({snap.pulses_missing} remaining)."

    # Antifragility: trend signal
    trend_note = ""
    if snap.confidence_trend == "improving":
        trend_note = " 7-day trend is improving — something is working. Maintain the pattern."
    elif snap.confidence_trend == "declining":
        trend_note = " 7-day trend is declining — identify what's fragile in the current pattern."

    return (
        f"{portfolio}{body_note} {ns_note}{trend_note} "
        f"Pulses: {pulses}/4. {action}"
    ).strip()
