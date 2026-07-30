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
    "learning": "Knowledge / Learning Loop",
}

_RISK_EMOJI = {"RED": "🔴", "AMBER": "🟠", "GREEN": "🟢", "UNKNOWN": "⚪"}
_TREND_ARROW = {"worsening": "↑", "improving": "↓", "steady": "→", "unknown": "·"}


def _canonical_metrics_for(brief_doc, event_type: str) -> dict:
    """MSN-0328 Wave 3: look up one event_type's metrics from the canonical
    CaptainBriefDocument (emitted by commands/brief.py right before this is
    called). Every call site below uses this as a per-field PREFERENCE over
    the directly-passed parameter, never a replacement — {} on no match
    (Supabase disabled, event not yet visible to a poll that raced the
    insert, or genuinely absent), so this can never lose data, only add
    the canonical source when it's actually there."""
    if brief_doc is None:
        return {}
    all_items = (
        getattr(brief_doc, "operational_intelligence", [])
        + getattr(brief_doc, "health", [])
        + getattr(brief_doc, "engineering", [])
    )
    for item in all_items:
        if item.event_type == event_type and item.metrics:
            return item.metrics
    return {}


def _canonical_decision_metrics(brief_doc):
    return _canonical_metrics_for(brief_doc, "human_systems.recommendation_computed")


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
    learning=None,                 # outcome_capture.LearningSnapshot | None (MSN-0076 WP5)
    date_str: str | None = None,
    brief_doc=None,                # core.platform.captain_brief_orchestrator.CaptainBriefDocument | None (MSN-0328 Wave 3)
) -> str:
    """Compose the single daily operating picture. Pure — brief_doc, like
    every other param, is pre-fetched by the caller; this function does no
    I/O of its own."""
    d = date_str or date.today().strftime("%a %d %b %Y")
    canon = _canonical_decision_metrics(brief_doc)

    # Escalation (red flag) always leads.
    head: list[str] = []
    if recommendation.escalation:
        head += [recommendation.escalation, "", "———", ""]

    # USS-TJR-MSN-0339 WP2: render every Attention Engine INTERRUPT_NOW item,
    # not one hardcoded event_type — MSN-0338 Gap #4 found the prior renderer
    # had no call site at all for ORI's `intelligence.signal.ranked`, so a
    # correctly-computed interrupt was silently dropped before any text was
    # produced. Reading `brief_doc.interrupt_now` directly (populated by
    # captain_brief_orchestrator.py, MSN-0339 WP2) fixes this for any
    # domain/event_type in the category, not just the one MSN-0338 traced.
    interrupt_items = list(getattr(brief_doc, "interrupt_now", []) or [])
    if interrupt_items:
        head.append(f"🚨 *INTERRUPT NOW ({len(interrupt_items)}):*")
        for item in interrupt_items[:5]:
            text = item.recommendation.description if item.recommendation else item.reason
            head.append(f"   • [{item.domain}] {text}")
        head.append("")

    # What matters today.
    lines = head + [
        f"*Captain's Daily Operating Picture — {d}*",
        f"_{capacity.headline}_",
        "",
        # The one key decision requiring attention.
        f"🎯 *Decision ({_OFFICER['decision']}):* {recommendation.primary}",
        f"   • _Why:_ {canon.get('expected_impact', recommendation.expected_impact)}",
        f"   • _Opportunity cost:_ {canon.get('opportunity_cost', recommendation.opportunity_cost)}",
        f"   • _What can wait:_ {canon.get('recommended_deferral', recommendation.recommended_deferral)}",
        f"   • _Confidence:_ {recommendation._confidence_label()} · {canon.get('strategic_alignment', recommendation.strategic_alignment)}",
        "",
        f"🫀 *Capacity ({_OFFICER['capacity']}):* {capacity.overall_band} "
        f"({round(capacity.overall_score)}/100) — "
        + " · ".join(f"{x.label} {x.band}" for x in capacity.domains),
    ]

    # Mission load.
    load_canon = _canonical_metrics_for(brief_doc, "mission.load_snapshot")
    if load.data_available or load_canon:
        open_count = load_canon.get("open_count", load.open_count)
        lines.append(f"📋 *Mission load ({_OFFICER['missions']}):* {open_count} open")

    # MSN-SPC-001 WP4: Strategic Focus — what today's work serves long-term.
    if strategy is not None and getattr(strategy, "data_available", False):
        strat_canon = _canonical_metrics_for(brief_doc, "strategy.focus_snapshot")
        active = list(getattr(strategy, "active", []) or [])
        if active:
            domains = getattr(strategy, "active_domains", []) or []
            active_count = strat_canon.get("active_count", len(active))
            domain_count = strat_canon.get("active_domains", len(domains))
            head = (
                f"🧭 *Strategic Focus ({_OFFICER['strategy']}):* {active_count} active "
                f"objective(s) across {domain_count} domain(s)"
            )
            orphans = strat_canon.get("orphan_count", getattr(strategy, "orphan_count", 0) or 0)
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
        delivery_canon = _canonical_metrics_for(brief_doc, "delivery.risk_snapshot")
        risk_line = (
            f"🚦 *Delivery ({_OFFICER['delivery']}):* "
            f"{delivery_canon.get('high_risk_count', ct.get('high_risk_count', 0))} high-risk "
            f"of {delivery_canon.get('open_count', ct.get('open_count', 0))} open"
        )
        constraint = delivery_canon.get("constraint", bn.get("constraint"))
        if constraint:
            constraint_count = delivery_canon.get("constraint_count", bn.get("constraint_count", 0))
            risk_line += f" · constraint: {constraint} ({constraint_count})"
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

    # MSN-0076/0080 WP3: outcome & learning loop — one concise line, never overloaded.
    if learning is not None and getattr(learning, "has_signal", False):
        bits: list[str] = []
        uncap = getattr(learning, "uncaptured_count", 0)
        if uncap:
            overdue = getattr(learning, "overdue_count", 0)
            bits.append(f"{uncap} item(s) missing outcomes"
                        + (f" ({overdue} overdue)" if overdue else ""))
        if getattr(learning, "content_worthy_count", 0):
            bits.append(f"{learning.content_worthy_count} content-worthy")
        if getattr(learning, "reusable_count", 0):
            bits.append(f"{learning.reusable_count} reusable insight(s)")
        if getattr(learning, "sensitive_pending", 0):
            bits.append(f"{learning.sensitive_pending} sensitive pending approval")
        recent = list(getattr(learning, "recent_lessons", []) or [])
        health = getattr(learning, "health", "") or ""
        health_tag = f" {_RISK_EMOJI.get(health.upper(), '')}".rstrip() if health and health != "UNKNOWN" else ""
        if bits or recent:
            line = f"🧠 *Learning ({_OFFICER['learning']}){health_tag}:* " + (" · ".join(bits) if bits else "")
            if recent:
                top = recent[0]
                title = (top.get("title") if isinstance(top, dict) else str(top)) or ""
                line += f"{' · ' if bits else ''}latest: {title[:60]}"
            lines.append(line.rstrip())
            lines.append("   • `python3 tools/record_outcome.py status`")

    lines += [
        "",
        "_One picture, one action. React with 👍 (helpful) / 😐 (neutral) / 👎 (not "
        "helpful), or `/hs feedback helpful|neutral|not`, so the system learns._",
    ]
    return "\n".join(lines)
