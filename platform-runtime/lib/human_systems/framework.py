"""Human Systems — Framework Engine (HSF-001 §1, §7, §8).

Pure, network-free reasoning over health log rows (the shape returned by the
Supabase ``analytics_health_daily`` view). Everything here is deterministic and
testable without a database.

Provides:
  - DOMAINS               — the six-domain registry
  - interpret_capacity()  — four-domain energy snapshot + daily capacity score
  - build_plan()          — low-capacity / recovery / movement / nutrition / mind
  - explain_signal()      — interpret one day's pattern as information
  - weekly_review()       — synthesise a run of days into a Human Systems review

No diagnosis. All copy follows the doctrine's language rules; see safety.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


# ── Domain registry (doctrine §1) ─────────────────────────────────────────────

DOMAINS: dict[str, dict] = {
    "medical": {
        "label": "Medical / Nervous System",
        "purpose": "Interpret pain, fatigue, dysregulation, sleep and recovery as information.",
    },
    "movement": {
        "label": "Movement",
        "purpose": "Sustain movement safely and consistently, pain-aware.",
    },
    "nutrition": {
        "label": "Nutrition",
        "purpose": "Support stable energy, recovery, satiety and health goals.",
    },
    "mind": {
        "label": "Mind / Cognitive Load",
        "purpose": "Manage focus, overwhelm, executive function and mental load.",
    },
    "performance": {
        "label": "Performance",
        "purpose": "Convert intent into sustainable action.",
    },
    "resilience": {
        "label": "Resilience / Life Operations",
        "purpose": "Apply operational-resilience thinking to human life systems.",
    },
}

# Critical personal services tracked by the resilience domain (doctrine §1).
CRITICAL_SERVICES = (
    "Work", "Sleep", "Mobility", "Dog care", "Relationships", "Learning", "Recovery",
)

# Energy-domain bands, best → worst.
BANDS = ("good", "moderate", "limited", "depleted")
_BAND_SCORE = {"good": 85, "moderate": 60, "limited": 35, "depleted": 15}
_BAND_ORDER = {b: i for i, b in enumerate(BANDS)}


def _band_from_score(score: float) -> str:
    if score >= 75:
        return "good"
    if score >= 55:
        return "moderate"
    if score >= 35:
        return "limited"
    return "depleted"


def _norm(value, default: str | None = None) -> str | None:
    if value is None:
        return default
    return str(value).strip().lower() or default


# ── Capacity snapshot (doctrine §8) ───────────────────────────────────────────

@dataclass
class EnergyDomain:
    key: str           # physical | cognitive | emotional | social
    label: str
    band: str          # good | moderate | limited | depleted
    score: float       # 0–100, operational only
    driver: str        # plain-language driver of the band


@dataclass
class CapacitySnapshot:
    domains: list[EnergyDomain] = field(default_factory=list)
    overall_band: str = "moderate"
    overall_score: float = 60.0
    data_available: bool = False
    headline: str = ""

    def domain(self, key: str) -> EnergyDomain | None:
        return next((d for d in self.domains if d.key == key), None)

    @property
    def limited_domains(self) -> list[EnergyDomain]:
        return [d for d in self.domains if d.band in ("limited", "depleted")]


def _sleep_score(row: dict) -> tuple[float, str]:
    hours = row.get("sleep_hours")
    quality = _norm(row.get("sleep_quality"))
    if hours is None and quality is None:
        return 50.0, "sleep not logged"
    score = 50.0
    driver = "sleep"
    if hours is not None:
        try:
            h = float(hours)
            score = max(0.0, min(100.0, (h / 7.5) * 70.0))
            driver = f"{h:.1f}h sleep"
        except (TypeError, ValueError):
            pass
    if quality == "good":
        score += 20
    elif quality == "fair":
        score += 8
    elif quality == "poor":
        score -= 12
        driver += ", poor quality"
    return max(0.0, min(100.0, score)), driver


def interpret_capacity(row: dict | None) -> CapacitySnapshot:
    """Derive a four-domain energy snapshot + daily capacity score from a row.

    ``row`` is a single ``analytics_health_daily`` record (or None). Missing
    fields degrade gracefully toward a neutral 'moderate' default rather than
    fabricating a reading.
    """
    if not row:
        snap = CapacitySnapshot(
            domains=[
                EnergyDomain(k, lbl, "moderate", 60.0, "no data logged")
                for k, lbl in (
                    ("physical", "Physical"), ("cognitive", "Cognitive"),
                    ("emotional", "Emotional"), ("social", "Social"),
                )
            ],
            overall_band="moderate",
            overall_score=60.0,
            data_available=False,
            headline="No check-in logged yet today. Consider a quick check-in to calibrate.",
        )
        return snap

    energy = _norm(row.get("energy"))
    ns = _norm(row.get("nervous_system_state"))
    mood = _norm(row.get("mood"))
    cap_rating = _norm(row.get("captain_capacity_rating"))
    pain = row.get("pain_score")
    sitting = row.get("sitting_tolerance_minutes")
    sleep_s, sleep_driver = _sleep_score(row)

    energy_score = {"high": 90, "moderate": 60, "low": 28}.get(energy, 55)
    ns_score = {"calm": 90, "activated": 52, "dysregulated": 22}.get(ns, 60)
    mood_score = {"positive": 85, "high": 85, "stable": 62, "moderate": 62, "low": 30}.get(mood, 58)

    pain_penalty = 0.0
    pain_note = ""
    if pain is not None:
        try:
            p = float(pain)
            pain_penalty = min(25.0, p * 2.5)  # contextual drag, never the target
            if p >= 6:
                pain_note = f", body signals high ({p:.0f}/10)"
        except (TypeError, ValueError):
            pass

    # Physical: sleep + energy − pain drag, nudged by sitting tolerance.
    phys = 0.45 * sleep_s + 0.45 * energy_score + 0.10 * 60 - pain_penalty
    if sitting is not None:
        try:
            s = float(sitting)
            phys += (min(s, 180) - 120) / 12  # baseline 120 min (ROS-001)
        except (TypeError, ValueError):
            pass
    phys = max(0.0, min(100.0, phys))
    phys_driver = f"{sleep_driver}, energy {energy or 'unknown'}{pain_note}"

    # Cognitive: sleep + nervous-system load drive focus / executive function.
    cog = 0.5 * sleep_s + 0.5 * ns_score
    cog = max(0.0, min(100.0, cog))
    cog_driver = f"{sleep_driver}, nervous system {ns or 'unknown'}"

    # Emotional: nervous-system state + mood.
    emo = 0.55 * ns_score + 0.45 * mood_score
    emo = max(0.0, min(100.0, emo))
    emo_driver = f"nervous system {ns or 'unknown'}, mood {mood or 'unknown'}"

    # Social: lighter signal — mood + nervous system, default conservative.
    soc = 0.5 * mood_score + 0.5 * ns_score
    soc = max(0.0, min(100.0, soc))
    soc_driver = "estimated from mood and nervous-system state"

    domains = [
        EnergyDomain("physical", "Physical", _band_from_score(phys), round(phys, 1), phys_driver),
        EnergyDomain("cognitive", "Cognitive", _band_from_score(cog), round(cog, 1), cog_driver),
        EnergyDomain("emotional", "Emotional", _band_from_score(emo), round(emo, 1), emo_driver),
        EnergyDomain("social", "Social", _band_from_score(soc), round(soc, 1), soc_driver),
    ]

    overall = mean([d.score for d in domains])
    # If the Captain self-rated capacity, let it pull the roll-up toward their read.
    if cap_rating in ("green", "amber", "red"):
        self_score = {"green": 82, "amber": 55, "red": 25}[cap_rating]
        overall = 0.6 * overall + 0.4 * self_score
    overall_band = _band_from_score(overall)

    limited = [d for d in domains if d.band in ("limited", "depleted")]
    if overall_band == "good":
        headline = "Capacity looks available today. A steady, sustainable load fits."
    elif overall_band == "moderate":
        headline = "Moderate capacity. Pace the day and protect the afternoon."
    elif overall_band == "limited":
        names = ", ".join(d.label.lower() for d in limited) or "several domains"
        headline = f"Limited capacity ({names}). This is a signal to lighten load today."
    else:
        headline = "Capacity is low today. Rest and protection are the priority."

    return CapacitySnapshot(
        domains=domains,
        overall_band=overall_band,
        overall_score=round(overall, 1),
        data_available=True,
        headline=headline,
    )


# ── Plan generation (doctrine §7.1) ───────────────────────────────────────────

PLAN_TYPES = ("low_capacity", "recovery", "movement", "nutrition", "mind")

_PLAN_ALIASES = {
    "low-capacity": "low_capacity", "low capacity": "low_capacity",
    "lowcap": "low_capacity", "low": "low_capacity",
    "recover": "recovery", "move": "movement", "exercise": "movement",
    "food": "nutrition", "eat": "nutrition", "diet": "nutrition",
    "focus": "mind", "cognitive": "mind", "overwhelm": "mind",
}


def normalise_plan_type(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower().replace("-", "_")
    if key in PLAN_TYPES:
        return key
    return _PLAN_ALIASES.get(raw.strip().lower())


def _intensity_for(band: str) -> str:
    return {
        "good": "steady", "moderate": "gentle",
        "limited": "minimal", "depleted": "rest-first",
    }.get(band, "gentle")


def build_plan(plan_type: str, snapshot: CapacitySnapshot) -> str:
    """Return a Captain-facing plan body (no safety footer — caller frames it)."""
    band = snapshot.overall_band
    intensity = _intensity_for(band)

    if plan_type == "low_capacity":
        return _low_capacity_plan(snapshot, intensity)
    if plan_type == "recovery":
        return _recovery_plan(snapshot, intensity)
    if plan_type == "movement":
        return _movement_plan(snapshot, intensity)
    if plan_type == "nutrition":
        return _nutrition_plan(snapshot)
    if plan_type == "mind":
        return _mind_plan(snapshot)
    return "I can build a low-capacity, recovery, movement, nutrition, or mind plan. Which would help?"


def _low_capacity_plan(snap: CapacitySnapshot, intensity: str) -> str:
    return "\n".join([
        "*Low-Capacity Day Plan*",
        f"_{snap.headline}_",
        "",
        "A practical shape for a protected day:",
        "• *One anchor only.* Pick a single must-do and let the rest be optional.",
        "• *Work in short blocks* (20–30 min) with real breaks between them.",
        "• *Movement:* the smallest gentle option — a short walk or some easy "
        "mobility. Consistency beats intensity.",
        "• *Nutrition anchors:* don't skip meals; protein + hydration steady the day.",
        "• *Nervous system:* one reset (breath, lie-down, outdoors) before the "
        "afternoon dip.",
        "• *Defer non-urgent decisions.* Low-capacity days are a poor time to "
        "commit to big things.",
        "",
        "This is a signal to lighten load, not to push through. The day still counts.",
    ])


def _recovery_plan(snap: CapacitySnapshot, intensity: str) -> str:
    limited = ", ".join(d.label.lower() for d in snap.limited_domains) or "general reserves"
    return "\n".join([
        "*Recovery Plan*",
        f"Based on the pattern, the domains asking for protection: *{limited}*.",
        "",
        "A practical recovery shape for the next few days:",
        "• *Sleep first.* A consistent wind-down and wake time does more than any "
        "single intervention.",
        "• *Pacing over pushing.* Plan to finish each block with something left in "
        "the tank.",
        "• *Gentle movement daily* to keep the system confident — not to train.",
        "• *Two nervous-system resets a day* (breath, somatic tracking, outdoors).",
        "• *Protect one genuinely restful window* and guard it like a mission slot.",
        "• *Connection:* one low-effort contact with someone steadying.",
        "",
        "Recovery is not repair. The aim is to give the system room to settle.",
    ])


def _movement_plan(snap: CapacitySnapshot, intensity: str) -> str:
    phys = snap.domain("physical")
    band = phys.band if phys else snap.overall_band
    if band in ("limited", "depleted"):
        core = [
            "• *3–5 min* of gentle mobility or a short walk, once daily.",
            "• Stop with capacity to spare — the goal is confidence, not fatigue.",
            "• A fallback on the hardest days: stand, breathe, and move through a "
            "comfortable range for 60 seconds.",
        ]
    elif band == "moderate":
        core = [
            "• *10–15 min* walk or easy mobility most days.",
            "• Add light strength only on steadier days, well within range.",
            "• Keep one rest day flexible — capacity, not the calendar, sets the pace.",
        ]
    else:
        core = [
            "• *20–30 min* of movement you enjoy, most days.",
            "• Progress gradually — small, repeatable increases beat big jumps.",
            "• Bank a smaller fallback session for lower-capacity days so the habit holds.",
        ]
    return "\n".join([
        "*Movement Plan (capacity-based, pain-aware)*",
        f"_Current physical capacity: {band}._",
        "",
        *core,
        "",
        "Movement is safe. We're protecting consistency and confidence, not "
        "chasing intensity. A practical next step could be choosing the time of "
        "day you're most likely to actually do it.",
    ])


def _nutrition_plan(snap: CapacitySnapshot) -> str:
    return "\n".join([
        "*Nutrition Support Plan*",
        "Practical anchors for stable energy and recovery — no restriction, no extremes:",
        "",
        "• *Protein at each meal* to support satiety and recovery.",
        "• *Hydration anchor:* a glass of water with each meal and on waking.",
        "• *Regular timing* steadies energy more than any single food choice.",
        "• *An easy fallback meal* you can make on low-capacity days, so eating "
        "well doesn't depend on having energy.",
        "• *Vegetables / fibre* where they fit, without making it a project.",
        "",
        "Consider keeping it simple and repeatable. If weight, energy or gut "
        "symptoms are a live concern, a dietitian or GP is the right call for "
        "tailored advice.",
    ])


def _mind_plan(snap: CapacitySnapshot) -> str:
    cog = snap.domain("cognitive")
    band = cog.band if cog else snap.overall_band
    return "\n".join([
        "*Mind / Cognitive Load Plan*",
        f"_Current cognitive capacity: {band}._",
        "",
        "When the load feels high, treat overwhelm as a capacity signal rather "
        "than a to-do list:",
        "• *Name the next smallest meaningful action* — just one.",
        "• *Externalise the rest:* park everything else on a list so it's not "
        "running in the background.",
        "• *One block at a time*, with a defined start and stop.",
        "• *A 2-minute reset* (breath or a short walk) before switching tasks.",
        "• *Defer decisions* that don't have to be made under load today.",
        "",
        "A practical next step could be choosing the single action and starting a "
        "short timer for it.",
    ])


# ── Signal explanation (doctrine §7) ──────────────────────────────────────────

def explain_signal(row: dict | None) -> str:
    """Interpret one day's pattern as information, not a verdict."""
    snap = interpret_capacity(row)
    if not snap.data_available:
        return (
            "No check-in is logged yet, so there's no pattern to read today. "
            "A quick check-in would let the system calibrate."
        )
    lines = [
        "*Reading today's signal*",
        f"_{snap.headline}_",
        "",
    ]
    for d in snap.domains:
        lines.append(f"• *{d.label}:* {d.band} — {d.driver}.")
    pain = row.get("pain_score") if row else None
    if pain is not None:
        lines += [
            "",
            "Body signals are treated as information, not a damage readout — they "
            "describe the nervous system's current state, not the day's worth.",
        ]
    lines += [
        "",
        "Based on the pattern, this *may* suggest where to spend and where to "
        "protect energy. It is not a diagnosis.",
    ]
    return "\n".join(lines)


# ── Weekly Human Systems review (doctrine §7.2) ───────────────────────────────

def _trend(values: list[float]) -> str:
    if len(values) < 3:
        return "insufficient_data"
    first = mean(values[: max(1, len(values) // 2)])
    last = mean(values[len(values) // 2:])
    delta = last - first
    if delta >= 6:
        return "improving"
    if delta <= -6:
        return "declining"
    return "steady"


def weekly_review(rows: list[dict]) -> str:
    """Synthesise a run of daily rows into a Human Systems weekly review.

    ``rows`` may be in any order; newest-first or oldest-first both work.
    """
    if not rows:
        return (
            "*Weekly Human Systems Review*\n"
            "No check-ins logged in the period. A few quick check-ins would give "
            "the system something to read next week."
        )

    ordered = sorted(rows, key=lambda r: str(r.get("log_date") or ""))
    snaps = [interpret_capacity(r) for r in ordered]
    overall_scores = [s.overall_score for s in snaps]
    direction = _trend(overall_scores)

    # Nervous-system tally (emotional-load leading indicator).
    ns_counts: dict[str, int] = {}
    sleep_vals: list[float] = []
    for r in ordered:
        ns = _norm(r.get("nervous_system_state"))
        if ns:
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        sh = r.get("sleep_hours")
        if sh is not None:
            try:
                sleep_vals.append(float(sh))
            except (TypeError, ValueError):
                pass

    dysreg = ns_counts.get("dysregulated", 0)
    activated = ns_counts.get("activated", 0)
    avg_sleep = mean(sleep_vals) if sleep_vals else None

    direction_label = {
        "improving": "Capacity has trended up across the period.",
        "declining": "Capacity has trended down across the period — worth a lighter plan ahead.",
        "steady": "Capacity has held broadly steady.",
        "insufficient_data": "Not enough days logged to read a clear direction.",
    }[direction]

    lines = [
        "*Weekly Human Systems Review*",
        f"_{len(ordered)} day(s) logged · average capacity {round(mean(overall_scores))}/100_",
        "",
        f"📈 *Trend* — {direction_label}",
    ]

    if dysreg + activated >= 3:
        lines.append(
            f"⚠️ *Risk signal* — {dysreg} dysregulated and {activated} activated "
            "day(s). This is a signal to review load and protect recovery, not a "
            "reflection on the Captain."
        )
    else:
        lines.append(
            f"ℹ️ *Nervous system* — {ns_counts.get('calm', 0)} calm day(s) logged. "
            "The system has been settling."
        )

    if avg_sleep is not None:
        sleep_note = "supportive" if avg_sleep >= 7 else "a likely drag on capacity"
        lines.append(f"ℹ️ *Sleep* — averaged {avg_sleep:.1f}h, {sleep_note}.")

    worst = min(snaps, key=lambda s: s.overall_score)
    if worst.limited_domains:
        focus = ", ".join(d.label.lower() for d in worst.limited_domains)
        lines.append(
            f"✅ *Where to protect next week* — {focus}. A practical next step "
            "could be building one small recovery anchor around it."
        )

    lines.append(
        "\nConsider this a capacity review, not a scorecard. The aim is to spot "
        "the pattern early and adjust load before it costs more."
    )
    return "\n".join(lines)
