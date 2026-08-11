"""Advisory Metrics & Intelligence — USS-TJR-MSN-0093 WP7.

Operational measures that make the advisory capability measurable:

    advisory requests · challenge requests · recommendation success rates ·
    confidence distribution · advisor utilisation · lesson reuse · evidence usage

Dashboard concepts: top-performing advisors, most valuable lessons, recent
advice, confidence trends, historical effectiveness.

Reuses the advisory snapshots (logs/advisory/*.json), the outcome ledger, and
the calibration module. Pure measurement — no authority.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_outcomes = _import_sibling("outcomes")  # noqa: E402
import calibration as _calibration  # noqa: E402
_learning = _import_sibling("learning")  # noqa: E402


def advisory_metrics() -> dict[str, Any]:
    records = _outcomes.load_records()
    outcome_events = _outcomes.load_outcomes()

    total = len(records)
    by_action = Counter(r.get("action", "advice") for r in records)
    challenges = by_action.get("challenge", 0)
    with_reviewer = sum(1 for r in records if r.get("reviewer"))
    escalations = sum(1 for r in records if r.get("escalation_required"))

    # Confidence distribution over advice given.
    conf_dist = Counter(r.get("confidence_band") for r in records if r.get("confidence_band"))

    # Advisor utilisation — how often each officer participated.
    advisor_util = Counter()
    for r in records:
        for o in r.get("officers", []):
            if o.get("officer"):
                advisor_util[o["officer"]] += 1

    # Lesson reuse — how often each lesson was surfaced in advice.
    lesson_use = Counter()
    for r in records:
        for lid in r.get("lesson_ids", []):
            if lid:
                lesson_use[lid] += 1

    # Evidence usage.
    advice_with_evidence = sum(1 for r in records if (r.get("evidence_count") or 0) > 0)
    advice_with_decisions = sum(1 for r in records if r.get("related_decision_ids"))

    # Outcome coverage & success.
    closed = [e for e in outcome_events if e.get("success") is not None or e.get("outcome") == "partial"]
    determinate = [e for e in outcome_events if e.get("success") is not None]
    success_rate = (
        round(sum(1 for e in determinate if e.get("success")) / len(determinate), 3)
        if determinate else None
    )

    cal = _calibration.calibration_report()
    reinforcement = _learning.lesson_reinforcement()

    return {
        "totals": {
            "advisory_requests": total,
            "challenge_requests": challenges,
            "reviewed": with_reviewer,
            "escalations": escalations,
            "outcomes_recorded": len(outcome_events),
            "outcome_coverage": round(len(closed) / total, 3) if total else 0.0,
        },
        "recommendation_success_rate": success_rate,
        "confidence_distribution": dict(conf_dist),
        "advisor_utilisation": dict(advisor_util),
        "lesson_reuse": dict(lesson_use.most_common(10)),
        "evidence_usage": {
            "advice_with_evidence": advice_with_evidence,
            "advice_with_related_decisions": advice_with_decisions,
            "evidence_rate": round(advice_with_evidence / total, 3) if total else 0.0,
        },
        "dashboard": {
            "top_advisors": cal["officer_ranking"][:5],
            "most_valuable_lessons": _most_valuable_lessons(lesson_use, reinforcement),
            "recent_advice": [
                {
                    "advisory_id": r.get("advisory_id"),
                    "question": (r.get("question") or "")[:100],
                    "confidence_band": r.get("confidence_band"),
                    "outcome": r.get("outcome"),
                    "recorded_at": r.get("recorded_at"),
                }
                for r in records[:8]
            ],
            "confidence_trend": _confidence_trend(records),
            "historical_effectiveness": cal["overall_accuracy"],
        },
        "sufficient_data": total >= 3,
    }


def _most_valuable_lessons(lesson_use: Counter, reinforcement: dict[str, dict]) -> list[dict[str, Any]]:
    """Lessons that are both reused and correlate with good outcomes."""
    out = []
    for lid, uses in lesson_use.most_common(10):
        reinf = reinforcement.get(lid, {})
        out.append({
            "lesson_id": lid,
            "uses": uses,
            "success_rate": reinf.get("success_rate"),
            "signal": reinf.get("signal", "neutral"),
        })
    # Prioritise reinforced lessons, then by usage.
    out.sort(key=lambda x: (x["signal"] == "reinforce", x["uses"]), reverse=True)
    return out[:5]


def _confidence_trend(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chronological confidence values (oldest→newest) for a sparkline."""
    ordered = sorted(records, key=lambda r: r.get("recorded_at", ""))
    trend = []
    for r in ordered[-20:]:
        val = r.get("confidence_value")
        if val is not None:
            trend.append({"at": r.get("recorded_at"), "confidence": val, "outcome": r.get("outcome")})
    return trend


def to_markdown(metrics: dict[str, Any] | None = None) -> str:
    m = metrics or advisory_metrics()
    t = m["totals"]
    L = ["# Advisory Metrics", ""]
    if not m["sufficient_data"]:
        L.append("_Provisional — fewer than 3 advisory requests recorded so far._")
        L.append("")
    L.append(f"- Advisory requests: **{t['advisory_requests']}**")
    L.append(f"- Challenge requests: **{t['challenge_requests']}**")
    L.append(f"- Outcomes recorded: **{t['outcomes_recorded']}** "
             f"(coverage {int(t['outcome_coverage'] * 100)}%)")
    sr = m["recommendation_success_rate"]
    L.append(f"- Recommendation success rate: **{int(sr * 100) if sr is not None else '—'}%**")
    L.append("")
    L.append("## Confidence Distribution")
    for band, n in (m["confidence_distribution"] or {}).items():
        L.append(f"- {band}: {n}")
    L.append("")
    L.append("## Advisor Utilisation")
    for officer, n in sorted(m["advisor_utilisation"].items(), key=lambda x: x[1], reverse=True):
        L.append(f"- {officer}: {n}")
    L.append("")
    L.append("## Top Advisors (by accuracy)")
    if m["dashboard"]["top_advisors"]:
        for r in m["dashboard"]["top_advisors"]:
            L.append(f"- {r['officer']}: {int(r['accuracy'] * 100)}% (n={r['samples']})")
    else:
        L.append("- No outcome data yet.")
    L.append("")
    L.append("## Most Valuable Lessons")
    if m["dashboard"]["most_valuable_lessons"]:
        for l in m["dashboard"]["most_valuable_lessons"]:
            sr = l["success_rate"]
            srt = f", {int(sr * 100)}% success" if sr is not None else ""
            L.append(f"- {l['lesson_id']} (used {l['uses']}×{srt}) — {l['signal']}")
    else:
        L.append("- No lessons surfaced yet.")
    return "\n".join(L)
