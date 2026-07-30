"""Officer Intelligence Processing (EXEC-010B WP3).

When a note reaches OFFICER_REVIEW, each assigned officer analyses it using
their domain lens. Findings are written to officer_findings JSONB. Once all
assigned officers have responded, the note advances to NUMBER_ONE_REVIEW.

Integrates with EXEC-010A officer framework — reuses officer domain knowledge
and keyword catalogues. No new officers; no new authority structure.

Public API:
    assign_officers(note: dict) -> list[str]
    analyse_note(note_id: str, officer: str, supabase_client) -> dict
    process_officer_review(note_id: str, supabase_client) -> ProcessResult
    advance_to_officer_review(note_id: str, supabase_client) -> dict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


# ── Officer domain keyword catalogues ─────────────────────────────────────────
# Reuses the same domain concepts as officer_triggers.py / officer_context.py.

_OFFICER_KEYWORDS: dict[str, list[str]] = {
    "research": [
        "research", "intelligence", "scan", "analysis", "investigation",
        "insight", "pattern", "signal", "trend", "risk", "emerging",
    ],
    "knowledge": [
        "lesson", "knowledge", "capture", "principle", "playbook", "adr",
        "decision record", "best practice", "retrospective", "learning",
    ],
    "engineering": [
        "technical", "architecture", "debt", "capability", "system",
        "infrastructure", "build", "deploy", "integration", "performance",
        "reliability", "security", "code", "module", "service",
    ],
    "medical": [
        "health", "capacity", "recovery", "wellbeing", "energy", "fatigue",
        "nervous system", "sleep", "stress", "pain", "symptom", "rest",
    ],
    "operations": [
        "operational", "delivery", "blocker", "execution", "process",
        "workflow", "coordination", "scheduling", "timeline", "pipeline",
    ],
    "qa": [
        "quality", "validation", "review", "decision", "gate", "test",
        "acceptance", "criteria", "compliance", "governance", "audit",
    ],
    "number_one": [
        "assignment", "coordination", "priority", "resource", "allocation",
        "mission", "sprint", "backlog", "workload", "crew",
    ],
}


def assign_officers(note: dict[str, Any]) -> list[str]:
    """Determine which officers should review this note based on content.

    Always includes 'research' as a baseline intelligence officer.
    Returns unique, sorted list.
    """
    content = " ".join([
        note.get("title") or "",
        note.get("raw_content") or "",
        " ".join(note.get("tags") or []),
    ]).lower()

    assigned: set[str] = {"research"}
    for officer, keywords in _OFFICER_KEYWORDS.items():
        if officer == "research":
            continue
        if any(kw in content for kw in keywords):
            assigned.add(officer)

    return sorted(assigned)


def _derive_finding(officer: str, content: str, matched: list[str]) -> str:
    """Generate a plain-text officer finding statement."""
    domain_summaries: dict[str, str] = {
        "research":   "Intelligence scan: note contains signals requiring research analysis.",
        "knowledge":  "Knowledge relevance: candidate for knowledge capture or lesson record.",
        "engineering": "Technical dimension: contains engineering/architecture signals.",
        "medical":    "Capacity dimension: contains health or wellbeing signals.",
        "operations": "Operational dimension: contains delivery or process signals.",
        "qa":         "Governance dimension: contains decision quality or compliance signals.",
        "number_one": "Coordination dimension: contains mission or resource signals.",
    }
    if matched:
        return f"{domain_summaries.get(officer, 'Domain review required.')} Keywords matched: {', '.join(matched[:5])}."
    return domain_summaries.get(officer, "No domain-specific signals detected.")


def analyse_note(
    note: dict[str, Any],
    officer: str,
) -> dict[str, Any]:
    """Run domain analysis for a single officer on a note.

    Returns the finding dict (caller is responsible for persisting it).
    """
    content = " ".join([
        note.get("title") or "",
        note.get("raw_content") or "",
    ]).lower()

    keywords = _OFFICER_KEYWORDS.get(officer, [])
    matched = [kw for kw in keywords if kw in content]
    relevance = round(min(1.0, len(matched) / max(len(keywords), 1)), 2)

    finding: dict[str, Any] = {
        "officer":           officer,
        "analysed_at":       datetime.utcnow().isoformat(),
        "relevance":         relevance,
        "matched_keywords":  matched[:10],
        "recommendation":    _derive_finding(officer, content, matched),
        "confidence":        round(min(0.9, 0.3 + relevance * 0.6), 2),
    }

    if officer == "research":
        themes = [kw for kw in ["risk", "trend", "signal", "emerging", "pattern"] if kw in content]
        finding["themes_detected"] = themes

    elif officer == "engineering":
        debt_signals = [kw for kw in ["debt", "legacy", "refactor", "performance"] if kw in content]
        finding["technical_debt_signals"] = debt_signals

    elif officer == "medical":
        severity_signals = [kw for kw in ["pain", "fatigue", "stress", "crisis"] if kw in content]
        finding["severity_signals"] = severity_signals

    return finding


@dataclass
class ProcessResult:
    note_id: str
    officers_analysed: list[str] = field(default_factory=list)
    new_status: str = "OFFICER_REVIEW"
    error: str | None = None


def advance_to_officer_review(
    note_id: str,
    supabase_client: Any,
) -> dict[str, Any]:
    """Transition a CAPTURED note to OFFICER_REVIEW and assign officers.

    Idempotent — safe to call on already-assigned notes.
    """
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, tags, status, assigned_officers"
    ).eq("id", note_id).single().execute()

    note = result.data
    if not note:
        return {"error": f"Note {note_id} not found"}

    if note["status"] not in ("CAPTURED",):
        return {"status": "skipped", "reason": f"Note already in {note['status']}"}

    officers = note.get("assigned_officers") or assign_officers(note)

    supabase_client.table("intelligence_notes").update({
        "status":           "OFFICER_REVIEW",
        "assigned_officers": officers,
    }).eq("id", note_id).execute()

    log.info("[notebook-officer] Note %s advanced to OFFICER_REVIEW, assigned: %s", note_id, officers)
    return {"status": "advanced", "note_id": note_id, "assigned_officers": officers}


def process_officer_review(
    note_id: str,
    supabase_client: Any,
) -> ProcessResult:
    """Run analysis for all assigned officers and advance to NUMBER_ONE_REVIEW.

    Writes individual officer findings to officer_findings JSONB.
    Advances to NUMBER_ONE_REVIEW when all officers have responded.
    """
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, tags, status, assigned_officers, officer_findings"
    ).eq("id", note_id).single().execute()

    note = result.data
    if not note:
        return ProcessResult(note_id=note_id, error=f"Note {note_id} not found")

    if note["status"] != "OFFICER_REVIEW":
        return ProcessResult(note_id=note_id, error=f"Note not in OFFICER_REVIEW (is {note['status']})")

    assigned: list[str] = note.get("assigned_officers") or []
    if not assigned:
        assigned = assign_officers(note)

    existing_findings: dict[str, Any] = note.get("officer_findings") or {}
    officers_analysed: list[str] = []

    for officer in assigned:
        if officer in existing_findings:
            officers_analysed.append(officer)
            continue
        finding = analyse_note(note, officer)
        existing_findings[officer] = finding
        officers_analysed.append(officer)
        log.info("[notebook-officer] Officer %s analysed note %s (relevance=%.2f)", officer, note_id, finding["relevance"])

    supabase_client.table("intelligence_notes").update({
        "officer_findings":   existing_findings,
        "assigned_officers":  assigned,
        "status":             "NUMBER_ONE_REVIEW",
    }).eq("id", note_id).execute()

    log.info("[notebook-officer] Note %s advanced to NUMBER_ONE_REVIEW after %d officer analyses", note_id, len(officers_analysed))
    return ProcessResult(
        note_id=note_id,
        officers_analysed=officers_analysed,
        new_status="NUMBER_ONE_REVIEW",
    )


def batch_process_officer_review(supabase_client: Any) -> list[ProcessResult]:
    """Process all notes currently in OFFICER_REVIEW status."""
    result = supabase_client.table("intelligence_notes").select(
        "id"
    ).eq("status", "OFFICER_REVIEW").execute()

    results: list[ProcessResult] = []
    for row in result.data or []:
        try:
            r = process_officer_review(row["id"], supabase_client)
            results.append(r)
        except Exception as exc:
            log.warning("[notebook-officer] Failed to process note %s: %s", row["id"], exc)
            results.append(ProcessResult(note_id=row["id"], error=str(exc)))
    return results


__all__ = [
    "assign_officers",
    "analyse_note",
    "advance_to_officer_review",
    "process_officer_review",
    "batch_process_officer_review",
    "ProcessResult",
]
