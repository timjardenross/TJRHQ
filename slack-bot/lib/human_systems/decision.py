"""HSF-002 — Captain Capacity Decision Engine.

Moves Human Systems from "what is happening" to "what should the Captain do about
it". Pure, network-free reasoning over a CapacitySnapshot (HSF-001), the current
MissionLoad (HSF-002 WP2), and recent daily rows.

The governing rule (Directive D-055): reduce decisions. Outputs are deliberately
small — a single highest-leverage action, a short focus/defer list — never a
recommendation list to wade through.

Work packages:
  WP1  allocate_capacity()       capacity → recommended focus + defer
  WP2  assess_mission_load()     capacity + open missions → overload detection
  WP4  detect_friction()         recurring causes of capacity loss
  WP3  weekly_capacity_review()  drivers, drains, one recommended change
  WP5  highest_leverage()        ONE primary (+ optional secondary), scored
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from . import framework, safety
from .mission_load import MissionLoad


# ── Capacity → sustainable active-mission mapping (reuses ROS-001) ─────────────
# How many missions to actively PROGRESS today (not total backlog).
_SUSTAINABLE_ACTIVE = {"good": 2, "moderate": 1, "limited": 0, "depleted": 0}
# Open-backlog level above which intake should pause when capacity isn't good.
OVERLOAD_BACKLOG_THRESHOLD = 5


# ── HSF-002 WP5 ⟂ EDO: delivery signal (active missions, blocked, bottlenecks) ─

@dataclass
class DeliverySignal:
    """Engineering-delivery signal fed into the highest-leverage decision.

    Populated by the caller from the EDO delivery layer so the human_systems
    engine stays decoupled from it (no cross-package import).
    """
    open_missions: int = 0
    blocked: int = 0
    oldest_open_age_days: int = 0
    top_bottleneck: str | None = None
    overloaded: bool = False


# ── WP2: Mission load assessment ──────────────────────────────────────────────

@dataclass
class MissionLoadAssessment:
    band: str
    open_count: int
    sustainable_active: int
    overloaded: bool
    headline: str
    recommendation: str


def assess_mission_load(snapshot: framework.CapacitySnapshot, load: MissionLoad) -> MissionLoadAssessment:
    band = snapshot.overall_band
    sustainable = _SUSTAINABLE_ACTIVE.get(band, 1)
    open_count = load.open_count

    overloaded = (
        band in ("limited", "depleted")
        or (open_count > sustainable and open_count >= OVERLOAD_BACKLOG_THRESHOLD)
        or (band == "moderate" and open_count > OVERLOAD_BACKLOG_THRESHOLD)
    )

    if not load.data_available:
        headline = f"Capacity is {band}; mission load not available to read."
        rec = (
            f"Based on capacity alone, progressing {sustainable} mission(s) today "
            "looks sustainable."
        )
    elif overloaded:
        headline = (
            f"Mission load ({open_count} open) exceeds available capacity ({band})."
        )
        rec = (
            f"Consider pausing new mission intake and progressing only "
            f"{max(sustainable, 1) if band not in ('limited','depleted') else 1} "
            "today. Defer the rest — they will keep."
        )
    else:
        headline = f"Mission load ({open_count} open) sits within {band} capacity."
        rec = (
            f"A practical next step could be progressing up to {sustainable} "
            "mission(s) today and holding new starts."
        )
    return MissionLoadAssessment(
        band=band, open_count=open_count, sustainable_active=sustainable,
        overloaded=overloaded, headline=headline, recommendation=rec,
    )


# ── WP1: Capacity allocation ──────────────────────────────────────────────────

@dataclass
class CapacityAllocation:
    band: str
    focus: list[str] = field(default_factory=list)   # ranked, where to spend capacity
    defer: list[str] = field(default_factory=list)    # what to stop / hold
    note: str = ""


def _top_priority_label(load: MissionLoad) -> str | None:
    tops = [p for p in load.top_priorities if p.is_active]
    if tops:
        return tops[0].label
    if load.open_titles:
        return load.open_titles[0]
    return None


def allocate_capacity(snapshot: framework.CapacitySnapshot, load: MissionLoad) -> CapacityAllocation:
    band = snapshot.overall_band
    top = _top_priority_label(load)

    if band in ("limited", "depleted"):
        focus = ["Recovery"]
        if top:
            focus.append(top)
        defer = [
            "New engineering or business initiatives",
            "Low-priority research",
            "Additional commitments",
        ]
        note = "This is a signal to protect capacity, not to push through."
    elif band == "moderate":
        focus = []
        if top:
            focus.append(top)
        focus.append("A protected recovery block")
        defer = ["New initiatives beyond the top priority", "Low-priority / P3+ backlog"]
        note = "Moderate capacity — one meaningful priority plus recovery is a fair day."
    else:  # good
        focus = []
        tops = [p.label for p in load.top_priorities if p.is_active][:2]
        focus.extend(tops or ([top] if top else []))
        focus.append("Bank a small recovery anchor")
        defer = ["P3+ backlog", "New commitments while capacity is being rebuilt"]
        note = "Capacity is available — spend it on what matters most, sustainably."

    # De-duplicate while preserving order.
    seen: set[str] = set()
    focus = [f for f in focus if not (f in seen or seen.add(f))]
    return CapacityAllocation(band=band, focus=focus, defer=defer, note=note)


# ── WP4: Friction detection ───────────────────────────────────────────────────

@dataclass
class FrictionFinding:
    key: str
    description: str   # the pattern, framed as information
    lever: str         # the actionable change
    confidence: float  # 0–1


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def detect_friction(rows: list[dict]) -> list[FrictionFinding]:
    """Identify recurring causes of capacity loss from recent daily rows."""
    findings: list[FrictionFinding] = []
    if len(rows) < 3:
        return findings

    ordered = sorted(rows, key=lambda r: str(r.get("log_date") or ""))
    snaps = [framework.interpret_capacity(r) for r in ordered]

    # 1. Short sleep → next-day capacity drop.
    drops = 0
    pairs = 0
    for i in range(len(ordered) - 1):
        sh = _f(ordered[i].get("sleep_hours"))
        if sh is None:
            continue
        pairs += 1
        if sh < 6.0 and snaps[i + 1].overall_band in ("limited", "depleted"):
            drops += 1
    if drops >= 2:
        findings.append(FrictionFinding(
            key="short_sleep_next_day",
            description=f"Short nights (under 6h) preceded a low-capacity day {drops} times.",
            lever="Protecting sleep is the highest-return lever on next-day capacity.",
            confidence=min(0.9, 0.5 + 0.15 * drops),
        ))

    # 2. Consecutive dysregulation / activation.
    streak = best = 0
    for r in ordered:
        ns = str(r.get("nervous_system_state") or "").lower()
        if ns in ("activated", "dysregulated"):
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    if best >= 2:
        findings.append(FrictionFinding(
            key="nervous_system_run",
            description=f"The nervous system ran activated/dysregulated for {best} days in a row.",
            lever="Two protected resets a day, and lightening load, tend to settle the run.",
            confidence=min(0.85, 0.45 + 0.15 * best),
        ))

    # 3. Consecutive low-capacity run (recovery debt).
    streak = best = 0
    for s in snaps:
        if s.overall_band in ("limited", "depleted"):
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    if best >= 3:
        findings.append(FrictionFinding(
            key="recovery_debt",
            description=f"Capacity ran limited/low for {best} consecutive days — recovery debt is building.",
            lever="A genuinely protected recovery window does more than another partial day.",
            confidence=min(0.9, 0.5 + 0.13 * best),
        ))

    # 4. Sleep-debt average.
    sleeps = [v for v in (_f(r.get("sleep_hours")) for r in ordered[-4:]) if v is not None]
    if len(sleeps) >= 3 and mean(sleeps) < 6.0:
        findings.append(FrictionFinding(
            key="sleep_debt_avg",
            description=f"Sleep has averaged {mean(sleeps):.1f}h over recent nights.",
            lever="A consistent wind-down and wake time is the single biggest capacity lever.",
            confidence=0.8,
        ))

    findings.sort(key=lambda f: -f.confidence)
    return findings


# ── WP5: Highest-leverage recommendation ──────────────────────────────────────

@dataclass
class Recommendation:
    primary: str
    rationale: str
    confidence: float          # 0–1
    leverage: str              # short label of the lever
    secondary: str | None = None
    escalation: str | None = None  # red-flag banner, when present

    def render(self) -> str:
        lines = []
        if self.escalation:
            lines += [self.escalation, "", "———", ""]
        lines += [
            "*Highest-Leverage Action*",
            self.primary,
            "",
            f"_Why: {self.rationale}_",
            f"_Confidence: {self._confidence_label()}._",
        ]
        if self.secondary:
            lines += ["", f"*If there's more in the tank:* {self.secondary}"]
        return "\n".join(lines)

    def _confidence_label(self) -> str:
        if self.confidence >= 0.75:
            return "high"
        if self.confidence >= 0.5:
            return "moderate"
        return "tentative"


@dataclass
class _Candidate:
    score: float
    primary: str
    rationale: str
    leverage: str
    domain: str


def highest_leverage(
    snapshot: framework.CapacitySnapshot,
    load: MissionLoad,
    frictions: list[FrictionFinding],
    *,
    notes: str | None = None,
    delivery: DeliverySignal | None = None,
    learned: dict[str, float] | None = None,
) -> Recommendation:
    """Produce ONE primary action (+ optional secondary), scored by leverage×confidence.

    Decision-reduction by construction: candidates are ranked and only the top
    one (plus at most one clearly-distinct secondary) is surfaced. ``delivery``
    (HSF-002 WP5 ⟂ EDO) lets active missions, blocked work, and bottlenecks
    compete as candidates. ``learned`` (EDO-003 WP3) applies gentle, observed
    confidence multipliers per domain (advisory — never autonomous).
    """
    escalation = safety.escalation_banner(safety.scan_red_flags(notes))

    band = snapshot.overall_band
    data_conf = 1.0 if snapshot.data_available else 0.5
    load_assess = assess_mission_load(snapshot, load)

    candidates: list[_Candidate] = []

    # Recovery protection — dominant when capacity is low.
    if band in ("limited", "depleted"):
        candidates.append(_Candidate(
            score=(0.95 if band == "depleted" else 0.85) * data_conf,
            primary="Protect capacity today: pick one anchor, defer the rest, and "
                    "schedule one genuine recovery block now.",
            rationale=f"capacity is {band}; protecting it is worth more than any task today",
            leverage="recovery protection", domain="recovery",
        ))

    # Mission overload — pause intake / defer.
    if load_assess.overloaded and load.data_available:
        candidates.append(_Candidate(
            score=0.8 * data_conf,
            primary=f"{load_assess.recommendation}",
            rationale=f"{load.open_count} open missions against {band} capacity",
            leverage="load reduction", domain="missions",
        ))

    # Strongest friction with a clear lever.
    if frictions:
        f0 = frictions[0]
        candidates.append(_Candidate(
            score=0.6 + 0.35 * f0.confidence,
            primary=f"{f0.lever}",
            rationale=f0.description.rstrip("."),
            leverage=f0.key.replace("_", " "), domain="friction",
        ))

    # Delivery signal — blocked work and bottlenecks compete for the lever.
    if delivery is not None:
        if delivery.blocked > 0:
            candidates.append(_Candidate(
                score=0.82 * data_conf,
                primary=f"Clear the blocked delivery item — {delivery.blocked} "
                        "mission(s) are blocked and quietly draining attention.",
                rationale=f"{delivery.blocked} blocked mission(s) in delivery",
                leverage="unblock delivery", domain="delivery",
            ))
        elif delivery.top_bottleneck:
            candidates.append(_Candidate(
                score=0.6 * data_conf,
                primary=f"Address the top delivery bottleneck: {delivery.top_bottleneck}.",
                rationale="delivery is stalling on one item",
                leverage="delivery bottleneck", domain="delivery",
            ))

    # Apply capacity to the top priority — when capacity is available.
    top = _top_priority_label(load)
    if band in ("good", "moderate") and top and not load_assess.overloaded:
        candidates.append(_Candidate(
            score=(0.7 if band == "good" else 0.55) * data_conf,
            primary=f"Spend your best window on: {top}. Hold everything below it.",
            rationale=f"capacity is {band} and '{top}' is the highest active priority",
            leverage="priority focus", domain="priority",
        ))

    # Default — maintain.
    candidates.append(_Candidate(
        score=0.35,
        primary="Hold a steady, sustainable pattern and protect your recovery window.",
        rationale="no single signal dominates today",
        leverage="maintain", domain="maintain",
    ))

    # EDO-003 WP3: apply gentle learned confidence multipliers (advisory).
    if learned:
        for c in candidates:
            c.score *= learned.get(c.domain, learned.get("_global", 1.0))

    candidates.sort(key=lambda c: -c.score)
    top_c = candidates[0]

    # Optional secondary: the next candidate from a *different* domain, if material.
    secondary = None
    for c in candidates[1:]:
        if c.domain != top_c.domain and c.score >= 0.5:
            secondary = c.primary
            break

    return Recommendation(
        primary=top_c.primary,
        rationale=top_c.rationale,
        confidence=round(top_c.score, 2),
        leverage=top_c.leverage,
        secondary=secondary,
        escalation=escalation,
    )


# ── MSN-EDO-003 WP3: Decision Intelligence 2.0 — recommendation package ────────

@dataclass
class RecommendationPackage:
    primary: str
    confidence: float
    expected_impact: str
    opportunity_cost: str
    recommended_deferral: str
    strategic_alignment: str
    secondary: str | None = None
    escalation: str | None = None

    def _confidence_label(self) -> str:
        return "high" if self.confidence >= 0.75 else "moderate" if self.confidence >= 0.5 else "tentative"

    def render(self) -> str:
        lines = []
        if self.escalation:
            lines += [self.escalation, "", "———", ""]
        lines += [
            "*Highest-Leverage Action*",
            self.primary,
            "",
            f"• *Confidence:* {self._confidence_label()}",
            f"• *Expected impact:* {self.expected_impact}",
            f"• *Opportunity cost:* {self.opportunity_cost}",
            f"• *Recommended deferral:* {self.recommended_deferral}",
            f"• *Strategic alignment:* {self.strategic_alignment}",
        ]
        if self.secondary:
            lines += ["", f"*If there's more in the tank:* {self.secondary}"]
        return "\n".join(lines)


_IMPACT_BY_LEVERAGE = {
    "recovery protection": "Protects tomorrow's capacity; lowers flare and overload risk.",
    "load reduction": "Frees attention and reduces overload and rework risk.",
    "unblock delivery": "Removes a stalled item draining attention and delivery throughput.",
    "delivery bottleneck": "Clears the constraint slowing delivery.",
    "priority focus": "Advances the highest-value objective while capacity allows.",
    "maintain": "Sustains steady progress without overextending.",
}


def recommendation_package(
    snapshot: framework.CapacitySnapshot,
    load: MissionLoad,
    frictions: list[FrictionFinding],
    *,
    notes: str | None = None,
    delivery: DeliverySignal | None = None,
    learned: dict[str, float] | None = None,
) -> RecommendationPackage:
    """Executive decision support: one action plus impact, opportunity cost,
    deferral, and strategic alignment (D-055). Reuses highest_leverage()."""
    rec = highest_leverage(snapshot, load, frictions, notes=notes,
                           delivery=delivery, learned=learned)
    alloc = allocate_capacity(snapshot, load)

    expected = _IMPACT_BY_LEVERAGE.get(rec.leverage, "Directs limited capacity to the highest-value next step.")

    # Opportunity cost: what choosing this defers.
    if rec.secondary:
        opportunity = f"The next-best option waits: {rec.secondary}"
    elif alloc.defer:
        opportunity = f"You hold off on: {alloc.defer[0].lower()}"
    else:
        opportunity = "Minimal — this is the lowest-regret use of capacity now."

    deferral = alloc.defer[0] if alloc.defer else "Nothing pressing to defer today."

    # Strategic alignment to D-055 (capacity-first).
    if rec.leverage in ("recovery protection", "load reduction", "unblock delivery", "delivery bottleneck"):
        alignment = "Strong — directly protects capacity and clears drag (D-055)."
    elif rec.leverage == "priority focus":
        alignment = "Strong — advances the top priority within available capacity (D-055)."
    else:
        alignment = "Moderate — steady, capacity-respecting progress."

    return RecommendationPackage(
        primary=rec.primary, confidence=rec.confidence, expected_impact=expected,
        opportunity_cost=opportunity, recommended_deferral=deferral,
        strategic_alignment=alignment, secondary=rec.secondary, escalation=rec.escalation,
    )


# ── WP3: Weekly capacity review (decision-focused) ────────────────────────────

def weekly_capacity_review(rows: list[dict], load: MissionLoad) -> str:
    if not rows:
        return (
            "*Weekly Capacity Review*\nNo check-ins logged this period — a few quick "
            "check-ins would let the review read drivers and drains next week."
        )

    ordered = sorted(rows, key=lambda r: str(r.get("log_date") or ""))
    snaps = [framework.interpret_capacity(r) for r in ordered]
    scores = [s.overall_score for s in snaps]
    frictions = detect_friction(ordered)

    # Drivers (what supported capacity).
    drivers: list[str] = []
    sleeps = [v for v in (_f(r.get("sleep_hours")) for r in ordered) if v is not None]
    if sleeps and mean(sleeps) >= 7:
        drivers.append("Consistent sleep")
    calm_days = sum(1 for r in ordered if str(r.get("nervous_system_state") or "").lower() == "calm")
    if calm_days >= max(2, len(ordered) // 2):
        drivers.append("Settled nervous system")
    moved = sum(1 for r in ordered if r.get("movement_completed") is True)
    if moved >= 2:
        drivers.append("Movement consistency")
    if len(scores) >= 3 and mean(scores[len(scores)//2:]) - mean(scores[:len(scores)//2]) >= 6:
        drivers.append("Capacity trending up")

    # Drains (what cost capacity) — sourced from friction findings + load.
    drains = [f.description for f in frictions[:2]]
    if load.data_available and load.open_count >= OVERLOAD_BACKLOG_THRESHOLD:
        drains.append(f"{load.open_count} open missions — load pressure")

    # The single recommended change (reuse highest-leverage on latest snapshot).
    rec = highest_leverage(snaps[-1], load, frictions)

    lines = [
        "*Weekly Capacity Review*",
        f"_{len(ordered)} day(s) · average capacity {round(mean(scores))}/100_",
        "",
        "*Capacity drivers:*",
    ]
    lines += [f"• {d}" for d in (drivers or ["Not enough signal to name a clear driver"])]
    lines += ["", "*Capacity drains:*"]
    lines += [f"• {d}" for d in (drains or ["No significant drain detected this period"])]
    lines += [
        "",
        "*Recommended change (one thing):*",
        rec.primary,
        "",
        "_A capacity review, not a scorecard. The aim is to protect capacity, not raise activity._",
    ]
    return "\n".join(lines)
