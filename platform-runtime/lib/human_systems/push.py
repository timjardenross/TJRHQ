"""Human Systems — Proactive Push Intelligence (HSF-001 §7.2).

Scheduler- and event-friendly generators that turn logged data into concise,
evidence-informed proactive output. Each generator is pure: it takes data in and
returns a ``PushMessage`` (or None when there's nothing worth surfacing), so it
can be unit-tested and wired to any delivery surface (Slack DM, Telegram, push).

Output is labelled by doctrine class: information | trend | risk_signal | action.
Red-flag escalation always overrides a routine push.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean

from . import framework, safety


def _pick(*variants: str) -> str:
    """Return a variant deterministically by day — cycles through all, no repeat within len(variants) days."""
    return variants[date.today().toordinal() % len(variants)]


@dataclass
class PushMessage:
    kind: str            # readiness | reflection | weekly_review | degradation | escalation
    output_class: str    # one of safety.OUTPUT_CLASSES
    title: str
    body: str
    severity: str = "info"   # info | notice | warning | urgent
    raw: bool = False        # composed briefs render their own header — skip the class-label head

    def render(self) -> str:
        """Render to a single Captain-facing string with class label + footer."""
        with_footer = self.kind != "escalation"
        if self.raw:
            return safety.frame(self.body, with_footer=with_footer)
        head = f"{safety.label_output_class(self.output_class)}  *{self.title}*"
        return safety.frame(f"{head}\n\n{self.body}", with_footer=with_footer)


def _escalation_push(text: str | None) -> PushMessage | None:
    hits = safety.scan_red_flags(text)
    banner = safety.escalation_banner(hits)
    if not banner:
        return None
    return PushMessage(
        kind="escalation",
        output_class="action",
        title="Please involve a professional",
        body=banner,
        severity="urgent" if any(h.urgent for h in hits) else "warning",
    )


# ── Morning readiness pulse ───────────────────────────────────────────────────

def morning_readiness_pulse(today_row: dict | None, *, recommendation: str | None = None,
                            delivery_note: str | None = None) -> PushMessage:
    """A concise morning read of today's capacity and what fits.

    ``recommendation`` (HSF-002) — the single highest-leverage action.
    ``delivery_note`` (EDO-003 WP1) — a one-line delivery-intelligence summary,
    appended only when there's something worth flagging. Both plain text so
    push.py stays decoupled from the decision/delivery engines.
    """
    esc = _escalation_push((today_row or {}).get("notes"))
    if esc:
        return esc

    snap = framework.interpret_capacity(today_row)
    domain_line = " · ".join(f"{d.label} {d.band}" for d in snap.domains)
    if not snap.data_available:
        body = (
            "No check-in logged yet. A quick `/health-check` would let the system "
            "calibrate today's plan. In the meantime, consider an easy start."
        )
        oclass = "information"
    else:
        next_step = (
            f"*Highest-leverage today:* {recommendation}"
            if recommendation
            else "A practical next step could be choosing one anchor for the day and "
                 "pacing the rest around it."
        )
        delivery_line = f"\n\n*Delivery:* {delivery_note}" if delivery_note else ""
        body = (
            f"{snap.headline}\n\n"
            f"*Capacity by domain:* {domain_line}\n\n"
            f"{next_step}{delivery_line}"
        )
        oclass = "risk_signal" if snap.overall_band in ("limited", "depleted") else "information"
    return PushMessage(
        kind="readiness",
        output_class=oclass,
        title="Morning Readiness Pulse",
        body=body,
        severity="notice" if snap.overall_band in ("limited", "depleted") else "info",
    )


# ── Evening recovery reflection ───────────────────────────────────────────────

def evening_recovery_reflection(today_row: dict | None) -> PushMessage:
    """A gentle end-of-day reflection and recovery prompt."""
    esc = _escalation_push((today_row or {}).get("notes"))
    if esc:
        return esc

    snap = framework.interpret_capacity(today_row)
    if not snap.data_available:
        body = _pick(
            "However today went, it counts. Consider a short wind-down — a "
            "consistent sleep time does more for tomorrow's capacity than almost "
            "anything else.",
            "The body doesn't reset on a schedule, but a consistent sleep window "
            "gives it the best chance. One small action before bed goes a long way.",
            "Rest isn't the absence of effort — it's where adaptation happens. "
            "A quiet close to the evening helps the system consolidate.",
            "There's no such thing as a perfect recovery day. What matters is the "
            "direction: a brief wind-down, screens down, consistent sleep time.",
            "Tonight's recovery starts now. A consistent bedtime does more for "
            "tomorrow than most productivity tactics.",
        )
    else:
        emo = snap.domain("emotional")
        if emo and emo.band in ("limited", "depleted"):
            tone = _pick(
                "Today asked a lot of the nervous system — be gentle with the evening.",
                "The emotional load today was real. The evening's job is to lower the "
                "activation level, not extend the effort.",
                "High nervous system cost today. Gentle inputs only from here — "
                "low stimulation, consistent routine, early enough sleep.",
            )
        else:
            tone = _pick(
                "A steady evening will help tomorrow start well.",
                "Capacity held well today. Protecting the close-out is what keeps "
                "the trend going.",
                "Good day by the numbers. The evening is where tomorrow's capacity "
                "gets built — worth treating it deliberately.",
            )
        action = _pick(
            "Consider one recovery action before bed: a wind-down routine, a brief "
            "reset, or simply protecting your sleep window. Recovery is not repair "
            "— it's giving the system room to settle.",
            "A short wind-down — consistent light, no screens, same sleep time — "
            "does more than most supplements. Small and consistent beats large and occasional.",
            "One thing worth doing: set tomorrow's first task before you sleep. "
            "It stops the brain from drafting plans at 2am.",
            "Recovery is upstream of performance. Tonight's inputs set tomorrow's baseline.",
            "Even 20 minutes of low-stimulation wind-down before sleep measurably "
            "improves the next day's cognitive baseline.",
        )
        body = f"{tone}\n\n{action}"
    return PushMessage(
        kind="reflection",
        output_class="action",
        title="Evening Recovery Reflection",
        body=body,
        severity="info",
    )


# ── Midday capacity check ─────────────────────────────────────────────────────

def midday_capacity_check(today_row: dict | None) -> PushMessage:
    """A brief midday signal-check — how is capacity holding through the day."""
    esc = _escalation_push((today_row or {}).get("notes"))
    if esc:
        return esc

    snap = framework.interpret_capacity(today_row)
    if not snap.data_available:
        body = _pick(
            "No morning check-in logged. A `/health-check` now would give the "
            "afternoon a calibrated baseline — even a rough one is useful.",
            "No baseline logged yet. A quick `/health-check` takes under a minute "
            "and helps the system understand how today is tracking.",
            "Without a morning pulse, the afternoon runs on instinct rather than data. "
            "A check-in now is still worth doing.",
            "Midday checkpoint. No telemetry logged today — a `/health-check` now "
            "would at least anchor the second half.",
            "The midpoint of the day is a useful recalibration window even without data. "
            "How does your energy feel compared to this morning?",
        )
        oclass = "information"
    else:
        cog = snap.domain("mind")
        low_domains = [d for d in snap.domains if d.band in ("limited", "depleted")]
        if low_domains:
            names = ", ".join(d.label for d in low_domains)
            tone = _pick(
                f"{names} {'is' if len(low_domains) == 1 else 'are'} running low "
                f"at the midpoint — this is the window to reduce load, not push through.",
                f"{names} {'is' if len(low_domains) == 1 else 'are'} flagging at midday. "
                f"Cutting scope now costs less than burning through the reserves.",
                f"The data shows {names.lower()} under pressure. Midday is the last "
                f"low-cost moment to adjust the afternoon's load.",
            )
            oclass = "risk_signal"
        elif cog and cog.band == "moderate":
            tone = _pick(
                "Cognitive load is moderate. A short break now (even 5 minutes) "
                "tends to extend useful focus further than grinding through.",
                "Mind is at moderate capacity. This is often the point where a "
                "5-minute reset returns more than 30 minutes of forced effort.",
                "Focus is holding but not fully loaded. A brief deliberate break "
                "here is investment, not procrastination.",
            )
            oclass = "information"
        else:
            tone = _pick(
                f"Capacity is holding at *{snap.overall_band}*. "
                "Good time to check if the afternoon's work still matches today's energy.",
                f"System reading *{snap.overall_band}* at midday. "
                "Worth a moment to confirm the afternoon plan is still right-sized.",
                f"*{snap.overall_band.capitalize()}* at the halfway mark. "
                "The afternoon is yours to shape — does what's left match what you have?",
            )
            oclass = "information"
        question = _pick(
            "One question worth asking: is what's left on today's list appropriate "
            "for what the system actually has?",
            "A useful midday check: does the afternoon's plan still match today's capacity?",
            "Worth a moment: what on today's list is truly necessary, and what can wait?",
        )
        body = f"{tone}\n\n{question}"
    return PushMessage(
        kind="midday_check",
        output_class=oclass,
        title="Midday Capacity Check",
        body=body,
        severity="notice" if oclass == "risk_signal" else "info",
    )


# ── End-of-workday transition ─────────────────────────────────────────────────

def end_of_workday_transition(today_row: dict | None) -> PushMessage:
    """Mark the close of the workday and prompt a deliberate shift to recovery mode."""
    esc = _escalation_push((today_row or {}).get("notes"))
    if esc:
        return esc

    snap = framework.interpret_capacity(today_row)
    if not snap.data_available:
        body = _pick(
            "The workday window is closing. Even without logged data, a deliberate "
            "close-out — noting one thing done and one thing to carry forward — "
            "helps the brain stop processing work in the background.",
            "Marking the end of work is a skill. Without a formal close-out, the "
            "brain keeps problem-solving in the background. One minute of deliberate "
            "shutdown helps.",
            "The boundary between work and recovery doesn't draw itself. A brief "
            "close-out ritual — note what's done, set aside what isn't — creates "
            "the transition.",
            "Close-outs aren't about getting everything done — they're about getting "
            "clear. One thing completed, one thing parked for tomorrow.",
            "No recovery data today, but the hour is the same. A deliberate end to "
            "the workday is worth doing regardless of how it tracked.",
        )
    else:
        if snap.overall_band in ("limited", "depleted"):
            transition_note = _pick(
                "Today ran at reduced capacity. The close-out matters more, not "
                "less — the nervous system needs a clear signal that work is done.",
                "Low capacity day. The transition to recovery mode is especially "
                "important tonight — don't let work bleed into the evening.",
                "The system ran limited today. A clean close-out is the first "
                "recovery action, not the last work action.",
            )
        else:
            transition_note = _pick(
                f"Today held *{snap.overall_band}* across the day. "
                "Close it deliberately so recovery starts clean.",
                f"*{snap.overall_band.capitalize()}* capacity day. "
                "Worth closing properly — good days are built on good recovery.",
                f"Solid reading across the day (*{snap.overall_band}*). "
                "A clean handoff from work to recovery keeps the trend going.",
            )
        close_out = _pick(
            "Consider a one-minute close-out: note the most important thing still "
            "open, set it aside until tomorrow, then step away from screens. "
            "The transition is the work — it's what makes recovery actually recover.",
            "One-minute close-out: write down the one open loop that matters most, "
            "then close the tab. That act tells the brain it's held.",
            "A simple ritual: what's done, what's parked, screens down. "
            "The brain needs a signal — give it one.",
            "Write tomorrow's first task before you stop. It offloads the planning "
            "from tonight's sleep and makes the morning faster.",
            "The close-out doesn't need to be long — it needs to be deliberate. "
            "Thirty seconds of intention is enough to mark the boundary.",
        )
        body = f"{transition_note}\n\n{close_out}"
    return PushMessage(
        kind="eod_transition",
        output_class="action",
        title="End-of-Workday Transition",
        body=body,
        severity="info",
    )


# ── Capacity degradation alert (leading indicator) ────────────────────────────

def capacity_degradation_alert(recent_rows: list[dict]) -> PushMessage | None:
    """Warn early when capacity is trending down or recovery debt is building.

    Returns None when there's no actionable signal — a routine that fires only
    when it matters. Expects several recent daily rows (any order).
    """
    if not recent_rows or len(recent_rows) < 3:
        return None

    ordered = sorted(recent_rows, key=lambda r: str(r.get("log_date") or ""))
    scores = [framework.interpret_capacity(r).overall_score for r in ordered]
    first_half = mean(scores[: max(1, len(scores) // 2)])
    second_half = mean(scores[len(scores) // 2:])
    delta = second_half - first_half

    # Recovery debt: consecutive recent limited/depleted days.
    recent_bands = [framework.interpret_capacity(r).overall_band for r in ordered[-3:]]
    low_run = all(b in ("limited", "depleted") for b in recent_bands)

    # Sleep debt signal.
    sleep_vals = []
    for r in ordered[-4:]:
        sh = r.get("sleep_hours")
        if sh is not None:
            try:
                sleep_vals.append(float(sh))
            except (TypeError, ValueError):
                pass
    sleep_debt = bool(sleep_vals) and mean(sleep_vals) < 6.0

    if not (delta <= -8 or low_run or sleep_debt):
        return None

    reasons = []
    if delta <= -8:
        reasons.append("capacity has trended down over recent days")
    if low_run:
        reasons.append("the last few days have run limited or low")
    if sleep_debt:
        reasons.append(f"sleep has averaged under 6h ({mean(sleep_vals):.1f}h)")

    body = (
        "Based on the pattern, " + "; ".join(reasons) + ".\n\n"
        "This is a signal to review capacity before it costs more — not a verdict "
        "on the day. A practical next step could be deliberately lightening "
        "tomorrow's load and protecting one real recovery window. If this keeps "
        "building, consider whether anything structural needs to change."
    )
    return PushMessage(
        kind="degradation",
        output_class="risk_signal",
        title="Capacity Degradation Alert",
        body=body,
        severity="warning",
    )


# ── Weekly Human Systems Review push ──────────────────────────────────────────

def weekly_human_systems_review(recent_rows: list[dict]) -> PushMessage:
    body = framework.weekly_review(recent_rows)
    return PushMessage(
        kind="weekly_review",
        output_class="trend",
        title="Weekly Human Systems Review",
        body=body,
        severity="info",
    )
