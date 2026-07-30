"""
Decision Effectiveness Intelligence — WP1
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Reads all decision JSON logs and produces structured effectiveness reporting:
- Success rate, quality trends, mode distribution
- Best/worst performing decision categories
- Integration with G-008 learning architecture signal

No database writes. Pure read from logs/decisions/*.json.

Public API:
    compute_decision_effectiveness(decisions_dir) -> dict
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DECISIONS_DIR = _REPO_ROOT / "logs" / "decisions"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_decision_logs(decisions_dir: Path | None = None) -> list[dict[str, Any]]:
    d = decisions_dir or _DECISIONS_DIR
    records = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data.setdefault("_source_file", f.name)
            records.append(data)
        except Exception:
            pass
    return records


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_HELD_SCORE: dict[str | None, float | None] = {
    "success": 1.0,
    "failure": 0.0,
    "partial": 0.5,
    None: None,
}

_MODE_LABELS = {
    "strategic": "Strategic",
    "research-to-implementation": "Research→Implementation",
    "governance": "Governance",
    "operational": "Operational",
}


def _normalise_held(raw: Any) -> str | None:
    if raw is None:
        return None
    v = str(raw).lower().strip()
    if v in ("success", "true", "1", "yes"):
        return "success"
    if v in ("failure", "false", "0", "no"):
        return "failure"
    if v in ("partial",):
        return "partial"
    return None


def _outcome_score(record: dict) -> float | None:
    held = _normalise_held(record.get("captain_decision_held"))
    explicit = record.get("outcome_quality_score")
    if explicit is not None:
        try:
            return max(1.0, min(5.0, float(explicit))) / 5.0  # normalise to 0–1
        except (TypeError, ValueError):
            pass
    return _HELD_SCORE.get(held)


def _has_meaningful_review(record: dict) -> bool:
    review = record.get("captain_outcome_review") or ""
    return isinstance(review, str) and len(review.strip()) > 10 and review.strip().upper() != "DEFERRED"


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def compute_decision_effectiveness(
    decisions_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Compute decision effectiveness metrics from JSON decision logs.

    Returns:
        Dict with summary, mode_breakdown, trend, best/worst categories,
        quality_score distribution, and G-008 learning signal.
    """
    records = _load_decision_logs(decisions_dir)
    total = len(records)

    if total == 0:
        return {
            "status": "no_data",
            "total_decisions": 0,
            "summary": "No decision logs found.",
        }

    # ── Basic counts ────────────────────────────────────────────────────────
    accepted = sum(1 for r in records if str(r.get("status", "")).lower() == "accepted")
    rejected = sum(1 for r in records if str(r.get("status", "")).lower() == "rejected")
    deferred = sum(1 for r in records if str(r.get("captain_outcome_review", "")).upper() == "DEFERRED")
    pending  = total - accepted - rejected

    with_review = sum(1 for r in records if _has_meaningful_review(r))
    with_held   = sum(1 for r in records if _normalise_held(r.get("captain_decision_held")) is not None)
    success_n   = sum(1 for r in records if _normalise_held(r.get("captain_decision_held")) == "success")
    failure_n   = sum(1 for r in records if _normalise_held(r.get("captain_decision_held")) == "failure")
    with_mission = sum(1 for r in records if r.get("mission_id"))
    with_lesson  = sum(1 for r in records if r.get("lesson_id") or r.get("lesson_ids_generated"))

    # ── Quality scores ──────────────────────────────────────────────────────
    scored = [(r, _outcome_score(r)) for r in records]
    rated  = [(r, s) for r, s in scored if s is not None]
    scores = [s for _, s in rated]

    quality_avg  = round(mean(scores), 3) if scores else None
    quality_stdev = round(stdev(scores), 3) if len(scores) >= 2 else None

    # ── Confidence distribution ─────────────────────────────────────────────
    confidences = [float(r["research_confidence"]) for r in records
                   if r.get("research_confidence") is not None]
    conf_avg = round(mean(confidences), 2) if confidences else None

    # ── Mode breakdown ──────────────────────────────────────────────────────
    mode_counts: Counter = Counter()
    mode_scores: dict[str, list[float]] = defaultdict(list)
    for r, s in scored:
        mode = str(r.get("decision_mode", "unknown")).lower()
        mode_counts[mode] += 1
        if s is not None:
            mode_scores[mode].append(s)

    mode_breakdown: list[dict] = []
    for mode, count in mode_counts.most_common():
        s_list = mode_scores.get(mode, [])
        mode_breakdown.append({
            "mode": _MODE_LABELS.get(mode, mode),
            "count": count,
            "pct": round(count / total * 100, 1),
            "avg_quality": round(mean(s_list), 3) if s_list else None,
            "rated": len(s_list),
        })

    # ── Best / worst performing modes (by avg quality, min 2 rated) ─────────
    ranked_modes = sorted(
        [(m, s_list) for m, s_list in mode_scores.items() if len(s_list) >= 2],
        key=lambda x: mean(x[1]),
        reverse=True,
    )
    best_mode  = _MODE_LABELS.get(ranked_modes[0][0], ranked_modes[0][0]) if ranked_modes else None
    worst_mode = _MODE_LABELS.get(ranked_modes[-1][0], ranked_modes[-1][0]) if len(ranked_modes) >= 2 else None

    # ── Temporal trend (chronological order) ───────────────────────────────
    chronological = sorted(rated, key=lambda x: x[0].get("timestamp", ""))
    trend = _compute_trend([s for _, s in chronological])

    # ── Outcome category distribution ───────────────────────────────────────
    outcome_cats = Counter(
        str(r.get("outcome_category", "")).lower()
        for r in records
        if r.get("outcome_category")
    )

    # ── G-008 signal ────────────────────────────────────────────────────────
    g008_ready = with_held >= 10
    g008_status = (
        f"ACTIVE ({with_held} decisions rated)" if g008_ready
        else f"PENDING — {with_held}/10 decisions rated ({10 - with_held} more needed)"
    )

    # ── Lesson coverage ─────────────────────────────────────────────────────
    lesson_coverage_pct = round(with_lesson / total * 100, 1) if total else 0

    summary_lines = [
        f"Total decisions: {total}",
        f"Accepted: {accepted} | Rejected: {rejected} | Deferred: {deferred}",
        f"Outcome rated: {with_held}/{total} ({round(with_held/total*100,1)}%)",
        f"Success rate: {round(success_n/with_held*100,1)}% ({success_n}/{with_held})" if with_held else "Success rate: insufficient data",
        f"Average quality score: {round(quality_avg*5,2):.1f}/5" if quality_avg is not None else "Quality score: insufficient data",
        f"Average research confidence: {conf_avg}" if conf_avg is not None else "Research confidence: N/A",
        f"G-008 learning loop: {g008_status}",
    ]

    return {
        "status": "ok",
        "total_decisions": total,
        "accepted": accepted,
        "rejected": rejected,
        "deferred": deferred,
        "with_outcome_review": with_review,
        "with_outcome_held": with_held,
        "success_count": success_n,
        "failure_count": failure_n,
        "success_rate": round(success_n / with_held, 3) if with_held else None,
        "with_mission_link": with_mission,
        "with_lesson_link": with_lesson,
        "lesson_coverage_pct": lesson_coverage_pct,
        "quality_avg": quality_avg,
        "quality_avg_5pt": round(quality_avg * 5, 2) if quality_avg is not None else None,
        "quality_stdev": quality_stdev,
        "quality_trend": trend,
        "research_confidence_avg": conf_avg,
        "mode_breakdown": mode_breakdown,
        "best_performing_mode": best_mode,
        "worst_performing_mode": worst_mode,
        "outcome_categories": dict(outcome_cats),
        "g008_learning_signal": {
            "ready": g008_ready,
            "rated_decisions": with_held,
            "required": 10,
            "status": g008_status,
        },
        "summary": " | ".join(summary_lines[:3]),
        "findings": summary_lines,
    }


def _compute_trend(scores: list[float]) -> str:
    if len(scores) < 4:
        return "insufficient_data"
    first_half = mean(scores[: len(scores) // 2])
    second_half = mean(scores[len(scores) // 2 :])
    delta = second_half - first_half
    if delta > 0.05:
        return "improving"
    if delta < -0.05:
        return "declining"
    return "stable"
