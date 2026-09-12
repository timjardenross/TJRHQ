"""Structured build lifecycle events for the learning loop.

These helpers emit machine-readable lifecycle records for engineering handoff
approval and batch progression. The goal is to preserve a structured trail
that downstream learning-loop consumers can query and understand.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lib.feedback_loops_service import FeedbackLoops
from lib.quality_scoring_service import QualityScoring

from tools.supabase.client import (
    CommanderSupabaseClient,
    log_commander_event,
    log_decision,
    log_memory_event,
)

log = logging.getLogger(__name__)

# GAP 1 follow-up (2026-09-12): QualityScoring.score_output() (deepeval's
# HallucinationMetric, now judge-model-backed via core/model-router — see
# quality_scoring_service.py's _ModelRouterJudge) had zero callers anywhere
# in the platform. This wires the first one, deliberately shadow-mode only
# (compute + log, never persisted, never gates anything) — same convention
# as intelligence/scheduler.py's enrich_and_save(..., shadow_mode=True).
# Default OFF: a real LLM judge call can take up to ~300s (escalate's own
# timeout), which is not acceptable inline latency for every mission build
# event by default — this is for a monitored opt-in observation window, run
# in a background thread so it can never slow down or block the actual
# decision/outcome write path above it.
_SHADOW_SCORE_OUTPUT_ENABLED = os.environ.get("QUALITY_SCORE_OUTPUT_SHADOW_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _shadow_score_output(mission_title: str, event_type: str, memory_text: str, notes: str | None) -> None:
    """Fire-and-log: compute a deepeval hallucination-based quality score for
    the synthesized outcome narrative against whatever grounding text
    (mission title, notes) is available, and log it. Never raises into the
    caller, never persisted — see module docstring above."""
    try:
        shadow_score = QualityScoring().score_output(
            prompt=f"Mission: {mission_title}\nEvent: {event_type}",
            response=memory_text,
            context=[notes] if notes else None,
        )
        log.info("[build-learning-loop] shadow score_output (observational, not persisted): %s", shadow_score)
    except Exception as exc:
        log.warning("[build-learning-loop] shadow score_output failed (non-blocking): %s", exc)


def generate_build_decision_id() -> str:
    """Generate a canonical decision id for build handoff lifecycle events."""
    return f"DEC-REC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"


def generate_build_outcome_id() -> str:
    """Generate a canonical outcome id for build handoff lifecycle events."""
    return f"OUT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"


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
    captured_at = datetime.now(timezone.utc).isoformat()
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
        dr_result = client.insert("decision_records", decision_payload)
        if dr_result.ok:
            # Chief Engineer 2026-08-10 decisions-heartbeat follow-up: this is
            # the confirmed canonical decision_records writer — the majority
            # of the table's real historical rows carry
            # metadata.source="build-learning-loop" and match
            # generate_build_decision_id()'s DEC-REC-<ts>-<hex> format exactly.
            # See other real writers (research_learning_loop.py,
            # comms_learning_loop.py) heartbeated the same way.
            try:
                from core.platform.heartbeat import record_heartbeat
                record_heartbeat("decisions", status="ok", detail=f"source=build-learning-loop event_type={event_type}")
            except Exception:
                pass
        else:
            log.warning("[build-learning-loop] decision_records write failed: %s", dr_result.error)

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
                "evaluation_date": datetime.now(timezone.utc).isoformat(),
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

                    if _SHADOW_SCORE_OUTPUT_ENABLED:
                        threading.Thread(
                            target=_shadow_score_output,
                            args=(mission_title, event_type, memory_text, notes),
                            daemon=True,
                        ).start()
            else:
                log.warning("[build-learning-loop] decision_outcomes write failed: %s", outcome_result.error)
    except Exception as exc:
        log.warning("[build-learning-loop] decision/outcome chain write failed: %s", exc)
