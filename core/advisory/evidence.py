"""Historical Evidence & Confidence adapter — USS-TJR-MSN-0092 WP3.

REUSE BEFORE REBUILD: the historical-evidence engine already exists in
``core/coordination/intelligence_store.py`` (get_intelligence_evidence,
historical outcome scoring, confidence_adjustment). MSN-0091 reported
``_gather_evidence`` as a null stub; that was stale — the store is wired into
the mission recommendation engine. This adapter does NOT re-implement it.

What this module adds (the genuine activation gap):
    1. Exposes the existing IntelligenceEvidence to the *specialist advisory
       runtime* (which previously had no evidence at all).
    2. Maps it onto the standard schema (EvidenceItem + ConfidenceLevel).
    3. Adds historical *decision* recall by reading the existing
       ``logs/decisions/*.json`` records — answering "what did we decide
       before, and how did it turn out?" which the store does not cover.

All reads are file-based and safe offline.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from schema import ConfidenceLevel, EvidenceItem, RelatedDecision

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DECISIONS_DIR = _REPO_ROOT / "logs" / "decisions"

# Make the existing intelligence store importable (flat-import house style).
_COORD = _REPO_ROOT / "core" / "coordination"
if str(_COORD) not in sys.path:
    sys.path.insert(0, str(_COORD))

_STOP_WORDS = {
    "the", "a", "an", "to", "for", "and", "or", "of", "in", "is", "we", "our",
    "this", "that", "should", "could", "would", "with", "as", "be", "by", "on",
    "at", "it", "do", "does", "how", "what", "why", "when", "which", "over",
    "vs", "than", "new", "use", "build", "make",
}


def _keywords(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()) - _STOP_WORDS


# ---------------------------------------------------------------------------
# Existing intelligence store (reused, not rebuilt)
# ---------------------------------------------------------------------------

def _load_store():
    """Return the intelligence_store module, or None if unavailable."""
    try:
        import intelligence_store  # noqa: PLC0415  (flat sibling import)
        return intelligence_store
    except Exception:  # noqa: BLE001
        return None


def gather_evidence(mission_type: str, objective: str) -> tuple[list[EvidenceItem], Any]:
    """Reuse intelligence_store; return (evidence_items, raw_evidence|None).

    The raw IntelligenceEvidence is returned alongside so callers can read its
    confidence_adjustment without re-querying.
    """
    store = _load_store()
    if store is None:
        return [], None

    try:
        ev = store.get_intelligence_evidence(mission_type or "General", objective or "")
    except Exception:  # noqa: BLE001
        return [], None

    items: list[EvidenceItem] = []

    if ev.historical_outcome_score is not None:
        direction = (
            "strong" if ev.historical_outcome_score >= 0.7
            else "mixed" if ev.historical_outcome_score >= 0.5
            else "poor"
        )
        items.append(EvidenceItem(
            kind="historical_outcome",
            reference=f"{mission_type or 'mission'} track record",
            detail=(
                f"{direction} historical performance across "
                f"{ev.outcome_sample_size} prior closure(s)"
            ),
            outcome_score=ev.historical_outcome_score,
        ))

    for sm in ev.similar_closed_missions:
        items.append(EvidenceItem(
            kind="similar_mission",
            reference=sm.mission_id,
            detail=f"{sm.title} ({sm.mission_type})".strip(" ()"),
            outcome_score=sm.outcome_score,
        ))

    return items, ev


# ---------------------------------------------------------------------------
# Historical decision recall (new — reads existing decision logs)
# ---------------------------------------------------------------------------

def gather_related_decisions(question: str, limit: int = 3) -> list[RelatedDecision]:
    """Return prior decisions related to ``question`` from logs/decisions/*.json.

    Answers "what did we decide before?" by keyword-matching the stored
    decision questions. Outcome (success/failure/partial) is surfaced where the
    Captain has reviewed it.
    """
    if not _DECISIONS_DIR.exists():
        return []

    query = _keywords(question)
    if not query:
        return []

    scored: list[tuple[int, RelatedDecision]] = []
    for path in _DECISIONS_DIR.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        rec_q = str(rec.get("question") or "")
        overlap = len(query & _keywords(rec_q))
        if overlap < 1:
            continue

        outcome = _normalise_outcome(rec.get("captain_decision_held"))
        action = _clean(rec.get("recommended_action")) or _clean(rec.get("final_recommendation"))
        scored.append((
            overlap,
            RelatedDecision(
                decision_id=str(rec.get("decision_id") or path.stem),
                question=rec_q[:160],
                recommended_action=(action or "")[:200],
                outcome=outcome,
                date=str(rec.get("timestamp") or "")[:10],
            ),
        ))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:limit]]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("none", "null", ""):
        return ""
    return text


def _normalise_outcome(value: Any) -> str:
    text = _clean(value).lower()
    if not text:
        return ""
    if "success" in text:
        return "success"
    if "fail" in text:
        return "failure"
    if "partial" in text:
        return "partial"
    return text[:20]


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def score_confidence(
    base: float,
    raw_evidence: Any,
    officer_confidences: Optional[list[int]] = None,
) -> ConfidenceLevel:
    """Derive a ConfidenceLevel from a base score, evidence and officer agreement.

    Reuses the intelligence_store's confidence_adjustment (already validated in
    the recommendation engine) and folds in officer-confidence signal so the
    advisory runtime gets the same evidence-based confidence behaviour.
    """
    value = base
    basis_parts: list[str] = []

    if raw_evidence is not None:
        adj = getattr(raw_evidence, "confidence_adjustment", 0.0) or 0.0
        value += adj
        if getattr(raw_evidence, "historical_outcome_score", None) is not None:
            basis_parts.append("historical outcome data")
        if getattr(raw_evidence, "applicable_lessons", None):
            basis_parts.append("applicable lessons")
        if getattr(raw_evidence, "similar_closed_missions", None):
            basis_parts.append("similar prior missions")

    if officer_confidences:
        avg = sum(officer_confidences) / len(officer_confidences) / 100.0
        # Blend officer agreement gently (70% prior, 30% officer signal).
        value = (value * 0.7) + (avg * 0.3)
        basis_parts.append(f"{len(officer_confidences)} officer input(s)")

    if not basis_parts:
        basis_parts.append("no historical evidence — opinion-weighted only")

    return ConfidenceLevel.from_value(value, basis=", ".join(basis_parts))
