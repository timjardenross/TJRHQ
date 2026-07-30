"""Closed-Loop Learning — USS-TJR-MSN-0093 WP5.

Turns recorded advisory outcomes (WP3) into a *learning signal* that influences
future advice, so the platform answers:

    What worked? What failed? What should be repeated? What should be avoided?

It does NOT grant authority or change recommendations autonomously — it adjusts
the *confidence* and *evidence* attached to advice, and surfaces reinforced /
cautionary lessons. The Captain still decides.

Reuses: outcomes.load_outcomes() (the ledger) and the same keyword-overlap
matching used elsewhere in the advisory runtime.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import outcomes as _outcomes  # noqa: E402

_MIN_SIMILAR_FOR_SIGNAL = 2
_STOP_WORDS = {
    "the", "a", "an", "to", "for", "and", "or", "of", "in", "is", "we", "our",
    "this", "that", "should", "could", "would", "with", "as", "be", "by", "on",
    "at", "it", "do", "does", "how", "what", "why", "when", "which", "over",
    "vs", "than", "new", "use", "build", "make",
}


def _keywords(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()) - _STOP_WORDS


def _success_score(outcome_event: dict[str, Any]) -> float:
    """Map an outcome to 0..1 (success=1, partial=0.5, failure=0, unknown skipped)."""
    success = outcome_event.get("success")
    if success is True:
        return 1.0
    if success is False:
        return 0.0
    # partial → 0.5; unknown → treated as neutral (caller filters unknown out)
    return 0.5


# ---------------------------------------------------------------------------
# Historical signal for a question
# ---------------------------------------------------------------------------

def historical_signal(question: str) -> dict[str, Any]:
    """Return a learning signal for ``question`` derived from past outcomes.

    {
      "matched": int,            # similar past advisory outcomes
      "success_rate": float|None,# 0..1 over matched (excl. unknown)
      "confidence_delta": float, # additive nudge for confidence (−0.1..+0.1)
      "reinforced_lessons": [ids],
      "avoid_lessons": [ids],
      "note": str,
    }
    """
    query = _keywords(question)
    empty = {
        "matched": 0, "success_rate": None, "confidence_delta": 0.0,
        "reinforced_lessons": [], "avoid_lessons": [], "note": "",
    }
    if not query:
        return empty

    events = _outcomes.load_outcomes()
    scored: list[tuple[float, dict[str, Any]]] = []
    for ev in events:
        if ev.get("success") is None and ev.get("outcome") == "unknown":
            continue
        overlap = len(query & _keywords(ev.get("question", "")))
        if overlap >= 1:
            scored.append((_success_score(ev), ev))

    if len(scored) < _MIN_SIMILAR_FOR_SIGNAL:
        return {**empty, "matched": len(scored),
                "note": "Insufficient prior outcomes on similar questions for a learning signal."}

    success_rate = round(sum(s for s, _ in scored) / len(scored), 3)

    # Confidence nudge: strong track record raises confidence, poor lowers it.
    if success_rate >= 0.75:
        delta = 0.08
    elif success_rate >= 0.6:
        delta = 0.04
    elif success_rate < 0.4:
        delta = -0.08
    else:
        delta = 0.0

    reinforced: list[str] = []
    avoid: list[str] = []
    for score, ev in scored:
        for lid in ev.get("lesson_ids", []):
            if not lid:
                continue
            if score >= 0.75 and lid not in reinforced:
                reinforced.append(lid)
            elif score <= 0.25 and lid not in avoid:
                avoid.append(lid)

    note = (
        f"{len(scored)} similar prior decision(s) succeeded {int(success_rate * 100)}% "
        "of the time — confidence adjusted accordingly."
    )
    return {
        "matched": len(scored),
        "success_rate": success_rate,
        "confidence_delta": delta,
        "reinforced_lessons": reinforced[:5],
        "avoid_lessons": avoid[:5],
        "note": note,
    }


# ---------------------------------------------------------------------------
# Lesson reinforcement (which lessons correlate with good outcomes)
# ---------------------------------------------------------------------------

def lesson_reinforcement() -> dict[str, dict[str, Any]]:
    """Aggregate outcome performance per lesson that has appeared in advice.

    Returns {lesson_id: {"appearances": n, "success_rate": float, "signal": str}}.
    signal ∈ {"reinforce", "neutral", "caution"}.
    """
    events = _outcomes.load_outcomes()
    by_lesson: dict[str, list[float]] = {}
    for ev in events:
        if ev.get("success") is None and ev.get("outcome") == "unknown":
            continue
        score = _success_score(ev)
        for lid in ev.get("lesson_ids", []):
            if lid:
                by_lesson.setdefault(lid, []).append(score)

    result: dict[str, dict[str, Any]] = {}
    for lid, scores in by_lesson.items():
        rate = round(sum(scores) / len(scores), 3)
        signal = "reinforce" if rate >= 0.7 else "caution" if rate < 0.4 else "neutral"
        result[lid] = {"appearances": len(scores), "success_rate": rate, "signal": signal}
    return result
