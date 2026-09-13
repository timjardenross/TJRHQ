"""Capacity Bot — Personal Causal-Effect Estimator (evidence engine).

Closes a real, verified gap: `capacity_interventions.evidence_strength` /
`evidence_basis` have sat unpopulated (defaulting to 'unknown') for all 30
seeded interventions since migration 0157 — but that pair of columns is
explicitly reserved for *general* (literature/guideline) evidence, per
0157's own comments: "general evidence tells you what's worth trying,
personal outcome data ... tells you what has actually worked for this
individual" and "Never combine with personal effectiveness
(capacity_intervention_events) into a single confidence number." Writing a
personal causal estimate into evidence_strength/evidence_basis would be
exactly the anti-pattern that migration warns against.

So this module does NOT touch evidence_strength/evidence_basis. It adds a
parallel, clearly-separate set of columns (migration
0202_capacity_interventions_personal_causal_effect.sql,
`personal_causal_effect*`) holding a *personal* estimate: did this
intervention coincide with a real shift in this individual's own
capacity_checkins history, using tfcausalimpact (a Bayesian structural
time-series counterfactual — Google's CausalImpact, ported to
Python/TensorFlow-Probability)?

Method, plainly stated (know its limits):
  - Treatment onset = the EARLIEST capacity_intervention_events.started_at
    for that intervention_id — i.e. "when this entered rotation", not a
    designed A/B experiment. Only one onset point is used even if the
    intervention was tried many times since; this cannot separate that
    first shift from anything else that also changed around the same date
    (the classic causal-inference caveat — this is observational, not
    experimental, evidence).
  - Outcome series = one capacity score per calendar day, built by
    averaging core.health.capacity_score.capacity_zone_from_checkin()'s
    nominal zone score (green=90/orange=60/red=25) across that day's
    checkin_type='capacity' rows in capacity_checkins. Reuses the exact
    same zone mapping the rest of the platform already treats as the
    capacity proxy — this module does not invent a new score.
  - Requires a minimum number of both pre- and post-onset days with actual
    check-in data (MIN_PRE_DAYS / MIN_POST_DAYS) before it will write
    anything. Below that, it writes nothing and leaves the columns null —
    same "never let missing evidence quietly read as validated" discipline
    0157 itself applies to evidence_strength.

Environment note: tfcausalimpact + pandas are NOT declared anywhere in this
bot's requirements.txt yet (added by this change) and could not be
installed/exercised in the authoring sandbox (large TensorFlow-Probability
wheel, network timeout). The pandas/causalimpact call itself
(_fit_causal_impact) is written directly against the library's documented
API (README + source, verified 2026-09-13) and is intentionally isolated
behind one small function so it can be smoke-tested in an environment that
actually has the dependency installed before this runs on a schedule —
every function around it (window sufficiency checks, day aggregation,
Supabase read/write, CLI) is unit-tested without needing the real library.

CLI:
    python3 telegram-bots/capacitybot/evidence_engine.py [--dry-run] [--intervention-id ID]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.health.capacity_score import capacity_zone_from_checkin  # noqa: E402
from intervention_engine import TABLE as INTERVENTIONS_TABLE  # noqa: E402

CHECKINS_TABLE = "capacity_checkins"

# Below these, the pre/post windows are too thin to trust a structural
# time-series fit on noisy daily self-report data — write nothing rather
# than manufacture false confidence.
MIN_PRE_DAYS = 10
MIN_POST_DAYS = 10

# Never pull more history than this on either side of onset — bounds both
# the Supabase query and the cost of the model fit. A slow-building effect
# beyond ~90 days either way is out of scope for this pass.
LOOKBACK_CAP_DAYS = 90

# Column names on capacity_interventions written by this module (migration
# 0202) — deliberately disjoint from evidence_strength/evidence_basis.
EFFECT_COLUMN = "personal_causal_effect"
CI_LOWER_COLUMN = "personal_causal_effect_ci_lower"
CI_UPPER_COLUMN = "personal_causal_effect_ci_upper"
P_VALUE_COLUMN = "personal_causal_effect_p_value"
SUMMARY_COLUMN = "personal_causal_effect_summary"
COMPUTED_AT_COLUMN = "personal_causal_effect_computed_at"


@dataclass
class EvidenceEstimate:
    intervention_id: str
    onset: date
    pre_days: int
    post_days: int
    effect: float
    ci_lower: float
    ci_upper: float
    p_value: float

    @property
    def significant(self) -> bool:
        """95% credible interval excludes zero."""
        return self.ci_lower > 0 or self.ci_upper < 0

    def summary_text(self) -> str:
        direction = "higher" if self.effect >= 0 else "lower"
        caveat = "" if self.significant else " (not significant — 95% interval includes zero)"
        return (
            f"Personal causal-impact estimate: capacity ran {abs(self.effect):.1f} pts {direction} "
            f"than the pre-intervention baseline would predict "
            f"(95% CI {self.ci_lower:+.1f} to {self.ci_upper:+.1f}, p={self.p_value:.3f}, "
            f"n={self.pre_days} pre / {self.post_days} post day{'s' if self.post_days != 1 else ''} "
            f"of check-ins){caveat}. Observational, not a controlled trial — "
            f"other things may have changed around the same date."
        )

    def to_payload(self, computed_at: str | None = None) -> dict:
        return {
            EFFECT_COLUMN: round(self.effect, 2),
            CI_LOWER_COLUMN: round(self.ci_lower, 2),
            CI_UPPER_COLUMN: round(self.ci_upper, 2),
            P_VALUE_COLUMN: round(self.p_value, 4),
            SUMMARY_COLUMN: self.summary_text(),
            COMPUTED_AT_COLUMN: computed_at or datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class _Window:
    pre_start: date
    pre_end: date
    post_start: date
    post_end: date
    pre_days: int
    post_days: int


def _prepare_window(
    series: dict[date, float],
    onset: date,
    *,
    today: date | None = None,
    min_pre_days: int = MIN_PRE_DAYS,
    min_post_days: int = MIN_POST_DAYS,
    lookback_cap_days: int = LOOKBACK_CAP_DAYS,
) -> _Window | None:
    """Pure function, no I/O, no pandas — bounds the pre/post date ranges
    around `onset` and counts how many days in `series` actually have data
    in each. Returns None (write nothing) if either side is short of its
    minimum. Days with no check-in at all are not fabricated — they are
    simply absent from `series` and don't count toward pre_days/post_days.
    """
    today = today or datetime.now(timezone.utc).date()
    pre_start = onset - timedelta(days=lookback_cap_days)
    pre_end = onset - timedelta(days=1)
    post_start = onset
    post_end = min(today, onset + timedelta(days=lookback_cap_days))

    if post_end < post_start:
        return None  # onset is in the future relative to `today` — nothing to measure yet

    pre_days = sum(1 for d, v in series.items() if pre_start <= d <= pre_end and v is not None)
    post_days = sum(1 for d, v in series.items() if post_start <= d <= post_end and v is not None)

    if pre_days < min_pre_days or post_days < min_post_days:
        return None

    return _Window(pre_start, pre_end, post_start, post_end, pre_days, post_days)


def _fit_causal_impact(
    series: dict[date, float],
    window: _Window,
) -> tuple[float, float, float, float] | None:
    """The one function in this module that needs pandas + tfcausalimpact.
    Lazy-imported (both are heavy, optional-until-needed dependencies —
    same convention as capacitybot/app.py's lazy `from supabase import
    create_client`). Returns (effect, ci_lower, ci_upper, p_value) or None
    on any failure — a model-fit failure must never crash the caller, same
    posture as every other external/model call in this codebase.
    """
    try:
        import pandas as pd
        from causalimpact import CausalImpact
    except ImportError as exc:  # pragma: no cover - environment-dependent
        log.error("tfcausalimpact/pandas not installed — cannot compute personal causal effect: %s", exc)
        return None

    all_days = [
        window.pre_start + timedelta(days=i)
        for i in range((window.post_end - window.pre_start).days + 1)
    ]
    # Missing days are left as NaN rather than forward-filled — the
    # structural time-series model this fits (Bayesian BSTS) is designed
    # to marginalize over missing observations rather than have them
    # faked, which forward-filling would do.
    frame = pd.DataFrame(
        {"y": [series.get(d) for d in all_days]},
        index=pd.to_datetime(all_days),
    )

    pre_period = [window.pre_start.isoformat(), window.pre_end.isoformat()]
    post_period = [window.post_start.isoformat(), window.post_end.isoformat()]

    try:
        ci = CausalImpact(frame, pre_period, post_period)
        summary = ci.summary_data
        effect = float(summary.loc["abs_effect", "average"])
        ci_lower = float(summary.loc["abs_effect_lower", "average"])
        ci_upper = float(summary.loc["abs_effect_upper", "average"])
        p_value = float(ci.p_value)
    except Exception as exc:  # noqa: BLE001 - model-fit surface is unpredictable, already logged
        log.error("CausalImpact fit failed: %s", exc)
        return None

    return effect, ci_lower, ci_upper, p_value


def compute_estimate(
    intervention_id: str,
    series: dict[date, float],
    onset: date,
    *,
    today: date | None = None,
    min_pre_days: int = MIN_PRE_DAYS,
    min_post_days: int = MIN_POST_DAYS,
) -> EvidenceEstimate | None:
    """Orchestrates _prepare_window + _fit_causal_impact. Pure aside from
    the model fit — no Supabase access here, so it's directly unit-testable
    against a synthetic series."""
    window = _prepare_window(
        series, onset, today=today, min_pre_days=min_pre_days, min_post_days=min_post_days,
    )
    if window is None:
        return None

    fit = _fit_causal_impact(series, window)
    if fit is None:
        return None

    effect, ci_lower, ci_upper, p_value = fit
    return EvidenceEstimate(
        intervention_id=intervention_id,
        onset=onset,
        pre_days=window.pre_days,
        post_days=window.post_days,
        effect=effect,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        p_value=p_value,
    )


# ── Supabase I/O ──────────────────────────────────────────────────────────────

async def _fetch_earliest_onset(db, intervention_id: str) -> date | None:
    if not db:
        return None
    try:
        res = (
            db.table("capacity_intervention_events")
            .select("started_at")
            .eq("intervention_id", intervention_id)
            .order("started_at", desc=False)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows or not rows[0].get("started_at"):
            return None
        ts = rows[0]["started_at"]
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
        return parsed.date()
    except Exception as exc:  # noqa: BLE001 - Supabase query surface is unpredictable, already logged
        log.error("capacity_intervention_events onset lookup failed for %s: %s", intervention_id, exc)
        return None


async def _fetch_daily_series(db, start: date, end: date) -> dict[date, float]:
    """One averaged zone-score per calendar day over [start, end], built
    from checkin_type='capacity' rows only (evening reflections carry no
    capacity_state). Days with no check-in are simply absent from the
    result — never interpolated here."""
    if not db:
        return {}
    try:
        res = (
            db.table(CHECKINS_TABLE)
            .select("log_date,capacity_state")
            .eq("checkin_type", "capacity")
            .gte("log_date", start.isoformat())
            .lte("log_date", end.isoformat())
            .execute()
        )
        rows = res.data or []
    except Exception as exc:  # noqa: BLE001 - Supabase query surface is unpredictable, already logged
        log.error("capacity_checkins series fetch failed [%s..%s]: %s", start, end, exc)
        return {}

    by_day: dict[date, list[float]] = {}
    for row in rows:
        state = row.get("capacity_state")
        log_date = row.get("log_date")
        if not state or not log_date:
            continue
        score, _status = capacity_zone_from_checkin({"capacity_state": state})
        if score is None:
            continue
        d = datetime.fromisoformat(log_date).date() if isinstance(log_date, str) else log_date
        by_day.setdefault(d, []).append(float(score))

    return {d: sum(scores) / len(scores) for d, scores in by_day.items()}


async def compute_and_write(
    db,
    intervention_id: str,
    *,
    dry_run: bool = False,
    min_pre_days: int = MIN_PRE_DAYS,
    min_post_days: int = MIN_POST_DAYS,
) -> EvidenceEstimate | None:
    """Full pipeline for one intervention: onset -> series -> estimate ->
    (unless dry_run) write to capacity_interventions. Returns the estimate
    (or None — never tried yet, or not enough data yet) either way, so
    callers can report on what was/wasn't computed without a second query.
    """
    onset = await _fetch_earliest_onset(db, intervention_id)
    if onset is None:
        return None

    today = datetime.now(timezone.utc).date()
    fetch_start = onset - timedelta(days=LOOKBACK_CAP_DAYS)
    fetch_end = min(today, onset + timedelta(days=LOOKBACK_CAP_DAYS))
    series = await _fetch_daily_series(db, fetch_start, fetch_end)

    estimate = compute_estimate(
        intervention_id, series, onset, today=today,
        min_pre_days=min_pre_days, min_post_days=min_post_days,
    )
    if estimate is None:
        return None

    if not dry_run and db:
        try:
            db.table(INTERVENTIONS_TABLE).update(estimate.to_payload()).eq(
                "intervention_id", intervention_id
            ).execute()
        except Exception as exc:  # noqa: BLE001 - Supabase query surface is unpredictable, already logged
            log.error("capacity_interventions personal-effect write failed for %s: %s", intervention_id, exc)

    return estimate


async def run_all(db, *, dry_run: bool = False) -> list[EvidenceEstimate]:
    """Backfill/refresh entry point — every enabled intervention, in one
    pass. Used by both the CLI (no --intervention-id) and (once wired) a
    scheduled job. Silently skips interventions with no attempts yet or not
    enough data — that's the expected steady state for most of the
    catalogue, not an error."""
    if not db:
        return []
    try:
        rows = db.table(INTERVENTIONS_TABLE).select("intervention_id").eq("enabled", True).execute().data or []
    except Exception as exc:  # noqa: BLE001 - Supabase query surface is unpredictable, already logged
        log.error("capacity_interventions catalogue fetch failed: %s", exc)
        return []

    estimates: list[EvidenceEstimate] = []
    for row in rows:
        estimate = await compute_and_write(db, row["intervention_id"], dry_run=dry_run)
        if estimate is not None:
            estimates.append(estimate)
    log.info(
        "Personal causal-effect pass: %d/%d intervention(s) had enough data to estimate (dry_run=%s)",
        len(estimates), len(rows), dry_run,
    )
    return estimates


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_db():
    import os

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        log.warning("SUPABASE_URL/SUPABASE_KEY not set — Supabase disabled")
        return None
    from supabase import create_client
    return create_client(url, key)


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Compute and log estimates but write nothing")
    parser.add_argument("--intervention-id", help="Only this intervention, instead of the full catalogue")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = _build_db()

    async def _main():
        if args.intervention_id:
            estimate = await compute_and_write(db, args.intervention_id, dry_run=args.dry_run)
            if estimate is None:
                print(f"{args.intervention_id}: not enough data yet (or never tried)")
            else:
                print(f"{args.intervention_id}: {estimate.summary_text()}")
        else:
            estimates = await run_all(db, dry_run=args.dry_run)
            for e in estimates:
                print(f"{e.intervention_id}: {e.summary_text()}")
            print(f"\n{len(estimates)} intervention(s) estimated.")

    asyncio.run(_main())


if __name__ == "__main__":
    _cli()
