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
from statistics import mean

from . import framework, safety


@dataclass
class PushMessage:
    kind: str            # readiness | reflection | weekly_review | degradation | escalation
    output_class: str    # one of safety.OUTPUT_CLASSES
    title: str
    body: str
    severity: str = "info"   # info | notice | warning | urgent

    def render(self) -> str:
        """Render to a single Captain-facing string with class label + footer."""
        head = f"{safety.label_output_class(self.output_class)}  *{self.title}*"
        with_footer = self.kind != "escalation"
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
        body = (
            "However today went, it counts. Consider a short wind-down — a "
            "consistent sleep time does more for tomorrow's capacity than almost "
            "anything else."
        )
    else:
        emo = snap.domain("emotional")
        tone = (
            "Today asked a lot of the nervous system — be gentle with the evening."
            if emo and emo.band in ("limited", "depleted")
            else "A steady evening will help tomorrow start well."
        )
        body = (
            f"{tone}\n\n"
            "Consider one recovery action before bed: a wind-down routine, a brief "
            "reset, or simply protecting your sleep window. Recovery is not repair "
            "— it's giving the system room to settle."
        )
    return PushMessage(
        kind="reflection",
        output_class="action",
        title="Evening Recovery Reflection",
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
