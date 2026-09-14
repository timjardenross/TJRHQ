"""
HQ Evolution calibration scoring — Fatebook-style: does this subsystem's
own predicted fit/relevance for a candidate actually track what happened
once the outcome is known?

Grounded in what already exists, not a new parallel outcome-tracking
mechanism. Three separate "outcome" systems already live in this repo
(core/knowledge/outcome_capture.py, platform-runtime/lib/
outcome_capture_service.py, and this directory's own outcome_contract.py/
outcome_evaluation.py) — none of them compute a calibration score. The one
existing precedent for exactly this kind of confidence-bucket accuracy
report is core/advisory/calibration.py's confidence_alignment(), for a
different subsystem (officer advisory, not HQ Evolution). This module
follows that same band-bucketing pattern rather than inventing a fourth
mechanism, applied to the fields HQ Evolution already has sitting unused
for this purpose on every Opportunity record:

  - `fit` ("weak"/"moderate"/"strong") and `relevance_score` (a continuous
    0-1 score from RelevanceGate.score_candidate(), relevance.py) — the
    PREDICTIONS, set at discovery/enrichment time, before any outcome
    exists.
  - `outcome.outcome_result` ("improved"/"no_material_change"/"regressed"/
    "inconclusive"/"not_yet_ready", opportunity_store.OUTCOME_RESULTS) —
    the resolved OUTCOME, set later by outcome_evaluation.evaluate_outcome().

No new Supabase table, no new JSONL file: both fields already live on the
same append-only opportunities.jsonl record (opportunity_store.py) — this
module only ever reads OpportunityStore.all_current(), never writes.

Interpretation choice worth being explicit about: `outcome_result` measures
whether the opportunity's own success/regression signal moved favourably
once implemented — not, strictly, "was choosing to pursue this a good
call." For a `rejected`/`watching` opportunity there is no outcome_result
at all (nothing was ever implemented to measure), so those never enter
this report — consistent with core/advisory/calibration.py's own
"unknown -> excluded" handling of indeterminate outcomes. This is the best
ground truth actually available in this codebase for "did the confidence
about this candidate pan out"; treat it as that, not as a verdict on the
rejection/approval decision itself.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from opportunity_store import OpportunityStore

DEFAULT_DATA_ROOT = Path("/opt/starship-endeavour/data/self-improvement")

_MIN_SAMPLES = 3  # below this, report "insufficient data" rather than noise

# Same three-band vocabulary opportunity_store.Opportunity.fit already uses
# (and relevance.py's RelevanceGate._FIT_SCORE already numerically ranks
# strong > moderate > weak) — reused here, not reinvented.
_FIT_BANDS = ("strong", "moderate", "weak")

# outcome_result -> a [0, 1] success score. "not_yet_ready" is deliberately
# excluded (open observation window — not a resolved verdict; matches
# core/advisory/calibration.py's own "unknown -> excluded" handling).
_OUTCOME_SCORE = {
    "improved": 1.0,
    "no_material_change": 0.5,
    "inconclusive": 0.5,
    "regressed": 0.0,
}


def _scored_opportunities(store: OpportunityStore) -> list[tuple[float, dict[str, Any]]]:
    """(success_score, opportunity) for every opportunity with a resolved
    outcome_result — i.e. one that was actually implemented and evaluated,
    not merely discovered/investigating/watching/rejected."""
    out = []
    for opp in store.all_current():
        result = (opp.get("outcome") or {}).get("outcome_result")
        if result in _OUTCOME_SCORE:
            out.append((_OUTCOME_SCORE[result], opp))
    return out


def _rate(scores: list[float]) -> float | None:
    return round(sum(scores) / len(scores), 3) if scores else None


# ---------------------------------------------------------------------------
# Fit-band alignment (mirrors core/advisory/calibration.py's
# confidence_alignment() exactly, just over HQ Evolution's own vocabulary)
# ---------------------------------------------------------------------------

def fit_alignment(store: OpportunityStore) -> dict[str, Any]:
    """Does the predicted `fit` band track actual outcome once resolved?"""
    bands: dict[str, list[float]] = {b: [] for b in _FIT_BANDS}
    for score, opp in _scored_opportunities(store):
        fit = opp.get("fit")
        if fit in bands:
            bands[fit].append(score)

    by_band = {b: {"samples": len(s), "success_rate": _rate(s)} for b, s in bands.items()}

    # Aligned if strong >= moderate >= weak (where each has data) — same
    # pairwise-ordering check core/advisory/calibration.py uses.
    ordered = [by_band[b]["success_rate"] for b in _FIT_BANDS if by_band[b]["success_rate"] is not None]
    aligned = all(earlier >= later for earlier, later in itertools.pairwise(ordered)) if len(ordered) >= 2 else None

    total = sum(len(s) for s in bands.values())
    return {
        "by_band": by_band,
        "aligned": aligned,
        "samples": total,
        "sufficient": total >= _MIN_SAMPLES,
        "interpretation": _fit_alignment_text(aligned),
    }


def _fit_alignment_text(aligned: bool | None) -> str:
    if aligned is None:
        return "Insufficient data across fit bands to assess calibration."
    if aligned:
        return "Fit predictions are well calibrated — 'strong'-fit candidates succeed more often than 'weak'-fit ones."
    return ("Fit predictions are miscalibrated — 'strong'-fit candidates are not outperforming "
            "'weak'-fit ones. Treat the fit field with caution.")


# ---------------------------------------------------------------------------
# Continuous relevance_score calibration (Brier score + bucketed
# predicted-vs-actual, the standard Fatebook/forecasting metric) — a
# finer-grained companion to the three discrete fit bands above. Computed
# from scratch: grepped this repo for "brier"/"calibration curve" first —
# zero hits before this function, nothing to reuse.
# ---------------------------------------------------------------------------

def relevance_score_calibration(store: OpportunityStore, n_buckets: int = 3) -> dict[str, Any]:
    """Brier score (mean squared error between the predicted relevance_score
    and the realised 0/0.5/1 outcome) overall, plus a predicted-vs-actual
    breakdown bucketed into `n_buckets` equal-width bins of relevance_score."""
    scored = [
        (opp.get("relevance_score"), score)
        for score, opp in _scored_opportunities(store)
        if isinstance(opp.get("relevance_score"), (int, float))
    ]
    if not scored:
        return {"samples": 0, "sufficient": False, "brier_score": None, "buckets": []}

    brier_score = round(sum((pred - actual) ** 2 for pred, actual in scored) / len(scored), 4)

    bucket_width = 1.0 / n_buckets
    buckets: list[dict[str, Any]] = []
    for i in range(n_buckets):
        lo, hi = i * bucket_width, (i + 1) * bucket_width
        is_last = i == n_buckets - 1
        in_bucket = [(pred, actual) for pred, actual in scored if lo <= pred < hi or (is_last and pred == hi)]
        if not in_bucket:
            buckets.append({"range": f"{lo:.2f}-{hi:.2f}", "samples": 0, "predicted_avg": None, "actual_rate": None})
            continue
        buckets.append({
            "range": f"{lo:.2f}-{hi:.2f}",
            "samples": len(in_bucket),
            "predicted_avg": round(sum(p for p, _ in in_bucket) / len(in_bucket), 3),
            "actual_rate": round(sum(a for _, a in in_bucket) / len(in_bucket), 3),
        })

    return {
        "samples": len(scored),
        "sufficient": len(scored) >= _MIN_SAMPLES,
        "brier_score": brier_score,
        "buckets": buckets,
    }


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------

def calibration_report(store: OpportunityStore) -> dict[str, Any]:
    scored = _scored_opportunities(store)
    return {
        "total_resolved_opportunities": len(scored),
        "overall_success_rate": _rate([s for s, _ in scored]),
        "fit_alignment": fit_alignment(store),
        "relevance_score_calibration": relevance_score_calibration(store),
        "sufficient_data": len(scored) >= _MIN_SAMPLES,
    }


def to_markdown(report: dict[str, Any]) -> str:
    L = ["# HQ Evolution Calibration", ""]
    if not report["sufficient_data"]:
        L.append(f"_Only {report['total_resolved_opportunities']} resolved opportunit"
                 f"{'y' if report['total_resolved_opportunities'] == 1 else 'ies'} — results are "
                 f"provisional until more candidates reach a resolved outcome._")
        L.append("")
    rate = report["overall_success_rate"]
    L.append(f"**Overall success rate:** {int(rate * 100) if rate is not None else '—'}% "
             f"(n={report['total_resolved_opportunities']})")
    L.append("")

    fa = report["fit_alignment"]
    L.append("## Fit-Band Alignment")
    L.append(fa["interpretation"])
    for band in _FIT_BANDS:
        d = fa["by_band"][band]
        if d["success_rate"] is not None:
            L.append(f"- {band}: {int(d['success_rate'] * 100)}% success (n={d['samples']})")
    L.append("")

    rc = report["relevance_score_calibration"]
    L.append("## Relevance-Score Calibration")
    if rc["brier_score"] is not None:
        L.append(f"- Brier score: {rc['brier_score']} (0 = perfect, 0.25 = no better than always guessing 0.5)")
        for b in rc["buckets"]:
            if b["samples"]:
                L.append(f"- {b['range']}: predicted avg {b['predicted_avg']}, actual success rate {b['actual_rate']} (n={b['samples']})")
    else:
        L.append("- No relevance_score data on resolved opportunities yet.")

    return "\n".join(L)


def _main() -> int:
    parser = argparse.ArgumentParser(description="HQ Evolution calibration report")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--json", action="store_true", help="Print the raw report dict instead of markdown")
    args = parser.parse_args()

    store = OpportunityStore(args.data_root)
    report = calibration_report(store)
    if args.json:
        import json
        print(json.dumps(report, indent=2))
    else:
        print(to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
