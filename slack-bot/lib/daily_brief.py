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
    "ori": "Operational Resilience Intelligence",
    "knowledge": "Knowledge",
    "strategy": "Strategic Command (XO)",
    "comms": "Communications & Presence Officer",
}

_RISK_EMOJI = {"RED": "🔴", "AMBER": "🟠", "GREEN": "🟢", "UNKNOWN": "⚪"}
_TREND_ARROW = {"worsening": "↑", "improving": "↓", "steady": "→", "unknown": "·"}


def compose_daily_brief(
    *,
    capacity,                      # framework.CapacitySnapshot
    recommendation,               # decision.RecommendationPackage
    load,                         # mission_load.MissionLoad
    delivery=None,                # decision.DeliverySignal | None
    control_tower: dict | None = None,
    ori=None,                      # intel.ori.ORISignal | None  (MSN-XO-003 WP2)
    knowledge=None,               # list[intel.knowledge.KnowledgeHit] | None (WP3)
    strategy=None,                 # strategy.objectives.StrategicSnapshot | None (SPC-001 WP4)
    comms=None,                    # list[comms.ContentOpportunity] | None (COMMS-001 WP5)
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

    # MSN-SPC-001 WP4: Strategic Focus — what today's work serves long-term.
    if strategy is not None and getattr(strategy, "data_available", False):
        active = list(getattr(strategy, "active", []) or [])
        if active:
            domains = getattr(strategy, "active_domains", []) or []
            head = (
                f"🧭 *Strategic Focus ({_OFFICER['strategy']}):* {len(active)} active "
                f"objective(s) across {len(domains)} domain(s)"
            )
            orphans = getattr(strategy, "orphan_count", 0) or 0
            if orphans:
                head += f" · {orphans} unaligned mission(s)"
            lines.append(head)
            for o in active[:3]:
                lines.append(
                    f"   • [{o.priority}] {o.title} — _{o.domain}_ · {o.progress_label()}"
                )

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

    # MSN-XO-003 WP2: Operational Resilience Intelligence (surfaced automatically).
    if ori is not None and getattr(ori, "data_available", True):
        risk = (ori.overall_risk or "UNKNOWN").upper()
        conf = f" · confidence {ori.confidence:.0%}" if ori.confidence is not None else ""
        lines.append(
            f"{_RISK_EMOJI.get(risk, '⚪')} *Resilience ({_OFFICER['ori']}):* "
            f"{risk} {_TREND_ARROW.get(ori.trend, '·')} — {ori.top_risk}{conf}"
        )
        if ori.recommended_action:
            lines.append(f"   • _Recommended:_ {ori.recommended_action}")

    # MSN-XO-003 WP3: relevant prior knowledge (surfaced automatically).
    if knowledge:
        lines.append(f"📚 *Relevant prior knowledge ({_OFFICER['knowledge']}):*")
        for h in knowledge[:4]:
            lines.append(f"   • [{h.kind}] {h.title}")

    # COMMS-001 WP5: presence — a publishable opportunity worth surfacing today.
    if comms:
        pub = [o for o in comms if getattr(o, "is_publishable", True)]
        if pub:
            top = pub[0]
            lines.append(
                f"📡 *Presence ({_OFFICER['comms']}):* {len(pub)} publishable "
                f"opportunity(ies) — top: {top.title} (_{top.pillar_name}_) · `/comms weekly`"
            )

    lines += [
        "",
        "_One picture, one action. React with 👍 (helpful) / 😐 (neutral) / 👎 (not "
        "helpful), or `/hs feedback helpful|neutral|not`, so the system learns._",
    ]
    return "\n".join(lines)
