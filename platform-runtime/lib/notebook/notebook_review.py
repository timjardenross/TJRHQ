"""Number One Review Queue (EXEC-010B WP5).

When a note reaches NUMBER_ONE_REVIEW, Number One triages it:
- Derives classification from officer findings
- Computes five scores (strategic alignment, value, urgency, effort, content potential)
- Sets recommended_route
- Generates triage_summary
- Advances to READY_FOR_ROUTING

Integration: reuses officer_findings data produced by notebook_officer.py (WP3).
Strategic alignment scoring defers to notebook_assessment.py (WP6).

Public API:
    triage_note(note_id: str, supabase_client) -> TriageResult
    batch_triage(supabase_client) -> list[TriageResult]
    get_review_queue(supabase_client) -> list[dict]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .notebook_assessment import assess_strategic_alignment, compute_content_potential

log = logging.getLogger(__name__)


# ── Classification derivation ─────────────────────────────────────────────────

_CLASSIFICATION_SIGNALS: dict[str, list[str]] = {
    "strategic_decision":   ["strategy", "direction", "objective", "goal", "priority", "architecture"],
    "mission_candidate":    ["mission", "project", "initiative", "deliverable", "ship", "build"],
    "capability_gap":       ["capability", "gap", "missing", "unable", "blocked", "constraint"],
    "knowledge_item":       ["lesson", "insight", "pattern", "principle", "retrospective", "learning"],
    "investigation_needed": ["unclear", "unknown", "investigate", "research", "explore", "question"],
    "health_signal":        ["health", "capacity", "recovery", "energy", "pain", "fatigue"],
    "operational_issue":    ["blocker", "issue", "problem", "broken", "delayed", "stuck"],
    "improvement_idea":     ["improve", "better", "optimise", "refactor", "enhance", "idea"],
}


def _derive_classification(note: dict[str, Any], findings: dict[str, Any]) -> str:
    content = " ".join([
        note.get("title") or "",
        note.get("raw_content") or "",
        " ".join(note.get("tags") or []),
    ]).lower()

    # Check findings for strong domain signals
    if findings.get("medical") and findings["medical"].get("severity_signals"):
        return "health_signal"

    if findings.get("engineering") and findings["engineering"].get("technical_debt_signals"):
        return "capability_gap"

    # Keyword-based classification
    best_match = "knowledge_item"
    best_count = 0
    for classification, keywords in _CLASSIFICATION_SIGNALS.items():
        count = sum(1 for kw in keywords if kw in content)
        if count > best_count:
            best_count = count
            best_match = classification

    return best_match


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_urgency(note: dict[str, Any]) -> float:
    content = (note.get("raw_content") or "").lower()
    urgent_signals = ["urgent", "asap", "critical", "immediately", "now", "today", "crisis", "emergency"]
    matches = sum(1 for s in urgent_signals if s in content)
    return round(min(1.0, 0.1 + matches * 0.2), 2)


def _score_value(note: dict[str, Any], findings: dict[str, Any]) -> float:
    avg_relevance = 0.5
    if findings:
        relevances = [f.get("relevance", 0.5) for f in findings.values() if isinstance(f, dict)]
        if relevances:
            avg_relevance = sum(relevances) / len(relevances)

    confidence = 0.5
    if findings:
        confidences = [f.get("confidence", 0.5) for f in findings.values() if isinstance(f, dict)]
        if confidences:
            confidence = sum(confidences) / len(confidences)

    return round(min(1.0, avg_relevance * 0.6 + confidence * 0.4), 2)


def _score_effort(note: dict[str, Any], classification: str) -> float:
    effort_by_class: dict[str, float] = {
        "strategic_decision":   0.80,
        "mission_candidate":    0.70,
        "capability_gap":       0.75,
        "knowledge_item":       0.20,
        "investigation_needed": 0.50,
        "health_signal":        0.10,
        "operational_issue":    0.40,
        "improvement_idea":     0.50,
    }
    return effort_by_class.get(classification, 0.50)


def _compute_confidence(strategic: float, value: float, urgency: float) -> float:
    return round(min(0.95, (strategic * 0.4 + value * 0.4 + urgency * 0.2)), 2)


# ── Route recommendation ──────────────────────────────────────────────────────

def _recommend_route(
    classification: str,
    strategic_score: float,
    urgency_score: float,
) -> str:
    if classification == "health_signal":
        return "number_one"

    if strategic_score >= 0.70 or classification == "strategic_decision":
        return "captain"

    if classification in ("mission_candidate", "capability_gap"):
        return "xo"

    if classification == "knowledge_item":
        return "knowledge"

    if urgency_score >= 0.60:
        return "number_one"

    if classification == "improvement_idea":
        return "officer"

    return "xo"


# ── Triage summary ────────────────────────────────────────────────────────────

def _format_triage_summary(
    note: dict[str, Any],
    classification: str,
    recommended_route: str,
    officers_contributing: list[str],
    strategic_score: float,
    value_score: float,
    urgency_score: float,
) -> str:
    route_map = {
        "captain":    "Captain decision required",
        "xo":         "XO action",
        "number_one": "Number One coordination",
        "officer":    "Officer domain action",
        "knowledge":  "Knowledge capture",
        "archive":    "Archive",
    }
    lines = [
        f"Classification: {classification.replace('_', ' ').title()}.",
        f"Recommended route: {route_map.get(recommended_route, recommended_route)}.",
        f"Scores — Strategic: {int(strategic_score*100)}, Value: {int(value_score*100)}, Urgency: {int(urgency_score*100)}.",
    ]
    if officers_contributing:
        lines.append(f"Officers reviewed: {', '.join(officers_contributing)}.")
    return " ".join(lines)


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class TriageResult:
    note_id: str
    classification: str
    recommended_route: str
    strategic_alignment_score: float
    value_score: float
    urgency_score: float
    effort_score: float
    confidence_score: float
    content_potential_score: float
    triage_summary: str
    error: str | None = None


# ── Public API ────────────────────────────────────────────────────────────────

def triage_note(note_id: str, supabase_client: Any) -> TriageResult:
    """Number One triage: classify, score, route, advance to READY_FOR_ROUTING."""
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, tags, status, officer_findings, assigned_officers"
    ).eq("id", note_id).single().execute()

    note = result.data
    if not note:
        return TriageResult(
            note_id=note_id, classification="", recommended_route="", error=f"Note {note_id} not found",
            strategic_alignment_score=0, value_score=0, urgency_score=0, effort_score=0,
            confidence_score=0, content_potential_score=0, triage_summary="",
        )

    if note["status"] != "NUMBER_ONE_REVIEW":
        return TriageResult(
            note_id=note_id, classification="", recommended_route="",
            error=f"Note not in NUMBER_ONE_REVIEW (is {note['status']})",
            strategic_alignment_score=0, value_score=0, urgency_score=0, effort_score=0,
            confidence_score=0, content_potential_score=0, triage_summary="",
        )

    findings: dict[str, Any] = note.get("officer_findings") or {}
    officers_contributing = list(findings.keys())

    classification        = _derive_classification(note, findings)
    strategic_score       = assess_strategic_alignment(note)
    value_score           = _score_value(note, findings)
    urgency_score         = _score_urgency(note)
    effort_score          = _score_effort(note, classification)
    confidence_score      = _compute_confidence(strategic_score, value_score, urgency_score)
    content_potential     = compute_content_potential(note)
    recommended_route     = _recommend_route(classification, strategic_score, urgency_score)
    triage_summary        = _format_triage_summary(
        note, classification, recommended_route, officers_contributing,
        strategic_score, value_score, urgency_score,
    )

    supabase_client.table("intelligence_notes").update({
        "status":                    "READY_FOR_ROUTING",
        "classification":            classification,
        "strategic_alignment_score": strategic_score,
        "value_score":               value_score,
        "urgency_score":             urgency_score,
        "effort_score":              effort_score,
        "confidence_score":          confidence_score,
        "content_potential_score":   content_potential,
        "recommended_route":         recommended_route,
        "triage_summary":            triage_summary,
    }).eq("id", note_id).execute()

    log.info(
        "[notebook-review] Note %s triaged: %s → %s (strategic=%.2f)",
        note_id, classification, recommended_route, strategic_score,
    )
    return TriageResult(
        note_id=note_id,
        classification=classification,
        recommended_route=recommended_route,
        strategic_alignment_score=strategic_score,
        value_score=value_score,
        urgency_score=urgency_score,
        effort_score=effort_score,
        confidence_score=confidence_score,
        content_potential_score=content_potential,
        triage_summary=triage_summary,
    )


def batch_triage(supabase_client: Any) -> list[TriageResult]:
    """Triage all notes currently in NUMBER_ONE_REVIEW status."""
    result = supabase_client.table("intelligence_notes").select("id").eq(
        "status", "NUMBER_ONE_REVIEW"
    ).execute()

    results: list[TriageResult] = []
    for row in result.data or []:
        try:
            r = triage_note(row["id"], supabase_client)
            results.append(r)
        except Exception as exc:
            log.warning("[notebook-review] Failed to triage note %s: %s", row["id"], exc)
    return results


def get_review_queue(supabase_client: Any) -> list[dict[str, Any]]:
    """Return notes awaiting Number One triage."""
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, status, created_at, assigned_officers, officer_findings"
    ).eq("status", "NUMBER_ONE_REVIEW").order("created_at").execute()
    return result.data or []


__all__ = [
    "triage_note",
    "batch_triage",
    "get_review_queue",
    "TriageResult",
]
