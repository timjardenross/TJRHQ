"""Wires completed research missions into the MSN-0060B learning loop.

Correct chain, verified against the LIVE Supabase schema (2026-07-05) rather
than the design docs, which had drifted from what's actually deployed:

  commander_decisions (uuid id, self-generated)
    -> decision_outcomes (decision_id = that uuid; own quality/clarity/
       timeliness/accuracy/actionability columns, left null here since
       research only has one overall confidence, not sub-scores)
  decision_records (independent text id)
    -> quality_scores (outcome_id = decision_outcomes' bigint id,
       decision_id = decision_records' text id, via QualityScoring,
       which needs the RAW supabase-py client, not the CommanderSupabaseClient
       wrapper — see tools/supabase/client.py's insert()/raw_client).

decision_outcomes.decision_id FKs to commander_decisions.id, NOT
decision_records.id, despite every design doc (including the original
build_learning_loop.py this was modelled on) assuming otherwise — see
reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md for the audit
trail on this discovery.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from tools.supabase.client import CommanderSupabaseClient
from lib.feedback_loops_service import FeedbackLoops
from lib.quality_scoring_service import QualityScoring

# Ensure repo root is importable so core.platform.event_bus resolves from any
# working directory this module is invoked from (e.g. slack-bot/, platform-runtime/).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

_STATUS_TO_OUTCOME = {
    "success": "Implemented",
    "partial": "Modified",
    "error": "Rejected",
}


def generate_research_decision_id() -> str:
    return f"DEC-RES-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"


def record_research_lifecycle_event(
    *,
    mission_id: str,
    research_topic: str,
    recommendation: str,
    confidence: float,
    status: str,
    provider_path: list[str] | None,
    user_id: str | None,
) -> None:
    """Record a research mission's decision/outcome and trigger quality scoring.

    Non-blocking: every step is wrapped so a failure here never affects the
    research result already returned to the caller.
    """
    outcome_status = _STATUS_TO_OUTCOME.get(status, "Unknown")  # for quality_scores/decision_records
    # decision_outcomes.outcome_status has its own CHECK constraint: only
    # 'success'/'partial'/'failed' (a third, separate vocabulary — verified
    # against the live schema; do not reuse the OutcomeStatus enum here).
    decision_outcomes_status = status if status in ("success", "partial") else "failed"
    provider_name = (provider_path or [None])[0]
    notes = (recommendation or research_topic)[:500]
    captured_at = datetime.utcnow().isoformat()

    try:
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[research-learning-loop] Supabase disabled; skipping")
            return

        # 1. commander_decisions — self-generated uuid so we can reference it
        #    immediately without depending on a returning-row round trip.
        commander_decision_id = str(uuid4())
        cd_result = client.insert(
            "commander_decisions",
            {
                "id": commander_decision_id,
                "decision_title": f"Research: {research_topic[:200]}",
                "decision_summary": notes,
                "source": "research-learning-loop",
                "user_id": user_id or "research-orchestrator",
                "route": "/research",
                "confidence": confidence,
                "status": outcome_status,
                "metadata": {"mission_id": mission_id, "provider_path": provider_path or []},
            },
        )
        if not cd_result.ok:
            log.warning("[research-learning-loop] commander_decisions write failed: %s", cd_result.error)
            return

        # 2. decision_outcomes — FKs to commander_decisions, not decision_records.
        do_result = client.insert(
            "decision_outcomes",
            {
                "decision_id": commander_decision_id,
                "mission_id": mission_id,
                "outcome_status": decision_outcomes_status,
                "outcome_notes": notes,
                "evaluation_date": captured_at,
                "evaluator": "research-orchestrator",
            },
            returning=True,
        )
        if not do_result.ok or not do_result.data:
            log.warning("[research-learning-loop] decision_outcomes write failed: %s", do_result.error)
            return
        outcome_bigint_id = do_result.data[0].get("id")

        # 3. decision_records — independent of commander_decisions/decision_outcomes;
        #    exists so quality_scores (which FKs to it separately) has a parent.
        decision_id = generate_research_decision_id()
        dr_result = client.insert(
            "decision_records",
            {
                "id": decision_id,
                "mission_id": mission_id,
                "recommendation_id": mission_id,
                "recommendation_text": notes,
                "human_decision": outcome_status,
                "decision_maker": user_id or "research-orchestrator",
                "decision_reason": f"Research mission confidence={confidence}",
                "decision_timestamp": captured_at,
                "captured_timestamp": captured_at,
                "metadata": {
                    "source": "research-learning-loop",
                    "research_topic": research_topic,
                    "confidence": confidence,
                    "provider_path": provider_path or [],
                },
            },
        )
        if not dr_result.ok:
            log.warning("[research-learning-loop] decision_records write failed: %s", dr_result.error)
            return

        # Chief Engineer 2026-08-10 decisions-heartbeat follow-up: a real,
        # live-wired decision_records writer (called from
        # commands/research_command.py's handle_research_request_with_slack),
        # heartbeated alongside build_learning_loop.py and
        # comms_learning_loop.py — all three are genuinely distinct event
        # producers into the same 'decisions' domain, not competing
        # candidates for one canonical path.
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat("decisions", status="ok", detail="source=research-learning-loop")
        except Exception:
            pass

        # Emit research-learning after all three DB writes succeed (commander_decisions,
        # decision_outcomes, decision_records). This is the authoritative moment a
        # research session is recorded into the learning loop. Fires even when quality
        # scoring is skipped (e.g. no raw client). Non-blocking per publish_event contract.
        try:
            from core.platform.event_bus import publish_event
            publish_event(
                "research.session.completed",
                domain="research-learning",
                source="research-learning-loop",
                confidence=round(confidence * 100),
                linked_missions=[mission_id],
                metrics={
                    "status": status,
                    "outcome_status": outcome_status,
                    "provider_name": provider_name,
                    "research_topic_length": len(research_topic),
                },
            )
        except Exception:
            pass

        # 4. quality_scores — ties decision_outcomes + decision_records together.
        # QualityScoring/FeedbackLoops need the raw supabase-py client (they call
        # .table() directly), not the CommanderSupabaseClient wrapper.
        raw = client.raw_client
        if raw is None or outcome_bigint_id is None:
            log.info("[research-learning-loop] Skipping quality score (no raw client or outcome id)")
            return
        try:
            quality_scoring = QualityScoring(raw)
            feedback_loops = FeedbackLoops(raw)
            quality_scoring.score_outcome(
                outcome_id=outcome_bigint_id,
                decision_id=decision_id,
                outcome_status=outcome_status,
                implementation_notes=notes,
                provider_name=provider_name,
                model_name=None,
                provider_route="research",
                feedback_loops=feedback_loops,
            )
            log.info(
                "[research-learning-loop] Scored: mission_id=%s outcome_id=%s decision_id=%s",
                mission_id, outcome_bigint_id, decision_id,
            )
        except Exception as exc:
            log.warning("[research-learning-loop] scoring/feedback skipped: %s", exc)

        # Emit research-learning-intelligence after quality scoring — this is when
        # the platform has a scored, consolidated learning record, not just a raw
        # session write. Scoped inside the raw-client guard so it only fires when
        # quality scoring was at least attempted. Non-blocking per publish_event contract.
        try:
            from core.platform.event_bus import publish_event
            publish_event(
                "research.learning.consolidated",
                domain="research-learning-intelligence",
                source="research-learning-loop",
                confidence=round(confidence * 100),
                linked_missions=[mission_id],
                metrics={
                    "outcome_id": outcome_bigint_id,
                    "decision_id": decision_id,
                    "outcome_status": outcome_status,
                    "provider_name": provider_name,
                },
            )
        except Exception:
            pass

    except Exception as exc:
        log.warning("[research-learning-loop] decision/outcome chain write failed: %s", exc)
