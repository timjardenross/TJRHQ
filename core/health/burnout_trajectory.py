"""
TJR Human Systems Workbench V3 — Burnout / Sustained-Strain Trajectory Engine.

See TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md, the
mission spec this module implements (referenced throughout below as
"V3 doc"). This is Mission 1's stated #1 priority: a TRAJECTORY signal —
"what condition has my system been operating in over days/weeks?" — kept
strictly separate from the existing NOW signal (deriveSystemPosture() in
lcars-portal/src/app/api/human-systems/route.ts, which stays unchanged).
V3 doc §2: "These must never be collapsed into one score."

Deterministic only — no ML, no LLM (V3 doc §22 "Rules A-G", §35: "The
workbench should not require an LLM for basic operation... start
deterministic"). Every threshold below is a plain if/elif rule with an
inline rationale comment, same discipline as core/health/capacity_score.py
(configurable WEIGHTS dict) and telegram-bots/capacitybot/
intervention_engine.py (documented scoring rules) — this module has no
weights dict because V3 doc §14 explicitly forbids a weighted numeric
score for burnout ("Weight nothing numerically into a fake score — bucket
into the 7 states via clear threshold rules").

TypeScript mirror: lcars-portal/src/app/api/human-systems/route.ts's
computeStrategicPosture() (search that name) — the two must be kept in
lock-step the same way intervention_engine.py and route.ts's
computeInterventionEffectiveness() are already documented as mirroring
each other. Any threshold change here must be made there too.

Public API:
    from core.health.burnout_trajectory import compute_burnout_trajectory

    profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="ENGAGE")
    # profile is a dict matching every non-identity column of the
    # `burnout_profile` table (migration 0154) — callers insert it (plus
    # window_days/computed_at bookkeeping the caller already controls)
    # directly as a row.
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Thresholds — named constants so each rule below reads as a sentence and a
# recalibration only ever touches one line (same pattern as capacity_score's
# WEIGHTS / CAPACITY_THRESHOLDS dicts).
# ---------------------------------------------------------------------------

# V3 doc §22 Rule F: "If data is insufficient: say `insufficient data`; do
# not fabricate a trajectory." Below this many quick check-ins in the
# window, no trajectory claim is made at all, regardless of how extreme the
# few available readings look.
MIN_CHECKINS_FOR_TRAJECTORY = 5

# Confidence bands, sample-size only (no time-coverage claim beyond what the
# caller's window_days already implies) — same "counts first, don't imply
# more certainty than the sample supports" discipline as intervention_
# engine.py's MIN_SAMPLE_FOR_WEIGHTING.
MIN_CHECKINS_FOR_MODERATE_CONFIDENCE = 8
MIN_CHECKINS_FOR_HIGH_CONFIDENCE = 12
MIN_EVENING_ROWS_FOR_HIGH_CONFIDENCE = 5

# burnout_like_depletion — the most severe bucket. Requires BOTH a severe
# capacity read (mostly red, not just orange) AND corroborating evidence
# from a second, independent dimension (functional accessibility, tolerance,
# or compensation cost) — never capacity_state alone (V3 doc §14: "Burnout
# Load... derive a cautious trend from COMBINATIONS of" signals, not one).
BURNOUT_LIKE_ORANGE_RED_PCT = 0.75
BURNOUT_LIKE_RED_PCT = 0.4
BURNOUT_LIKE_EVENING_DEBT_YES = 2

# sustained_high_strain — the spec's own worked example threshold (V3 doc
# implementation brief): "≥60% of check-ins orange/red AND ≥2 evening
# capacity_debt='yes' in window".
SUSTAINED_HIGH_ORANGE_RED_PCT = 0.6
SUSTAINED_HIGH_EVENING_DEBT_YES = 2

# accumulating_strain — meaningful strain signal present but not yet
# sustained/severe. Any one of these alone is enough to leave "stable"
# (V3 doc Rule C: elevate concern even when capacity itself still looks
# acceptable — see the ef_worsening/tolerance_falling branch specifically).
ACCUMULATING_ORANGE_RED_PCT = 0.4
ACCUMULATING_COMPENSATION_HIGH_PCT = 0.5
ACCUMULATING_EVENING_DEBT_YES_OR_MAYBE = 3

# Executive-function / tolerance trend comparison — window split into an
# earlier and later half (chronological), each half needs at least this
# many readings before a trend claim is made from it (too few and the
# "trend" is noise, not signal — same "insufficient data, say so" caution
# applied at the sub-metric level).
MIN_ROWS_PER_HALF_FOR_TREND = 2

# Ordinal difficulty scale for executive_function — good=0 is easiest,
# very_difficult=3 is hardest. A rise of this much between the window's
# earlier and later half counts as "worsening" (half a step on a 4-point
# scale — e.g. average moving from "good" to consistently "strained").
EF_ORDINAL = {"good": 0, "strained": 1, "difficult": 2, "very_difficult": 3}
EF_WORSENING_DELTA = 0.5

# Tolerance / stimulation mismatch — fraction of readings at either extreme
# (low or high, i.e. NOT 'balanced') rising by this many percentage points
# between the earlier and later half counts as "falling tolerance" (V3 doc
# §6.3: "Has my tolerance changed from my own baseline?").
TOLERANCE_EXTREME_RATE_RISE = 0.25

# Recovery-duration "elevated" bucket — Half a day or longer (mirrors
# lcars-portal's RECOVERY_DURATION_LABEL/rdBand ordering in
# api/human-systems/route.ts, where these three map to 'limited'/'rest').
ELEVATED_RECOVERY_DURATION_LABELS = {"Half a day", "Full day", "Multiple days"}
ELEVATED_RECOVERY_DURATION_CODES = {"hd", "fd", "md"}
RECOVERY_DURATION_RISE_DELTA = 0.34  # roughly "one more elevated reading" on a small deep-check sample

# recovery_trajectory (spec §6.5) halves comparison thresholds.
RECOVERY_IMPROVING_DELTA = -0.2
RECOVERY_DETERIORATING_DELTA = 0.2

# ---------------------------------------------------------------------------
# Strategic posture rank — lower is more protective/cautious, higher is more
# permissive. Shared vocabulary with Today's Posture (engage/steady/protect/
# recover, lowercased) so Rule A is a same-scale comparison, not a
# translation — plus the additional Burnout Recovery Stage postures (V3 doc
# §8) Today's Posture has no equivalent for. `redesign` is a valid
# burnout_profile.strategic_posture value per the schema but is
# deliberately never emitted by this engine — it names a STRUCTURAL
# response ("change recurring conditions"), not a day-to-day load level,
# and the platform's existing redesign-candidate detection
# (computeRedesignCandidates() in api/human-systems/route.ts) already owns
# that surface; folding it into this rank would conflate two different
# axes of "what to do next".
# ---------------------------------------------------------------------------

POSTURE_RANK = {
    "recover": 0,
    "protect": 1,
    "stabilise": 2,
    "steady": 3,
    "re_engage": 4,
    "rebuild": 5,
    "engage": 6,
}
_RANK_TO_POSTURE = {v: k for k, v in POSTURE_RANK.items()}

# Today's Posture (SystemPostureBand, deriveSystemPosture() in route.ts) ->
# strategic-posture vocabulary. RESET (a short regulation-first detour, no
# strategic equivalent) maps to 'protect' — the most conservative of the
# postures RESET could plausibly imply, never to 'recover' (RESET is not
# the same as depleted) and never to anything more permissive. UNKNOWN/None
# (no check-in today) maps to the neutral middle, 'steady' — cautious
# default, matches V3 doc §5's instruction to never fabricate a NOW claim
# when there's no check-in to read it from.
TODAY_POSTURE_TO_STRATEGIC = {
    "ENGAGE": "engage",
    "STEADY": "steady",
    "PROTECT": "protect",
    "RECOVER": "recover",
    "RESET": "protect",
    "UNKNOWN": "steady",
}

# system_trajectory -> the most protective strategic posture that
# trajectory permits, regardless of how good today looks (V3 doc Rule A).
# 'stable' has no floor — trajectory imposes no extra caution beyond
# today's own reading. 'insufficient_data' is handled separately, before
# this table is ever consulted (Rule F).
TRAJECTORY_FLOOR = {
    "burnout_like_depletion": "recover",
    "sustained_high_strain": "protect",
    "accumulating_strain": "protect",
    "recovery_signals_emerging": "stabilise",
    "rebuilding": "re_engage",
    "stable": None,
}

# V3 doc §8's stage names, one per trajectory bucket where a stage applies.
# 'stable' and 'insufficient_data' have no active recovery stage — there is
# nothing to stage a return from.
TRAJECTORY_TO_RECOVERY_STAGE = {
    "accumulating_strain": "protect",
    "sustained_high_strain": "stabilise",
    "burnout_like_depletion": "recover",
    "recovery_signals_emerging": "re_engage",
    "rebuilding": "rebuild",
}

_STRATEGIC_MESSAGES = {
    "insufficient_data": (
        "Not enough recent check-ins yet to read a sustained-strain trend — "
        "today's own posture is what's guiding this."
    ),
    "stable": (
        "No sustained-strain pattern showing in the recent window — "
        "today's own posture applies without a trajectory adjustment."
    ),
    "accumulating_strain": (
        "Sustained strain appears to be building. Favour steady or "
        "protective pacing even on an easier day."
    ),
    "sustained_high_strain": (
        "Recent recovery demand has stayed high. Strategic posture stays "
        "protective — a better day today isn't evidence the wider strain "
        "has resolved."
    ),
    "burnout_like_depletion": (
        "Sustained strain and recovery demand have stayed high for a while. "
        "Recovery is the priority — use any extra capacity selectively "
        "rather than as proof of recovery."
    ),
    "recovery_signals_emerging": (
        "Some early signs of easing strain in the recent window — worth "
        "stabilising conditions before adding load back in."
    ),
    "rebuilding": (
        "Recovery has been holding across the recent window — capacity can "
        "be reintroduced gradually, watching for recovery demand to rise "
        "again."
    ),
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _sort_key(row: dict) -> str:
    """Chronological sort key — prefers captured_at, falls back to
    log_date, then "" (stable sort keeps original order when neither is
    present, never crashes on a legacy/partial row)."""
    return str(row.get("captured_at") or row.get("log_date") or "")


def _split_halves(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Chronological earlier/later halves for trend comparisons. Odd counts
    give the extra row to the later half (slightly favours detecting a
    recent change over an old one, since recency is what "trajectory"
    means here)."""
    ordered = sorted(rows, key=_sort_key)
    mid = len(ordered) // 2
    return ordered[:mid], ordered[mid:]


def _rate(rows: list[dict], predicate) -> Optional[float]:
    if not rows:
        return None
    return sum(1 for r in rows if predicate(r)) / len(rows)


def _ef_ordinal_avg(rows: list[dict]) -> Optional[float]:
    vals = [EF_ORDINAL[r["executive_function"]] for r in rows if r.get("executive_function") in EF_ORDINAL]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _is_elevated_recovery_duration(value: Any) -> bool:
    return value in ELEVATED_RECOVERY_DURATION_LABELS or value in ELEVATED_RECOVERY_DURATION_CODES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_burnout_trajectory(
    checkins: list[dict],
    window_days: int = 21,
    today_posture: Optional[str] = None,
) -> dict:
    """Derive a `burnout_profile` row from a window of `capacity_checkins`
    rows.

    Args:
        checkins: every capacity_checkins row in the window (both
            checkin_type='capacity' and 'evening' rows — this function
            filters internally). Rows may be missing any/all of the V3
            (0153) fields or even the 0152 fields — legacy rows must never
            crash this function (V3 doc §32: "legacy records with missing
            V3 fields" is an explicit testing requirement).
        window_days: the window these `checkins` were queried over (not
            re-derived from the rows themselves — the caller's query
            already defines it, and an empty/sparse window shouldn't be
            allowed to shrink the number reported).
        today_posture: today's SystemPostureBand
            (deriveSystemPosture()'s .posture in route.ts —
            'ENGAGE'|'STEADY'|'PROTECT'|'RECOVER'|'RESET'|'UNKNOWN'|None).
            Used only as the strategic-posture fallback/ceiling — this
            function never recomputes or overrides Today's Posture itself.

    Returns:
        A dict with every column `burnout_profile` (migration 0154) needs
        except `id`/`computed_at`/`created_at` (caller/DB-default owned).
    """
    capacity_rows = [c for c in checkins if c.get("capacity_state")]
    evening_rows = [c for c in checkins if c.get("checkin_type") == "evening"]
    deep_rows = [c for c in checkins if c.get("recovery_duration")]

    relevant_checkin_count = len(capacity_rows)

    contributing_signals: dict[str, Any] = {
        "window_days": window_days,
        "relevant_checkin_count": relevant_checkin_count,
        "evening_row_count": len(evening_rows),
        "deep_checkin_count": len(deep_rows),
    }

    # ── Rule F — insufficient data, never fabricate a trajectory ─────────
    if relevant_checkin_count < MIN_CHECKINS_FOR_TRAJECTORY:
        strategic_posture = TODAY_POSTURE_TO_STRATEGIC.get(today_posture or "UNKNOWN", "steady")
        return {
            "window_days": window_days,
            "system_trajectory": "insufficient_data",
            "trajectory_confidence": "low",
            "relevant_checkin_count": relevant_checkin_count,
            "exhaustion_level": None,
            "tolerance_change": None,
            "recovery_trajectory": "insufficient_data",
            "current_recovery_stage": None,
            "strategic_posture": strategic_posture,
            "strategic_posture_message": _STRATEGIC_MESSAGES["insufficient_data"],
            "contributing_signals": contributing_signals,
        }

    # ── Whole-window aggregates ───────────────────────────────────────────
    orange_red_pct = _rate(capacity_rows, lambda r: r["capacity_state"] in ("orange", "red")) or 0.0
    red_pct = _rate(capacity_rows, lambda r: r["capacity_state"] == "red") or 0.0
    evening_debt_yes = sum(1 for r in evening_rows if r.get("capacity_debt") == "yes")
    evening_debt_yes_or_maybe = sum(1 for r in evening_rows if r.get("capacity_debt") in ("yes", "maybe"))
    compensation_high_pct = _rate(capacity_rows, lambda r: r.get("compensation_load") in ("high", "extreme")) or 0.0

    # ── Executive-function trend (Rule C — functional accessibility) ─────
    ef_earlier, ef_later = _split_halves(capacity_rows)
    ef_avg_earlier = _ef_ordinal_avg(ef_earlier)
    ef_avg_later = _ef_ordinal_avg(ef_later)
    ef_worsening = (
        len(ef_earlier) >= MIN_ROWS_PER_HALF_FOR_TREND
        and len(ef_later) >= MIN_ROWS_PER_HALF_FOR_TREND
        and ef_avg_earlier is not None
        and ef_avg_later is not None
        and (ef_avg_later - ef_avg_earlier) >= EF_WORSENING_DELTA
    )

    # ── Tolerance / stimulation-extreme trend ─────────────────────────────
    stim_earlier, stim_later = _split_halves(capacity_rows)
    extreme_rate_earlier = _rate(stim_earlier, lambda r: r.get("stimulation_state") in ("low", "high"))
    extreme_rate_later = _rate(stim_later, lambda r: r.get("stimulation_state") in ("low", "high"))
    tolerance_falling = (
        len(stim_earlier) >= MIN_ROWS_PER_HALF_FOR_TREND
        and len(stim_later) >= MIN_ROWS_PER_HALF_FOR_TREND
        and extreme_rate_earlier is not None
        and extreme_rate_later is not None
        and (extreme_rate_later - extreme_rate_earlier) >= TOLERANCE_EXTREME_RATE_RISE
    )

    # ── Recovery-duration trend (Rule D) ──────────────────────────────────
    rd_earlier, rd_later = _split_halves(deep_rows)
    rd_rate_earlier = _rate(rd_earlier, lambda r: _is_elevated_recovery_duration(r.get("recovery_duration")))
    rd_rate_later = _rate(rd_later, lambda r: _is_elevated_recovery_duration(r.get("recovery_duration")))
    recovery_duration_rising = (
        len(rd_earlier) >= MIN_ROWS_PER_HALF_FOR_TREND
        and len(rd_later) >= MIN_ROWS_PER_HALF_FOR_TREND
        and rd_rate_earlier is not None
        and rd_rate_later is not None
        and (rd_rate_later - rd_rate_earlier) >= RECOVERY_DURATION_RISE_DELTA
    )

    # ── recovery_trajectory (spec §6.5) — capacity-state halves comparison ─
    cap_earlier, cap_later = _split_halves(capacity_rows)
    orange_red_earlier = _rate(cap_earlier, lambda r: r["capacity_state"] in ("orange", "red"))
    orange_red_later = _rate(cap_later, lambda r: r["capacity_state"] in ("orange", "red"))
    if (
        len(cap_earlier) < MIN_ROWS_PER_HALF_FOR_TREND
        or len(cap_later) < MIN_ROWS_PER_HALF_FOR_TREND
        or orange_red_earlier is None
        or orange_red_later is None
    ):
        recovery_trajectory = "insufficient_data"
    else:
        delta = orange_red_later - orange_red_earlier
        if delta <= RECOVERY_IMPROVING_DELTA:
            recovery_trajectory = "improving"
        elif delta >= RECOVERY_DETERIORATING_DELTA:
            recovery_trajectory = "deteriorating"
        elif ef_worsening or tolerance_falling:
            # Capacity itself looks roughly flat, but a corroborating
            # dimension is moving the wrong way — call this volatile
            # rather than stable (Rule C: don't let a flat capacity_state
            # read mask a worsening functional-accessibility signal).
            recovery_trajectory = "volatile"
        else:
            recovery_trajectory = "stable"

    contributing_signals.update({
        "orange_red_pct": round(orange_red_pct, 3),
        "red_pct": round(red_pct, 3),
        "evening_debt_yes_count": evening_debt_yes,
        "evening_debt_yes_or_maybe_count": evening_debt_yes_or_maybe,
        "compensation_high_pct": round(compensation_high_pct, 3),
        "ef_worsening": ef_worsening,
        "tolerance_falling": tolerance_falling,
        "recovery_duration_rising": recovery_duration_rising,
        "recovery_trajectory": recovery_trajectory,
    })

    # ── system_trajectory bucket — first matching rule wins, most severe
    # checked first (V3 doc §22, thresholds named above) ─────────────────
    if (
        orange_red_pct >= BURNOUT_LIKE_ORANGE_RED_PCT
        and red_pct >= BURNOUT_LIKE_RED_PCT
        and evening_debt_yes >= BURNOUT_LIKE_EVENING_DEBT_YES
        and (ef_worsening or tolerance_falling or compensation_high_pct >= ACCUMULATING_COMPENSATION_HIGH_PCT)
    ):
        system_trajectory = "burnout_like_depletion"
    elif orange_red_pct >= SUSTAINED_HIGH_ORANGE_RED_PCT and evening_debt_yes >= SUSTAINED_HIGH_EVENING_DEBT_YES:
        system_trajectory = "sustained_high_strain"
    elif (
        orange_red_pct >= ACCUMULATING_ORANGE_RED_PCT
        or (ef_worsening and tolerance_falling)
        or compensation_high_pct >= ACCUMULATING_COMPENSATION_HIGH_PCT
        or evening_debt_yes_or_maybe >= ACCUMULATING_EVENING_DEBT_YES_OR_MAYBE
        or recovery_trajectory == "deteriorating"
    ):
        # Rule C: elevate concern even when capacity_state alone still
        # looks acceptable, if a corroborating signal (functional
        # accessibility, compensation, capacity debt, or a deteriorating
        # trend) says otherwise — Scenario 3's acceptance test.
        system_trajectory = "accumulating_strain"
    elif recovery_trajectory == "improving" and orange_red_earlier is not None and orange_red_earlier >= ACCUMULATING_ORANGE_RED_PCT:
        # Was genuinely strained earlier in the window and has been
        # improving since — distinct from "rebuilding" below, which
        # additionally requires the LATER half to already be clearly good.
        later_is_good = orange_red_later is not None and orange_red_later < ACCUMULATING_ORANGE_RED_PCT
        later_evening_clear = not any(r.get("capacity_debt") == "yes" for r in _split_halves(evening_rows)[1])
        if later_is_good and later_evening_clear and len(cap_later) >= MIN_ROWS_PER_HALF_FOR_TREND:
            system_trajectory = "rebuilding"
        else:
            system_trajectory = "recovery_signals_emerging"
    else:
        system_trajectory = "stable"

    # ── trajectory_confidence — sample-size only (V3 doc §18 "Confidence"
    # line, e.g. "Moderate — 12 relevant check-ins across 18 days") ───────
    if (
        relevant_checkin_count >= MIN_CHECKINS_FOR_HIGH_CONFIDENCE
        and len(evening_rows) >= MIN_EVENING_ROWS_FOR_HIGH_CONFIDENCE
    ):
        trajectory_confidence = "high"
    elif relevant_checkin_count >= MIN_CHECKINS_FOR_MODERATE_CONFIDENCE:
        trajectory_confidence = "moderate"
    else:
        trajectory_confidence = "low"

    # ── exhaustion_level / tolerance_change — plain-language descriptors,
    # not a fixed enum (V3 doc §6.1/§6.3 deliberately leave these open) ───
    if red_pct >= BURNOUT_LIKE_RED_PCT:
        exhaustion_level = "high"
    elif orange_red_pct >= ACCUMULATING_ORANGE_RED_PCT:
        exhaustion_level = "elevated"
    elif orange_red_pct > 0:
        exhaustion_level = "moderate"
    else:
        exhaustion_level = "low"

    tolerance_change = "reduced" if tolerance_falling else "stable"

    current_recovery_stage = TRAJECTORY_TO_RECOVERY_STAGE.get(system_trajectory)

    # ── strategic_posture — Rule A/D, mechanically enforced via rank ─────
    today_rank = POSTURE_RANK[TODAY_POSTURE_TO_STRATEGIC.get(today_posture or "UNKNOWN", "steady")]
    floor_name = TRAJECTORY_FLOOR.get(system_trajectory)
    final_rank = min(today_rank, POSTURE_RANK[floor_name]) if floor_name else today_rank

    # Rule D — a rising recovery-duration trend clamps the ceiling even if
    # trajectory/today's posture alone would allow more load.
    if recovery_duration_rising:
        final_rank = min(final_rank, POSTURE_RANK["stabilise"])

    # V3 doc §8.5 — "Rebuild must be gated. Do not recommend capacity
    # expansion simply because one or two good check-ins occurred." Reached
    # only when the WHOLE window's later half already qualified as
    # 'rebuilding' (a sustained trend, not 1-2 days) AND today's own
    # posture independently corroborates it AND recovery duration isn't
    # trending back up.
    if system_trajectory == "rebuilding" and today_posture == "ENGAGE" and not recovery_duration_rising:
        final_rank = POSTURE_RANK["rebuild"]

    strategic_posture = _RANK_TO_POSTURE[final_rank]
    strategic_posture_message = _STRATEGIC_MESSAGES[system_trajectory]

    return {
        "window_days": window_days,
        "system_trajectory": system_trajectory,
        "trajectory_confidence": trajectory_confidence,
        "relevant_checkin_count": relevant_checkin_count,
        "exhaustion_level": exhaustion_level,
        "tolerance_change": tolerance_change,
        "recovery_trajectory": recovery_trajectory,
        "current_recovery_stage": current_recovery_stage,
        "strategic_posture": strategic_posture,
        "strategic_posture_message": strategic_posture_message,
        "contributing_signals": contributing_signals,
    }
