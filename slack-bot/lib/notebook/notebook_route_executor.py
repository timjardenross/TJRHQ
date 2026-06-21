"""Route Execution Engine (EXEC-010C WP1).

Converts Captain-approved notebook routes into actual system artefacts.
Called after a note reaches ROUTED status (human approval mandatory — see
notebook_router.py WP8). The executor creates the artefact and writes back
the entity ID for full traceability.

Supported routes:
    MISSION              → missions table (Idea status, awaiting XO approval)
    BUILD_REQUEST        → build_request_inbox table (PENDING_TRIAGE)
    STRATEGIC_INITIATIVE → strategic_objectives table
    IMPROVEMENT          → improvement backlog (decisions table)
    KNOWLEDGE_ARTICLE    → lessons_learned table
    RESEARCH_REQUEST     → research_memory table
    COMMUNICATION_OPPORTUNITY → comms_content table

Idempotency: if a note already has a routed_to_id, execution is skipped.
Audit trail: routed_at, routed_by, routed_entity_type written on success.

Public API:
    execute_route(note_id, supabase_client, routed_by="system") -> ExecutionResult
    execute_all_routed(supabase_client) -> list[ExecutionResult]
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_ROUTES = frozenset({
    "MISSION",
    "BUILD_REQUEST",
    "STRATEGIC_INITIATIVE",
    "IMPROVEMENT",
    "KNOWLEDGE_ARTICLE",
    "RESEARCH_REQUEST",
    "COMMUNICATION_OPPORTUNITY",
})

# Map recommended_route values (from WP5 triage) to WP1 route types
ROUTE_MAP: dict[str, str] = {
    "captain":    "MISSION",
    "xo":         "MISSION",
    "number_one": "IMPROVEMENT",
    "officer":    "KNOWLEDGE_ARTICLE",
    "knowledge":  "KNOWLEDGE_ARTICLE",
}


@dataclass
class ExecutionResult:
    note_id: str
    route_type: str
    artefact_id: str | None = None
    artefact_table: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.artefact_id is not None


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _slug(text: str, maxlen: int = 60) -> str:
    return text.strip()[:maxlen]


# ── Route handlers ─────────────────────────────────────────────────────────────

def _create_mission(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Insert a mission stub into the missions table (status=Idea)."""
    mid = f"M-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-NB"
    title = note.get("title") or _slug(note.get("raw_content", "Notebook capture"), 80)
    description = "\n\n".join(filter(None, [
        note.get("triage_summary"),
        note.get("raw_content"),
    ]))

    record: dict[str, Any] = {
        "id":           mid,
        "title":        title,
        "created_by":   "notebook",
        "owner":        "notebook",
        "status":       "Idea",
        "description":  description[:2000],
        "created_at":   _now(),
        "updated_at":   _now(),
        "updated_by":   "notebook",
    }

    try:
        supabase_client.table("missions").insert(record).execute()
        log.info("[notebook-executor] Mission %s created from note %s", mid, note["id"])
        return mid, "missions"
    except Exception as exc:
        log.warning("[notebook-executor] Mission insert failed for note %s: %s", note["id"], exc)
        return None, "missions"


def _create_build_request(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Insert into build_request_inbox (PENDING_TRIAGE)."""
    bid = f"BREQ-NB-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    title = note.get("title") or _slug(note.get("raw_content", "Notebook build request"), 80)

    record: dict[str, Any] = {
        "request_id":   bid,
        "title":        title,
        "summary":      note.get("triage_summary") or note.get("raw_content", "")[:500],
        "requested_by": "notebook",
        "status":       "PENDING_TRIAGE",
        "source":       f"intelligence_notes:{note['id']}",
        "created_at":   _now(),
    }

    try:
        supabase_client.table("build_request_inbox").insert(record).execute()
        log.info("[notebook-executor] Build request %s created from note %s", bid, note["id"])
        return bid, "build_request_inbox"
    except Exception as exc:
        log.warning("[notebook-executor] Build request insert failed for note %s: %s", note["id"], exc)
        return None, "build_request_inbox"


def _create_strategic_initiative(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Insert a strategic objective stub."""
    obj_id = f"OBJ-NB-{datetime.utcnow().strftime('%Y%m%d')}"
    title = note.get("title") or _slug(note.get("raw_content", "Notebook initiative"), 80)

    record: dict[str, Any] = {
        "id":          str(uuid.uuid4()),
        "objective_id": obj_id,
        "title":        title,
        "description":  note.get("raw_content", "")[:1000],
        "domain":       "Starship Endeavour",
        "status":       "active",
        "priority":     "P2",
        "owner":        "captain",
        "created_at":   _now(),
        "updated_at":   _now(),
    }

    try:
        supabase_client.table("strategic_objectives").insert(record).execute()
        log.info("[notebook-executor] Strategic objective %s created from note %s", obj_id, note["id"])
        return obj_id, "strategic_objectives"
    except Exception as exc:
        log.warning("[notebook-executor] Strategic objective insert failed for note %s: %s", note["id"], exc)
        return None, "strategic_objectives"


def _create_improvement(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Add to improvement backlog (decisions table, owner prefix pattern)."""
    dec_id = f"DEC-NB-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    content_preview = _slug(note.get("raw_content", "Notebook improvement idea"), 80)

    record: dict[str, Any] = {
        "id":         dec_id,
        "owner":      f"notebook_improvement:{note['id']}",
        "statement":  f"[IMPROVEMENT] notebook: {content_preview}",
        "rationale":  "\n".join(filter(None, [
            f"SCORE: {int((note.get('value_score') or 0) * 10)} | BAND: medium",
            f"SOURCE: intelligence_notes:{note['id']}",
            note.get("triage_summary", ""),
        ])),
        "status":     "Active",
        "created_by": "notebook",
        "created_at": _now(),
        "updated_at": _now(),
        "updated_by": "notebook",
    }

    try:
        supabase_client.table("decisions").insert(record).execute()
        log.info("[notebook-executor] Improvement %s created from note %s", dec_id, note["id"])
        return dec_id, "decisions"
    except Exception as exc:
        log.warning("[notebook-executor] Improvement insert failed for note %s: %s", note["id"], exc)
        return None, "decisions"


def _create_knowledge_article(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Insert into lessons_learned as a knowledge capture."""
    lesson_date = datetime.utcnow().strftime("%Y-%m-%d")
    ll_id = f"LL-NB-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    title = note.get("title") or _slug(note.get("raw_content", "Notebook knowledge capture"), 80)

    record: dict[str, Any] = {
        "id":            str(uuid.uuid4()),
        "lesson_id":     ll_id,
        "title":         title,
        "date_recorded": lesson_date,
        "context":       "Captain's Notebook — intelligence capture",
        "lesson_text":   note.get("raw_content", "")[:2000],
        "outcome":       note.get("triage_summary", ""),
        "future_guidance": note.get("triage_summary", ""),
        "source":        "manual",
        "created_at":    _now(),
        "updated_at":    _now(),
    }

    try:
        supabase_client.table("lessons_learned").insert(record).execute()
        log.info("[notebook-executor] Knowledge article %s created from note %s", ll_id, note["id"])
        return ll_id, "lessons_learned"
    except Exception as exc:
        log.warning("[notebook-executor] Knowledge article insert failed for note %s: %s", note["id"], exc)
        return None, "lessons_learned"


def _create_research_request(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Insert into research_memory as a research request."""
    res_id = f"RES-NB-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    title = note.get("title") or _slug(note.get("raw_content", "Notebook research request"), 80)

    record: dict[str, Any] = {
        "id":          str(uuid.uuid4()),
        "research_id": res_id,
        "query":       title,
        "summary":     note.get("raw_content", "")[:1000],
        "status":      "pending",
        "source":      f"intelligence_notes:{note['id']}",
        "created_at":  _now(),
    }

    try:
        supabase_client.table("research_memory").insert(record).execute()
        log.info("[notebook-executor] Research request %s created from note %s", res_id, note["id"])
        return res_id, "research_memory"
    except Exception as exc:
        log.warning("[notebook-executor] Research request insert failed for note %s: %s", note["id"], exc)
        return None, "research_memory"


def _create_comms_opportunity(note: dict[str, Any], supabase_client: Any) -> tuple[str | None, str]:
    """Insert into comms_content as a communication opportunity."""
    comms_id = f"comms-nb-{note['id'][:8]}"
    title = note.get("title") or _slug(note.get("raw_content", "Notebook comms opportunity"), 80)

    record: dict[str, Any] = {
        "id":             str(uuid.uuid4()),
        "content_id":     comms_id,
        "title":          title,
        "source_kind":    "notebook",
        "source_ref":     note["id"],
        "classification": "draft",
        "status":         "opportunity",
        "created_at":     _now(),
        "updated_at":     _now(),
    }

    try:
        supabase_client.table("comms_content").insert(record).execute()
        log.info("[notebook-executor] Comms opportunity %s created from note %s", comms_id, note["id"])
        return comms_id, "comms_content"
    except Exception as exc:
        log.warning("[notebook-executor] Comms opportunity insert failed for note %s: %s", note["id"], exc)
        return None, "comms_content"


_ROUTE_HANDLERS = {
    "MISSION":                   _create_mission,
    "BUILD_REQUEST":             _create_build_request,
    "STRATEGIC_INITIATIVE":      _create_strategic_initiative,
    "IMPROVEMENT":               _create_improvement,
    "KNOWLEDGE_ARTICLE":         _create_knowledge_article,
    "RESEARCH_REQUEST":          _create_research_request,
    "COMMUNICATION_OPPORTUNITY": _create_comms_opportunity,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def execute_route(
    note_id: str,
    supabase_client: Any,
    routed_by: str = "system",
    route_type: str | None = None,
) -> ExecutionResult:
    """Execute the approved route for a notebook note — creates the artefact.

    Captain approval must have occurred first (status=ROUTED). Idempotent:
    skips notes that already have a routed_to_id.
    """
    result = supabase_client.table("intelligence_notes").select(
        "id, title, raw_content, status, recommended_route, routed_to_type, "
        "routed_to_id, triage_summary, classification, value_score"
    ).eq("id", note_id).single().execute()

    note = result.data
    if not note:
        return ExecutionResult(note_id=note_id, route_type=route_type or "", error="Note not found")

    if note["status"] != "ROUTED":
        return ExecutionResult(
            note_id=note_id, route_type=route_type or "",
            skipped=True, skip_reason=f"Note not ROUTED (is {note['status']})",
        )

    if note.get("routed_to_id"):
        return ExecutionResult(
            note_id=note_id,
            route_type=route_type or note.get("routed_to_type", ""),
            artefact_id=note["routed_to_id"],
            skipped=True, skip_reason="Already executed — routed_to_id present",
        )

    # Determine route type
    effective_route = route_type or ROUTE_MAP.get(
        note.get("recommended_route") or "", "KNOWLEDGE_ARTICLE"
    )
    if effective_route not in SUPPORTED_ROUTES:
        effective_route = "KNOWLEDGE_ARTICLE"

    handler = _ROUTE_HANDLERS.get(effective_route)
    if not handler:
        return ExecutionResult(
            note_id=note_id, route_type=effective_route,
            error=f"No handler for route type {effective_route}",
        )

    artefact_id, artefact_table = handler(note, supabase_client)
    if not artefact_id:
        return ExecutionResult(
            note_id=note_id, route_type=effective_route,
            error=f"Artefact creation failed for route {effective_route}",
        )

    # Write traceability fields back to the note
    try:
        supabase_client.table("intelligence_notes").update({
            "routed_to_id":       artefact_id,
            "routed_to_type":     artefact_table,
            "routed_entity_type": effective_route,
            "routed_at":          _now(),
            "routed_by":          routed_by,
        }).eq("id", note_id).execute()
    except Exception as exc:
        log.warning("[notebook-executor] Traceability update failed for note %s: %s", note_id, exc)

    return ExecutionResult(
        note_id=note_id,
        route_type=effective_route,
        artefact_id=artefact_id,
        artefact_table=artefact_table,
    )


def execute_all_routed(
    supabase_client: Any,
    routed_by: str = "system",
) -> list[ExecutionResult]:
    """Execute routes for all ROUTED notes that have no routed_to_id yet."""
    result = supabase_client.table("intelligence_notes").select("id").eq(
        "status", "ROUTED"
    ).is_("routed_to_id", "null").execute()

    results: list[ExecutionResult] = []
    for row in result.data or []:
        try:
            r = execute_route(row["id"], supabase_client, routed_by=routed_by)
            results.append(r)
        except Exception as exc:
            log.warning("[notebook-executor] Unhandled error for note %s: %s", row["id"], exc)
            results.append(ExecutionResult(note_id=row["id"], route_type="", error=str(exc)))

    log.info(
        "[notebook-executor] Executed %d routes: %d success, %d errors",
        len(results),
        sum(1 for r in results if r.success),
        sum(1 for r in results if r.error),
    )
    return results


__all__ = [
    "execute_route",
    "execute_all_routed",
    "ExecutionResult",
    "SUPPORTED_ROUTES",
    "ROUTE_MAP",
]
