"""Structured build lifecycle events for the learning loop.

These helpers emit machine-readable lifecycle records for engineering handoff
approval and batch progression. The goal is to preserve a structured trail
that downstream learning-loop consumers can query and understand.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4
from typing import Any

from tools.supabase.client import CommanderSupabaseClient, log_commander_event, log_decision, log_memory_event
from lib.feedback_loops_service import FeedbackLoops
from lib.quality_scoring_service import QualityScoring

log = logging.getLogger(__name__)


def generate_build_decision_id() -> str:
    """Generate a canonical decision id for build handoff lifecycle events."""
    return f"DEC-REC-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"


def generate_build_outcome_id() -> str:
    """Generate a canonical outcome id for build handoff lifecycle events."""
    return f"OUT-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"


def record_build_lifecycle_event(
    *,
    event_type: str,
    decision_id: str,
    source_record: str,
    handoff_path: str,
    mission_title: str,
    status: str,
    batch_status: str,
    batch_group: str,
    priority: str,
    outcome_id: str | None = None,
    approver_user_id: str | None = None,
    batch_actor: str | None = None,
    notes: str | None = None,
    thread_ts: str | None = None,
    channel_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Emit a structured lifecycle record for the build/learning loop."""
    captured_at = datetime.utcnow().isoformat()
    payload: dict[str, Any] = {
        "source": "slack-build",
        "channel_id": channel_id,
        "user_id": user_id or approver_user_id,
        "thread_ts": thread_ts,
        "route": "/build",
        "confidence": 0.9,
        "event_type": event_type,
        "metadata": {
            "schema": "build-lifecycle-v2",
            "event_type": event_type,
            "decision_id": decision_id,
            "outcome_id": outcome_id,
            "source_record": source_record,
            "handoff_path": handoff_path,
            "mission_title": mission_title,
            "status": status,
            "batch_status": batch_status,
            "batch_group": batch_group,
            "priority": priority,
            "approver_user_id": approver_user_id,
            "batch_actor": batch_actor,
            "notes": notes or "",
            "captured_at": captured_at,
        },
    }

    memory_text = (
        f"Build lifecycle event: {event_type}\n"
        f"Decision ID: {decision_id}\n"
        f"Outcome ID: {outcome_id or 'pending'}\n"
        f"Mission: {mission_title}\n"
        f"Status: {status}\n"
        f"Batch Status: {batch_status}\n"
        f"Batch Group: {batch_group}\n"
        f"Priority: {priority}\n"
        f"Handoff: {handoff_path}\n"
        f"Source Record: {source_record}\n"
        f"Notes: {notes or 'none'}"
    )

    try:
        log_commander_event(payload | {"message_text": memory_text})
    except Exception as exc:
        log.warning("[build-learning-loop] commander_event write failed: %s", exc)

    try:
        log_decision(
            {
                "decision_title": f"{mission_title} {event_type}",
                "decision_summary": memory_text,
                "source": "slack-build",
                "channel_id": channel_id,
                "user_id": user_id or approver_user_id,
                "thread_ts": thread_ts,
                "route": "/build",
                "confidence": 0.9,
                "metadata": payload["metadata"],
            }
        )
    except Exception as exc:
        log.warning("[build-learning-loop] commander_decision write failed: %s", exc)

    try:
        log_memory_event(
            {
                "memory_text": memory_text,
                "source": "slack-build",
                "channel_id": channel_id,
                "user_id": user_id or approver_user_id,
                "thread_ts": thread_ts,
                "route": "/build",
                "confidence": 0.9,
                "tags": ["build", "learning-loop", "engineering-handoff", event_type.lower()],
                "metadata": payload["metadata"],
            }
        )
    except Exception as exc:
        log.warning("[build-learning-loop] commander_memory write failed: %s", exc)

    try:
        client = CommanderSupabaseClient()
        decision_payload = {
            "id": decision_id,
            "mission_id": source_record,
            "recommendation_id": handoff_path,
            "recommendation_text": memory_text,
            "human_decision": status,
            "decision_maker": user_id or approver_user_id or "unknown",
            "decision_reason": notes or "",
            "decision_timestamp": captured_at,
            "captured_timestamp": captured_at,
            "metadata": {
                **payload["metadata"],
                "source": "build-learning-loop",
            },
        }
        client.insert("decision_records", decision_payload)

        if outcome_id:
            outcome_status = {
                "handoff_created": "Pending",
                "batch_claimed": "In Progress",
                "batch_advanced": "Completed" if status in {"DELIVERED", "APPROVED_FOR_ENGINEERING"} else "In Progress",
            }.get(event_type, "Pending")
            outcome_payload = {
                "id": outcome_id,
                "decision_id": decision_id,
                "outcome_status": outcome_status,
                "implementation_notes": notes or memory_text,
                "outcome_timestamp": datetime.utcnow().isoformat(),
            }
            outcome_result = client.insert("decision_outcomes", outcome_payload)
            if outcome_result.ok:
                try:
                    quality_scoring = QualityScoring(client)
                    feedback_loops = FeedbackLoops(client)
                    quality_scoring.score_outcome(
                        outcome_id=outcome_id,
                        decision_id=decision_id,
                        outcome_status=outcome_status,
                        implementation_notes=notes or memory_text,
                        provider_name=None,
                        model_name=None,
                        provider_route="/build",
                        feedback_loops=feedback_loops,
                    )
                except Exception as exc:
                    log.warning("[build-learning-loop] scoring/feedback skipped: %s", exc)
    except Exception as exc:
        log.warning("[build-learning-loop] decision/outcome chain write failed: %s", exc)
