"""Confidence Calibration — USS-TJR-MSN-0093 WP4.

Measures, from recorded advisory outcomes (WP3):

    * recommendation accuracy   — overall success rate
    * confidence accuracy       — does higher confidence actually succeed more?
    * officer performance       — per-officer historical accuracy
    * challenge effectiveness   — did challenged/escalated advice avoid bad calls?

Answers:
    Which officers provide the most accurate advice?
    Does confidence align with outcomes?
    Which recommendations consistently succeed?

Reuses the outcome ledger only. Advisory/measurement — no authority granted.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_outcomes = _import_sibling("outcomes")  # noqa: E402

_MIN_SAMPLES = 3  # below this, report "insufficient data" rather than noise


def _scored_events() -> list[tuple[float, dict[str, Any]]]:
    """Return (success_score, event) for events with a determinate outcome."""
    out = []
    for ev in _outcomes.load_outcomes():
        success = ev.get("success")
        if success is True:
            out.append((1.0, ev))
        elif success is False:
            out.append((0.0, ev))
        elif ev.get("outcome") == "partial":
            out.append((0.5, ev))
        # unknown → excluded
    return out


def _rate(scores: list[float]) -> float | None:
    return round(sum(scores) / len(scores), 3) if scores else None


# ---------------------------------------------------------------------------
# Officer performance
# ---------------------------------------------------------------------------

def officer_accuracy() -> dict[str, dict[str, Any]]:
    """Per-officer historical accuracy across advice they participated in."""
    by_officer: dict[str, list[float]] = {}
    for score, ev in _scored_events():
        for officer in ev.get("officers", []):
            if officer:
                by_officer.setdefault(officer, []).append(score)

    result: dict[str, dict[str, Any]] = {}
    for officer, scores in by_officer.items():
        result[officer] = {
            "samples": len(scores),
            "accuracy": _rate(scores),
            "sufficient": len(scores) >= _MIN_SAMPLES,
        }
    return result


# ---------------------------------------------------------------------------
# Confidence alignment
# ---------------------------------------------------------------------------

def confidence_alignment() -> dict[str, Any]:
    """Does stated confidence track actual success? Compares success rate by band."""
    bands: dict[str, list[float]] = {"High": [], "Medium": [], "Low": []}
    for score, ev in _scored_events():
        band = ev.get("confidence_band")
        if band in bands:
            bands[band].append(score)

    by_band = {b: {"samples": len(s), "success_rate": _rate(s)} for b, s in bands.items()}

    # Aligned if High >= Medium >= Low (where each has data).
    ordered = [by_band[b]["success_rate"] for b in ("High", "Medium", "Low")
               if by_band[b]["success_rate"] is not None]
    aligned = all(earlier >= later for earlier, later in zip(ordered, ordered[1:])) if len(ordered) >= 2 else None

    total = sum(len(s) for s in bands.values())
    return {
        "by_band": by_band,
        "aligned": aligned,
        "samples": total,
        "sufficient": total >= _MIN_SAMPLES,
        "interpretation": _alignment_text(aligned, by_band),
    }


def _alignment_text(aligned: bool | None, by_band: dict[str, Any]) -> str:
    if aligned is None:
        return "Insufficient data across confidence bands to assess alignment."
    if aligned:
        return "Confidence is well calibrated — higher-confidence advice succeeds more often."
    return ("Confidence is miscalibrated — higher-confidence advice is not outperforming "
            "lower-confidence advice. Treat stated confidence with caution.")


# ---------------------------------------------------------------------------
# Challenge effectiveness
# ---------------------------------------------------------------------------

def challenge_effectiveness() -> dict[str, Any]:
    """Did challenged/escalated advice avoid adverse outcomes?

    'Prevented adverse decisions' = advice that flagged escalation_required AND
    was NOT ultimately recorded as a failure (the challenge did its job, or the
    Captain heeded the escalation).
    """
    escalated = [(s, ev) for s, ev in _scored_events() if ev.get("escalation_required")]
    reviewed = [(s, ev) for s, ev in _scored_events() if ev.get("reviewer")]

    prevented = sum(1 for s, _ in escalated if s >= 0.5)
    escalated_failures = sum(1 for s, _ in escalated if s < 0.5)

    return {
        "escalations": len(escalated),
        "prevented_adverse": prevented,
        "escalated_failures": escalated_failures,
        "reviewed_count": len(reviewed),
        "reviewed_success_rate": _rate([s for s, _ in reviewed]),
        "note": (
            f"Challenge reviews flagged {len(escalated)} decision(s) for escalation; "
            f"{prevented} avoided an adverse outcome."
        ),
    }


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------

def calibration_report() -> dict[str, Any]:
    scored = _scored_events()
    overall = _rate([s for s, _ in scored])
    officers = officer_accuracy()
    ranked = sorted(
        [(o, d["accuracy"], d["samples"]) for o, d in officers.items() if d["accuracy"] is not None],
        key=lambda x: (x[1], x[2]), reverse=True,
    )
    return {
        "total_outcomes": len(scored),
        "overall_accuracy": overall,
        "officer_accuracy": officers,
        "officer_ranking": [{"officer": o, "accuracy": a, "samples": n} for o, a, n in ranked],
        "confidence_alignment": confidence_alignment(),
        "challenge_effectiveness": challenge_effectiveness(),
        "sufficient_data": len(scored) >= _MIN_SAMPLES,
    }


def to_markdown(report: dict[str, Any] | None = None) -> str:
    report = report or calibration_report()
    L = ["# Advisory Confidence Calibration", ""]
    if not report["sufficient_data"]:
        L.append(f"_Only {report['total_outcomes']} recorded outcome(s) — results are provisional "
                 f"until more advice is closed out with `/advisory-outcome`._")
        L.append("")
    acc = report["overall_accuracy"]
    L.append(f"**Overall recommendation accuracy:** "
             f"{int(acc * 100) if acc is not None else '—'}% "
             f"(n={report['total_outcomes']})")
    L.append("")
    L.append("## Officer Accuracy")
    if report["officer_ranking"]:
        for r in report["officer_ranking"]:
            L.append(f"- **{r['officer']}**: {int(r['accuracy'] * 100)}% (n={r['samples']})")
    else:
        L.append("- No officer outcome data yet.")
    L.append("")
    ca = report["confidence_alignment"]
    L.append("## Confidence Alignment")
    L.append(ca["interpretation"])
    for band in ("High", "Medium", "Low"):
        d = ca["by_band"][band]
        if d["success_rate"] is not None:
            L.append(f"- {band}: {int(d['success_rate'] * 100)}% success (n={d['samples']})")
    L.append("")
    ce = report["challenge_effectiveness"]
    L.append("## Challenge Effectiveness")
    L.append(f"- {ce['note']}")
    L.append(f"- Reviewed decisions: {ce['reviewed_count']}")
    return "\n".join(L)
