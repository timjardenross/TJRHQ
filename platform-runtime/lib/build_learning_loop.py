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
            # Two separate downstream vocabularies, neither of which is
            # Pending/In Progress/Completed above — verified against the live
            # schema 2026-07-05:
            #   decision_outcomes.outcome_status: CHECK-constrained to
            #     success/partial/failed only.
            #   quality_scores (via QualityScoring._calculate_score):
            #     Implemented/Modified/Deferred/Rejected/Unknown.
            decision_outcomes_status = (
                "success" if status in {"DELIVERED", "APPROVED_FOR_ENGINEERING"}
                else "failed" if status == "FAILED"
                else "partial"
            )
            quality_outcome_status = (
                "Implemented" if status in {"DELIVERED", "APPROVED_FOR_ENGINEERING"}
                else "Rejected" if status == "FAILED"
                else "Unknown"
            )

            # decision_outcomes.decision_id FKs to commander_decisions(id) (uuid),
            # NOT decision_records(id) (text) — verified against the live schema
            # 2026-07-05 (see reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md).
            # This insert previously targeted the wrong parent/columns entirely
            # (implementation_notes/outcome_timestamp don't exist on this table,
            # and outcome_id/decision_id here are bigint/uuid, not the OUT-.../
            # DEC-... text ids generated above) and was silently failing.
            commander_decision_id = str(uuid4())
            cd_result = client.insert(
                "commander_decisions",
                {
                    "id": commander_decision_id,
                    "decision_title": f"{mission_title} {event_type}",
                    "decision_summary": memory_text,
                    "source": "build-learning-loop",
                    "channel_id": channel_id,
                    "user_id": user_id or approver_user_id,
                    "thread_ts": thread_ts,
                    "route": "/build",
                    "confidence": 0.9,
                    "status": outcome_status,
                    "metadata": payload["metadata"],
                },
            )
            if not cd_result.ok:
                log.warning("[build-learning-loop] commander_decisions write failed: %s", cd_result.error)
                return

            outcome_payload = {
                "decision_id": commander_decision_id,
                "mission_id": source_record,
                "outcome_status": decision_outcomes_status,
                "outcome_notes": notes or memory_text,
                "evaluation_date": datetime.utcnow().isoformat(),
                "evaluator": user_id or approver_user_id or "unknown",
            }
            outcome_result = client.insert("decision_outcomes", outcome_payload, returning=True)
            if outcome_result.ok and outcome_result.data:
                outcome_bigint_id = outcome_result.data[0].get("id")
                raw = client.raw_client
                if raw is not None and outcome_bigint_id is not None:
                    try:
                        quality_scoring = QualityScoring(raw)
                        feedback_loops = FeedbackLoops(raw)
                        quality_scoring.score_outcome(
                            outcome_id=outcome_bigint_id,
                            decision_id=decision_id,
                            outcome_status=quality_outcome_status,
                            implementation_notes=notes or memory_text,
                            provider_name=None,
                            model_name=None,
                            provider_route="/build",
                            feedback_loops=feedback_loops,
                        )
                    except Exception as exc:
                        log.warning("[build-learning-loop] scoring/feedback skipped: %s", exc)
            else:
                log.warning("[build-learning-loop] decision_outcomes write failed: %s", outcome_result.error)
    except Exception as exc:
        log.warning("[build-learning-loop] decision/outcome chain write failed: %s", exc)
