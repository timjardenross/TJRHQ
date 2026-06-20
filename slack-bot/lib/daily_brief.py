"""Captain's Daily Operating Picture (MSN-XO-002 WP1).

ONE flagship brief that composes the *existing* Human Systems and EDO engines —
it builds no new analytics. Pure: takes already-fetched parts and returns the
brief string, so it is fully testable and the command/scheduler just gather data.

Answers, in one concise executive briefing: What matters today? Why? What should
I do? What can wait? Framed by the four line officers (XO-001 structure).
"""

from __future__ import annotations

from datetime import date

# Officer attributions (WP4 — brief reflects the simplified command structure).
_OFFICER = {
    "capacity": "Human Systems Officer",
    "delivery": "Engineering & Delivery Officer",
    "missions": "Number One",
    "decision": "Human Systems Officer",
}


def compose_daily_brief(
    *,
    capacity,                      # framework.CapacitySnapshot
    recommendation,               # decision.RecommendationPackage
    load,                         # mission_load.MissionLoad
    delivery=None,                # decision.DeliverySignal | None
    control_tower: dict | None = None,
    date_str: str | None = None,
) -> str:
    """Compose the single daily operating picture. Pure."""
    d = date_str or date.today().strftime("%a %d %b %Y")

    # Escalation (red flag) always leads.
    head: list[str] = []
    if recommendation.escalation:
        head += [recommendation.escalation, "", "———", ""]

    # What matters today.
    lines = head + [
        f"*Captain's Daily Operating Picture — {d}*",
        f"_{capacity.headline}_",
        "",
        # The one key decision requiring attention.
        f"🎯 *Decision ({_OFFICER['decision']}):* {recommendation.primary}",
        f"   • _Why:_ {recommendation.expected_impact}",
        f"   • _Opportunity cost:_ {recommendation.opportunity_cost}",
        f"   • _What can wait:_ {recommendation.recommended_deferral}",
        f"   • _Confidence:_ {recommendation._confidence_label()} · {recommendation.strategic_alignment}",
        "",
        f"🫀 *Capacity ({_OFFICER['capacity']}):* {capacity.overall_band} "
        f"({round(capacity.overall_score)}/100) — "
        + " · ".join(f"{x.label} {x.band}" for x in capacity.domains),
    ]

    # Mission load.
    if load.data_available:
        lines.append(f"📋 *Mission load ({_OFFICER['missions']}):* {load.open_count} open")

    # Delivery risk + blockers.
    if control_tower:
        ct = control_tower
        bn = ct.get("bottleneck") or {}
        risk_line = (
            f"🚦 *Delivery ({_OFFICER['delivery']}):* {ct.get('high_risk_count', 0)} high-risk "
            f"of {ct.get('open_count', 0)} open"
        )
        if bn.get("constraint"):
            risk_line += f" · constraint: {bn['constraint']} ({bn.get('constraint_count', 0)})"
        lines.append(risk_line)
        top = ct.get("top_risks") or []
        if top:
            lines.append("   • At risk: " + ", ".join(f"{r.title} ({r.score})" for r in top[:3]))

    # Active blockers (from delivery signal).
    if delivery and delivery.blocked:
        lines.append(f"⛔ *Active blockers:* {delivery.blocked} blocked mission(s)"
                     + (f" · top: {delivery.top_bottleneck}" if delivery.top_bottleneck else ""))

    lines += [
        "",
        "_One picture, one action. React with 👍 (helpful) / 😐 (neutral) / 👎 (not "
        "helpful), or `/hs feedback helpful|neutral|not`, so the system learns._",
    ]
    return "\n".join(lines)
