"""Wires Captain-approved content pipeline transitions into the learning loop.

Correct chain against the LIVE Supabase schema (2026-07-05) — see
lib/research_learning_loop.py's module docstring for the full explanation of
why this needs commander_decisions -> decision_outcomes as one chain and
decision_records -> quality_scores as a second, independent one. Only fires
on CAPTAIN_ONLY_TRIGGERS transitions (comms/pipeline.py) — those are genuine
human accept decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

log = logging.getLogger(__name__)


def generate_comms_decision_id() -> str:
    return f"DEC-COM-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"


def record_comms_approval_event(
    *,
    content_id: str,
    title: str,
    trigger: str,
    old_state: str,
    new_state: str,
    actor: str,
) -> None:
    """Record a Captain approval decision/outcome and trigger quality scoring.

    Non-blocking: never raises, never affects the pipeline transition that
    already succeeded before this is called.
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient
        from lib.feedback_loops_service import FeedbackLoops
        from lib.quality_scoring_service import QualityScoring
    except ImportError as exc:
        log.warning("[comms-learning-loop] Unavailable (missing dependency: %s) — skipped", exc)
        return

    notes = f"Content '{title}' advanced {old_state} -> {new_state}"
    captured_at = datetime.utcnow().isoformat()

    try:
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[comms-learning-loop] Supabase disabled; skipping")
            return

        # 1. commander_decisions
        commander_decision_id = str(uuid4())
        cd_result = client.insert(
            "commander_decisions",
            {
                "id": commander_decision_id,
                "decision_title": f"Content approval: {title[:200]}",
                "decision_summary": notes,
                "source": "comms-learning-loop",
                "user_id": actor,
                "route": "/comms",
                "confidence": 1.0,
                "status": "Implemented",
                "metadata": {"content_id": content_id, "trigger": trigger},
            },
        )
        if not cd_result.ok:
            log.warning("[comms-learning-loop] commander_decisions write failed: %s", cd_result.error)
            return

        # 2. decision_outcomes — FKs to commander_decisions, not decision_records.
        # outcome_status here is CHECK-constrained to success/partial/failed,
        # a different vocabulary than quality_scores' Implemented/Modified/etc.
        do_result = client.insert(
            "decision_outcomes",
            {
                "decision_id": commander_decision_id,
                "mission_id": content_id,
                "outcome_status": "success",
                "outcome_notes": notes,
                "evaluation_date": captured_at,
                "evaluator": actor,
            },
            returning=True,
        )
        if not do_result.ok or not do_result.data:
            log.warning("[comms-learning-loop] decision_outcomes write failed: %s", do_result.error)
            return
        outcome_bigint_id = do_result.data[0].get("id")

        # 3. decision_records — independent parent for quality_scores.
        decision_id = generate_comms_decision_id()
        dr_result = client.insert(
            "decision_records",
            {
                "id": decision_id,
                "mission_id": content_id,
                "recommendation_id": content_id,
                "recommendation_text": f"Content '{title}' at stage '{old_state}'",
                "human_decision": "Accepted",
                "decision_maker": actor,
                "decision_reason": f"Captain trigger '{trigger}': {old_state} -> {new_state}",
                "decision_timestamp": captured_at,
                "captured_timestamp": captured_at,
                "metadata": {
                    "source": "comms-learning-loop",
                    "content_id": content_id,
                    "trigger": trigger,
                    "old_state": old_state,
                    "new_state": new_state,
                },
            },
        )
        if not dr_result.ok:
            log.warning("[comms-learning-loop] decision_records write failed: %s", dr_result.error)
            return

        # Chief Engineer 2026-08-10 decisions-heartbeat follow-up: a real,
        # live-wired decision_records writer (called from
        # lib/comms/pipeline.py's advance() on CAPTAIN_ONLY_TRIGGERS),
        # heartbeated alongside build_learning_loop.py and
        # research_learning_loop.py — all three are genuinely distinct event
        # producers into the same 'decisions' domain, not competing
        # candidates for one canonical path.
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat("decisions", status="ok", detail="source=comms-learning-loop")
        except Exception:
            pass

        # 4. quality_scores — needs the RAW supabase-py client, not the wrapper.
        raw = client.raw_client
        if raw is None or outcome_bigint_id is None:
            log.info("[comms-learning-loop] Skipping quality score (no raw client or outcome id)")
            return
        try:
            quality_scoring = QualityScoring(raw)
            feedback_loops = FeedbackLoops(raw)
            quality_scoring.score_outcome(
                outcome_id=outcome_bigint_id,
                decision_id=decision_id,
                outcome_status="Implemented",
                implementation_notes=notes,
                provider_name=None,
                model_name=None,
                provider_route="comms",
                feedback_loops=feedback_loops,
            )
            log.info(
                "[comms-learning-loop] Scored: content_id=%s outcome_id=%s decision_id=%s",
                content_id, outcome_bigint_id, decision_id,
            )
        except Exception as exc:
            log.warning("[comms-learning-loop] scoring/feedback skipped: %s", exc)

    except Exception as exc:
        log.warning("[comms-learning-loop] decision/outcome chain write failed: %s", exc)
