"""Captain's Daily Operating Picture (MSN-XO-002 WP1).

ONE flagship brief that composes the *existing* Human Systems and EDO engines —
it builds no new analytics. Pure: takes already-fetched parts and returns the
brief string, so it is fully testable and the command/scheduler just gather data.

Answers, in one concise executive briefing: What matters today? Why? What should
I do? What can wait? Framed by the four line officers (XO-001 structure).

Progressive disclosure: the scheduled push and bare `/brief` render a short
"Today" *card* (``mode="card"``) — the one decision plus only the exceptions
that cross a threshold. Everything else lives behind ``/brief <section>`` and
``/brief all`` (``mode="all"``, the full dashboard and the default here).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

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
_BAND_EMOJI = {"good": "🟢", "moderate": "🟡", "limited": "🟠", "depleted": "🔴"}

# Modes: "card" (default push), "all" (full dashboard), or one section view.
SECTIONS = ("delivery", "resilience", "knowledge", "comms", "learning")
MODES = ("card", "all") + SECTIONS

# Internal scheduler/job titles that leak into Command Memory and are noise to the Captain.
_INTERNAL_KNOWLEDGE = re.compile(r"^\s*\[OFFICER SCHEDULE\]", re.IGNORECASE)

# How many "worth a look" items the card adds, by overall capacity band.
_WORTH_A_LOOK = {"good": 3, "moderate": 1}


def _clip(text: str | None, limit: int) -> str:
    """Truncate on a word boundary with an ellipsis (never mid-word)."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:—- ")
    return (cut or text[:limit]) + "…"


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


# ── Section helpers (each returns lines; empty list = nothing to show) ────────

def _open_count(load, brief_doc) -> int:
    canon = _canonical_metrics_for(brief_doc, "mission.load_snapshot")
    return canon.get("open_count", getattr(load, "open_count", 0) or 0)


def _mission_load_lines(load, brief_doc) -> list[str]:
    load_canon = _canonical_metrics_for(brief_doc, "mission.load_snapshot")
    if load.data_available or load_canon:
        return [f"📋 *Mission load ({_OFFICER['missions']}):* {_open_count(load, brief_doc)} open"]
    return []


def _strategy_lines(strategy, brief_doc, open_count: int) -> list[str]:
    """MSN-SPC-001 WP4: Strategic Focus — what today's work serves long-term."""
    if strategy is None or not getattr(strategy, "data_available", False):
        return []
    strat_canon = _canonical_metrics_for(brief_doc, "strategy.focus_snapshot")
    active = list(getattr(strategy, "active", []) or [])
    if not active:
        return []
    domains = getattr(strategy, "active_domains", []) or []
    active_count = strat_canon.get("active_count", len(active))
    domain_count = strat_canon.get("active_domains", len(domains))
    head = (
        f"🧭 *Strategic Focus ({_OFFICER['strategy']}):* {active_count} active "
        f"objective(s) across {domain_count} domain(s)"
    )
    orphans = strat_canon.get("orphan_count", getattr(strategy, "orphan_count", 0) or 0)
    # Every open mission counted as unaligned carries no information — hide it.
    if orphans and not (open_count and orphans >= open_count):
        head += f" · {orphans} unaligned mission(s)"
    lines = [head]
    for o in active[:3]:
        lines.append(f"   • [{o.priority}] {o.title} — _{o.domain}_ · {o.progress_label()}")
    return lines


def _delivery_counts(control_tower, brief_doc) -> tuple[int, int]:
    canon = _canonical_metrics_for(brief_doc, "delivery.risk_snapshot")
    ct = control_tower or {}
    return (
        canon.get("high_risk_count", ct.get("high_risk_count", 0)),
        canon.get("open_count", ct.get("open_count", 0)),
    )


def _delivery_lines(control_tower, delivery, brief_doc) -> list[str]:
    """Delivery risk + blockers. The risk block is hidden when nothing is open
    (its sources disagree with mission load otherwise)."""
    lines: list[str] = []
    if control_tower:
        ct = control_tower
        bn = ct.get("bottleneck") or {}
        delivery_canon = _canonical_metrics_for(brief_doc, "delivery.risk_snapshot")
        high, opened = _delivery_counts(ct, brief_doc)
        if opened:
            risk_line = (
                f"🚦 *Delivery ({_OFFICER['delivery']}):* {high} high-risk of {opened} open"
            )
            constraint = delivery_canon.get("constraint", bn.get("constraint"))
            if constraint:
                constraint_count = delivery_canon.get("constraint_count", bn.get("constraint_count", 0))
                risk_line += f" · constraint: {constraint} ({constraint_count})"
            lines.append(risk_line)
            top = ct.get("top_risks") or []
            if top:
                lines.append(
                    "   • At risk: " + ", ".join(f"{_clip(r.title, 60)} ({r.score})" for r in top[:3])
                )
    # Active blockers (from delivery signal).
    if delivery and delivery.blocked:
        lines.append(f"⛔ *Active blockers:* {delivery.blocked} blocked mission(s)"
                     + (f" · top: {delivery.top_bottleneck}" if delivery.top_bottleneck else ""))
    return lines


def _ori_lines(ori) -> list[str]:
    """MSN-XO-003 WP2: Operational Resilience Intelligence."""
    if ori is None or not getattr(ori, "data_available", True):
        return []
    risk = (ori.overall_risk or "UNKNOWN").upper()
    conf = f" · confidence {ori.confidence:.0%}" if ori.confidence is not None else ""
    lines = [
        f"{_RISK_EMOJI.get(risk, '⚪')} *Resilience ({_OFFICER['ori']}):* "
        f"{risk} {_TREND_ARROW.get(ori.trend, '·')} — {ori.top_risk}{conf}"
    ]
    if ori.recommended_action:
        lines.append(f"   • _Recommended:_ {ori.recommended_action}")
    return lines


def _knowledge_hits(knowledge) -> list:
    return [h for h in (knowledge or []) if not _INTERNAL_KNOWLEDGE.match(getattr(h, "title", "") or "")]


def _knowledge_lines(knowledge) -> list[str]:
    """MSN-XO-003 WP3: relevant prior knowledge."""
    hits = _knowledge_hits(knowledge)
    if not hits:
        return []
    return [f"📚 *Relevant prior knowledge ({_OFFICER['knowledge']}):*"] + [
        f"   • [{h.kind}] {h.title}" for h in hits[:4]
    ]


def _comms_lines(comms) -> list[str]:
    """COMMS-001 WP5: presence — a publishable opportunity worth surfacing."""
    if not comms:
        return []
    pub = [o for o in comms if getattr(o, "is_publishable", True)]
    if not pub:
        return []
    top = pub[0]
    return [
        f"📡 *Presence ({_OFFICER['comms']}):* {len(pub)} publishable "
        f"opportunity(ies) — top: {top.title} (_{top.pillar_name}_) · `/comms weekly`"
    ]


def _learning_lines(learning) -> list[str]:
    """MSN-0076/0080 WP3: outcome & learning loop — one concise line, never overloaded."""
    if learning is None or not getattr(learning, "has_signal", False):
        return []
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
    if not (bits or recent):
        return []
    line = f"🧠 *Learning ({_OFFICER['learning']}){health_tag}:* " + (" · ".join(bits) if bits else "")
    if recent:
        top = recent[0]
        title = (top.get("title") if isinstance(top, dict) else str(top)) or ""
        line += f"{' · ' if bits else ''}latest: {title[:60]}"
    return [line.rstrip(), "   • `python3 tools/record_outcome.py status`"]


# ── Leading block: escalation + INTERRUPT_NOW ─────────────────────────────────

def _head_lines(recommendation, brief_doc) -> list[str]:
    head: list[str] = []
    # Escalation (red flag) always leads.
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
    return head


# ── Card (default push) ───────────────────────────────────────────────────────

def _capacity_card_line(capacity) -> str:
    if not getattr(capacity, "data_available", True):
        return capacity.headline
    band = capacity.overall_band
    line = (f"{_BAND_EMOJI.get(band, '⚪')} {band.capitalize()} capacity "
            f"({round(capacity.overall_score)}/100)")
    low = [x.label for x in getattr(capacity, "limited_domains", [])]
    if low:
        line += " — low: " + ", ".join(low)
    return line


def _compose_card(*, d, head, capacity, recommendation, canon, load, delivery,
                  control_tower, ori, knowledge, strategy, comms, learning,
                  brief_doc) -> str:
    lines = head + [
        f"☀️ *Daily Operating Picture* — {d}",
        _capacity_card_line(capacity),
        "",
        f"🎯 *Today:* {recommendation.primary}",
        f"   Why: {canon.get('expected_impact', recommendation.expected_impact)}",
        f"   Can wait: {canon.get('recommended_deferral', recommendation.recommended_deferral)}",
    ]

    surfaced: list[str] = []
    quiet: list[str] = []

    # Delivery: only when something is actually wrong.
    high, opened = _delivery_counts(control_tower, brief_doc)
    blocked = getattr(delivery, "blocked", 0) if delivery else 0
    if high or blocked:
        bits = []
        if high:
            bits.append(f"{high} high-risk of {opened} open")
        if blocked:
            top = getattr(delivery, "top_bottleneck", None)
            bits.append(f"{blocked} blocked" + (f" (top: {_clip(top, 50)})" if top else ""))
        surfaced.append("🚦 Delivery: " + " · ".join(bits))
    elif opened:
        quiet.append("delivery")

    # Resilience: RED, or AMBER and worsening. Otherwise just a quiet label.
    if ori is not None and getattr(ori, "data_available", True):
        risk = (ori.overall_risk or "UNKNOWN").upper()
        if risk == "RED" or (risk == "AMBER" and ori.trend == "worsening"):
            surfaced.append(
                f"{_RISK_EMOJI.get(risk, '⚪')} Resilience: {risk} {_TREND_ARROW.get(ori.trend, '·')}"
                f" — {_clip(ori.top_risk, 80)}"
            )
            action = (ori.recommended_action or "").strip()
            if action and not action.startswith("No specific action"):
                surfaced.append(f"   • {_clip(action, 140)}")
        else:
            quiet.append(f"resilience ({risk} {ori.trend})")

    # Learning: only overdue outcomes.
    overdue = getattr(learning, "overdue_count", 0) if learning is not None else 0
    if overdue:
        surfaced.append(f"🧠 Learning: {overdue} outcome(s) overdue · /brief learning")

    if strategy is not None and getattr(strategy, "data_available", False) \
            and getattr(strategy, "active", None):
        quiet.append("strategy")

    if surfaced:
        lines += [""] + surfaced

    # Green/moderate capacity can take a little optional reading.
    n_extra = _WORTH_A_LOOK.get(capacity.overall_band, 0) if getattr(capacity, "data_available", True) else 0
    if n_extra:
        extras: list[str] = []
        active = list(getattr(strategy, "active", []) or []) if strategy is not None else []
        if active:
            extras.append(f"🧭 {_clip(active[0].title, 70)} — {active[0].domain}")
        pub = [o for o in (comms or []) if getattr(o, "is_publishable", True)]
        if pub:
            extras.append(f"📡 {_clip(pub[0].title, 70)}")
        kn = _knowledge_hits(knowledge)
        if kn:
            extras.append(f"📚 {_clip(kn[0].title, 70)}")
        if extras:
            lines += ["", "👀 Worth a look:"] + [f"   • {e}" for e in extras[:n_extra]]

    lines.append("")
    if quiet:
        lines.append("✅ Quiet: " + " · ".join(quiet))
    lines += [
        "More: `/brief delivery` · `resilience` · `strategy` · `comms` · `knowledge` · `all`",
        "React 👍 😐 👎 so the system learns.",
    ]
    return "\n".join(lines)


# ── Single-section views (`/brief <section>`) ─────────────────────────────────

def _compose_section(mode, *, d, load, delivery, control_tower, ori, knowledge,
                     comms, learning, brief_doc) -> str:
    titles = {
        "delivery": "Delivery", "resilience": "Resilience", "knowledge": "Prior knowledge",
        "comms": "Presence", "learning": "Learning",
    }
    if mode == "delivery":
        body = _mission_load_lines(load, brief_doc) + _delivery_lines(control_tower, delivery, brief_doc)
    elif mode == "resilience":
        body = _ori_lines(ori)
    elif mode == "knowledge":
        body = _knowledge_lines(knowledge)
    elif mode == "comms":
        body = _comms_lines(comms)
    else:
        body = _learning_lines(learning)
    if not body:
        body = [f"_Nothing to report for {titles[mode].lower()} right now._"]
    return "\n".join([f"*{titles[mode]} — {d}*", ""] + body + ["", "_Back to the card: `/brief`._"])


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
    mode: str = "all",             # "card" | "all" | one of SECTIONS
) -> str:
    """Compose the daily operating picture. Pure — brief_doc, like every other
    param, is pre-fetched by the caller; this function does no I/O of its own.

    ``mode="all"`` (default) is the full dashboard; ``"card"`` is the short
    Today card used by the scheduled push; a section name renders that section."""
    if mode not in MODES:
        raise ValueError(f"unknown brief mode: {mode!r} (expected one of {MODES})")
    d = date_str or datetime.now(timezone.utc).date().strftime("%a %d %b %Y")

    if mode in SECTIONS:
        return _compose_section(
            mode, d=d, load=load, delivery=delivery, control_tower=control_tower, ori=ori,
            knowledge=knowledge, comms=comms, learning=learning, brief_doc=brief_doc,
        )

    canon = _canonical_decision_metrics(brief_doc)
    head = _head_lines(recommendation, brief_doc)

    if mode == "card":
        return _compose_card(
            d=d, head=head, capacity=capacity, recommendation=recommendation, canon=canon,
            load=load, delivery=delivery, control_tower=control_tower, ori=ori,
            knowledge=knowledge, strategy=strategy, comms=comms, learning=learning,
            brief_doc=brief_doc,
        )

    # mode == "all": the full dashboard.
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
    lines += _mission_load_lines(load, brief_doc)
    lines += _strategy_lines(strategy, brief_doc, _open_count(load, brief_doc))
    lines += _delivery_lines(control_tower, delivery, brief_doc)
    lines += _ori_lines(ori)
    lines += _knowledge_lines(knowledge)
    lines += _comms_lines(comms)
    lines += _learning_lines(learning)
    lines += [
        "",
        ("_One picture, one action. React with 👍 (helpful) / 😐 (neutral) / 👎 (not "
        "helpful), or `/hs feedback helpful|neutral|not`, so the system learns._"),
    ]
    return "\n".join(lines)
