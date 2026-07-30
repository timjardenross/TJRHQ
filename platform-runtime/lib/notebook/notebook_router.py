"""Routing & Promotion (EXEC-010B WP8).

Human approval is mandatory before any note is promoted to ROUTED.
Officers set recommended_route (via WP5 triage) but CANNOT set ROUTED.
Only the Captain (via the UI) or an explicit approve_route() call from a
human-initiated process may promote a note.

This module also handles pipeline orchestration: advancing notes through
the CAPTURED → OFFICER_REVIEW → NUMBER_ONE_REVIEW → READY_FOR_ROUTING
stages automatically (officer processing is autonomous). The final
READY_FOR_ROUTING → ROUTED step requires human approval every time.

Public API:
    approve_route(note_id, approved_route, routed_to_type, routed_to_id, supabase_client) -> RouteResult
    archive_note(note_id, supabase_client) -> RouteResult
    get_routing_queue(supabase_client) -> list[dict]
    run_notebook_pipeline(supabase_client) -> PipelineResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class RouteResult:
    note_id: str
    action: str
    route: str | None = None
    routed_to_type: str | None = None
    error: str | None = None


@dataclass
class PipelineResult:
    advanced_to_officer_review: list[str] = field(default_factory=list)
    advanced_to_number_one: list[str] = field(default_factory=list)
    advanced_to_ready: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ran_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def total_advanced(self) -> int:
        return (len(self.advanced_to_officer_review)
                + len(self.advanced_to_number_one)
                + len(self.advanced_to_ready))


_VALID_ROUTES = frozenset({"captain", "xo", "number_one", "officer", "knowledge", "archive"})
_VALID_ROUTED_TO_TYPES = frozenset({"mission", "decision", "lesson", "knowledge", "archived"})


def approve_route(
    note_id: str,
    approved_route: str,
    routed_to_type: str,
    supabase_client: Any,
    routed_to_id: str | None = None,
) -> RouteResult:
    """Captain approves the routing of a note. MANDATORY human action.

    Idempotent — calling on an already-ROUTED note returns 'already_routed'.
    """
    if approved_route not in _VALID_ROUTES:
        return RouteResult(note_id=note_id, action="error", error=f"Invalid route: {approved_route}")
    if routed_to_type not in _VALID_ROUTED_TO_TYPES:
        return RouteResult(note_id=note_id, action="error", error=f"Invalid routed_to_type: {routed_to_type}")

    check = supabase_client.table("intelligence_notes").select("id, status").eq("id", note_id).single().execute()
    note = check.data
    if not note:
        return RouteResult(note_id=note_id, action="error", error=f"Note {note_id} not found")

    if note["status"] == "ROUTED":
        return RouteResult(note_id=note_id, action="already_routed", route=approved_route)

    supabase_client.table("intelligence_notes").update({
        "status":          "ROUTED",
        "recommended_route": approved_route,
        "routed_to_type":  routed_to_type,
        "routed_to_id":    routed_to_id,
    }).eq("id", note_id).execute()

    log.info(
        "[notebook-router] Note %s ROUTED → %s (%s) — human approved",
        note_id, approved_route, routed_to_type,
    )
    return RouteResult(
        note_id=note_id,
        action="routed",
        route=approved_route,
        routed_to_type=routed_to_type,
    )


def archive_note(note_id: str, supabase_client: Any) -> RouteResult:
    """Archive a note. Available to the Captain at any pipeline stage."""
    check = supabase_client.table("intelligence_notes").select("id, status").eq("id", note_id).single().execute()
    note = check.data
    if not note:
        return RouteResult(note_id=note_id, action="error", error=f"Note {note_id} not found")

    if note["status"] == "ARCHIVED":
        return RouteResult(note_id=note_id, action="already_archived")

    supabase_client.table("intelligence_notes").update({
        "status": "ARCHIVED",
    }).eq("id", note_id).execute()

    return RouteResult(note_id=note_id, action="archived")


def get_routing_queue(supabase_client: Any) -> list[dict[str, Any]]:
    """Return notes at READY_FOR_ROUTING awaiting Captain approval."""
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, classification, recommended_route, "
        "strategic_alignment_score, value_score, urgency_score, confidence_score, "
        "triage_summary, created_at"
    ).eq("status", "READY_FOR_ROUTING").order("strategic_alignment_score", desc=True).execute()
    return result.data or []


def run_notebook_pipeline(supabase_client: Any) -> PipelineResult:
    """Advance all notes through the autonomous pipeline stages.

    CAPTURED → OFFICER_REVIEW → NUMBER_ONE_REVIEW → READY_FOR_ROUTING.
    The final READY_FOR_ROUTING → ROUTED step is NOT included here;
    it requires explicit human approval via approve_route().
    """
    from .notebook_officer import advance_to_officer_review, process_officer_review
    from .notebook_review import triage_note

    result = PipelineResult()

    # Stage 1: CAPTURED → OFFICER_REVIEW
    captured = supabase_client.table("intelligence_notes").select("id").eq(
        "status", "CAPTURED"
    ).execute()
    for row in captured.data or []:
        try:
            r = advance_to_officer_review(row["id"], supabase_client)
            if r.get("status") == "advanced":
                result.advanced_to_officer_review.append(row["id"])
        except Exception as exc:
            result.errors.append(f"CAPTURED→OFFICER_REVIEW {row['id']}: {exc}")

    # Stage 2: OFFICER_REVIEW → NUMBER_ONE_REVIEW
    in_review = supabase_client.table("intelligence_notes").select("id").eq(
        "status", "OFFICER_REVIEW"
    ).execute()
    for row in in_review.data or []:
        try:
            r = process_officer_review(row["id"], supabase_client)
            if r.new_status == "NUMBER_ONE_REVIEW":
                result.advanced_to_number_one.append(row["id"])
        except Exception as exc:
            result.errors.append(f"OFFICER_REVIEW→NUMBER_ONE_REVIEW {row['id']}: {exc}")

    # Stage 3: NUMBER_ONE_REVIEW → READY_FOR_ROUTING
    awaiting_triage = supabase_client.table("intelligence_notes").select("id").eq(
        "status", "NUMBER_ONE_REVIEW"
    ).execute()
    for row in awaiting_triage.data or []:
        try:
            r = triage_note(row["id"], supabase_client)
            if not r.error:
                result.advanced_to_ready.append(row["id"])
        except Exception as exc:
            result.errors.append(f"NUMBER_ONE_REVIEW→READY_FOR_ROUTING {row['id']}: {exc}")

    log.info(
        "[notebook-router] Pipeline run: %d captured, %d reviewed, %d triaged, %d errors",
        len(result.advanced_to_officer_review),
        len(result.advanced_to_number_one),
        len(result.advanced_to_ready),
        len(result.errors),
    )
    return result


__all__ = [
    "approve_route",
    "archive_note",
    "get_routing_queue",
    "run_notebook_pipeline",
    "RouteResult",
    "PipelineResult",
]
