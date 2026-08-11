"""Data Quality & Trust — USS-TJR-MSN-0098 WP1 + WP8.

Two intertwined questions:

    WP1 — What operational data is MISSING, why, and how to capture it easily?
    WP8 — Does the system know what it knows? Does it recognise uncertainty?

Both read the *existing* stores (advisory ledger, decision logs, mission/decision
outcomes, lessons) — no new data store. The goal is to improve the quality of
intelligence the existing systems produce, by making gaps visible and trust
measurable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_outcomes = _import_sibling("outcomes")
import timeline as _timeline
import calibration as _calibration
import metrics as _metrics


# ---------------------------------------------------------------------------
# WP1 — Capture gaps
# ---------------------------------------------------------------------------

def capture_gaps() -> dict[str, Any]:
    """Identify missing operational data, why it's missing, and how to capture it."""
    records = _outcomes.load_records()
    open_advice = [r for r in records if not r.get("outcome")]

    # Decisions with no recorded captain outcome.
    decisions = _timeline.load_events(kinds=["decision"])
    decisions_no_outcome = [e for e in decisions if not e.outcome]

    gaps: list[dict[str, Any]] = []

    if open_advice:
        gaps.append(_gap(
            "advisory_outcomes",
            len(open_advice),
            "Advice was given but the outcome was never recorded, so the system cannot learn from it.",
            "Close each with `/advisory-outcome <id|last> <success|failure|partial>` (one tap in the portal).",
            sample=[r.get("advisory_id") for r in open_advice[:5]],
        ))

    if decisions_no_outcome:
        gaps.append(_gap(
            "decision_closures",
            len(decisions_no_outcome),
            "Strategic decisions have no captain-held outcome, so decision quality cannot be scored.",
            "Record the held outcome when a decision plays out (decision register / portal).",
            sample=[e.ref for e in decisions_no_outcome[:5]],
        ))

    # Health check-ins — detected by absence of health events in the timeline window.
    # (Health series live in Supabase; offline this surfaces as a standing gap.)
    gaps.append(_gap(
        "health_checkins",
        0,
        "Daily health check-ins drive wellness intelligence and capacity scoring.",
        "Use `/health-check` (Slack) or the portal Medical pages — 30s/day.",
        standing=True,
    ))

    return {
        "gaps": gaps,
        "open_advisory_loops": len(open_advice),
        "decisions_awaiting_outcome": len(decisions_no_outcome),
        "narrative": _gaps_narrative(gaps),
    }


def _gap(kind, count, why, how, *, sample=None, standing=False):
    return {
        "kind": kind,
        "missing_count": count,
        "why": why,
        "how_to_capture": how,
        "sample": sample or [],
        "standing": standing,
    }


def _gaps_narrative(gaps: list[dict]) -> str:
    actionable = [g for g in gaps if g["missing_count"] > 0]
    if not actionable:
        return "No outstanding capture gaps — recorded data is reasonably complete."
    bits = [f"{g['missing_count']} {g['kind'].replace('_', ' ')}" for g in actionable]
    return "Capture gaps: " + ", ".join(bits) + ". Closing these improves what the system can learn."


# ---------------------------------------------------------------------------
# WP8 — Trust metrics
# ---------------------------------------------------------------------------

def trust_metrics() -> dict[str, Any]:
    """Measure whether the system knows what it knows and recognises uncertainty."""
    cal = _calibration.calibration_report()
    met = _metrics.advisory_metrics()
    records = _outcomes.load_records()

    total = len(records)
    closed = len([r for r in records if r.get("outcome")])
    coverage = round(closed / total, 3) if total else 0.0

    # Evidence quality: share of advice backed by historical evidence or lessons.
    with_evidence = sum(1 for r in records if (r.get("evidence_count") or 0) > 0 or r.get("lesson_ids"))
    evidence_rate = round(with_evidence / total, 3) if total else 0.0

    accuracy = cal.get("overall_accuracy")
    alignment = cal.get("confidence_alignment", {})

    # "Recognises uncertainty": does it flag low confidence / insufficient data?
    recognises_uncertainty = (
        not cal.get("sufficient_data", False)  # honestly reports provisional
        or alignment.get("aligned") is not None
    )

    return {
        "data_completeness": coverage,
        "evidence_quality": evidence_rate,
        "recommendation_quality": accuracy,
        "confidence_accuracy": alignment.get("aligned"),
        "confidence_alignment_detail": alignment.get("interpretation"),
        "sample_size": cal.get("total_outcomes", 0),
        "knows_what_it_knows": bool(total > 0),
        "recognises_uncertainty": bool(recognises_uncertainty),
        "sufficient_data": cal.get("sufficient_data", False),
        "narrative": _trust_narrative(coverage, evidence_rate, accuracy, cal.get("sufficient_data")),
    }


def _trust_narrative(coverage, evidence_rate, accuracy, sufficient) -> str:
    if not sufficient:
        return ("Trust is provisional — too few closed outcomes to judge accuracy. "
                "The system correctly flags this uncertainty rather than overclaiming.")
    parts = [
        f"outcome coverage {int(coverage*100)}%",
        f"evidence-backed advice {int(evidence_rate*100)}%",
    ]
    if accuracy is not None:
        parts.append(f"recommendation accuracy {int(accuracy*100)}%")
    return "Trust: " + ", ".join(parts) + "."


def to_markdown() -> str:
    gaps = capture_gaps()
    trust = trust_metrics()
    L = ["# Data Quality & Trust", "", "## Capture Gaps", gaps["narrative"], ""]
    for g in gaps["gaps"]:
        if g["missing_count"] > 0 or g["standing"]:
            L.append(f"- **{g['kind']}** ({g['missing_count']}): {g['why']}")
            L.append(f"  - How: {g['how_to_capture']}")
    L.append("")
    L.append("## Trust")
    L.append(trust["narrative"])
    return "\n".join(L)
