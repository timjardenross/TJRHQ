#!/usr/bin/env python3
"""
MSN-0060B: Learning Loop Service
Phase B1A - Decision Capture Foundation

Implements decision logging, outcome tracking, and quality scoring.

Architecture:
- Backend-only access (SERVICE_ROLE_KEY via CommanderSupabaseClient)
- Incremental implementation: B1A → B1B → B1C → B1D → B1E → B1F
- Non-blocking (failures don't crash workflow; logged for audit)
- Evidence-based (all decisions logged with rationale)

Phase B1A (THIS MODULE):
- Record human decisions to research recommendations
- Ensure decisions linked to mission and recommendation
- Validate data integrity before storage

Phase B1B (NEXT):
- Capture outcome after decision
- Track outcome status progression

Phase B1C (FUTURE):
- Auto-score quality based on effectiveness
- Generate scoring reason for audit

Phase B1D (FUTURE):
- Integrate with ResearchMemoryRetriever
- Update memory confidence based on outcome

Phase B1E (FUTURE):
- Queue decision for follow-up checks
- Leverage Supabase Cron for daily processing

Phase B1F (FUTURE):
- Aggregate metrics to daily health snapshots
- Enable observability dashboard
"""

import logging
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum

log = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    """Human decision classification."""
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    MODIFIED = "Modified"
    DEFERRED = "Deferred"
    ESCALATED = "Escalated"


@dataclass
class ProviderMetadata:
    """Recommendation provider provenance for analysis."""
    provider_name: Optional[str] = None
    # Examples: "google", "openrouter", "ollama", "anthropic", "openai"

    model_name: Optional[str] = None
    # Examples: "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "mistral-small"

    provider_route: Optional[str] = None
    # Examples: "primary", "fallback", "local_fallback", "consolidation"

    research_execution_id: Optional[str] = None
    # Links decision to specific research execution for full traceability

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "provider_route": self.provider_route,
            "research_execution_id": self.research_execution_id,
        }


@dataclass
class DecisionRecord:
    """Represents a human decision on a research recommendation."""
    id: str
    mission_id: str
    recommendation_id: str
    recommendation_text: str
    human_decision: str
    decision_maker: str
    decision_reason: str
    decision_timestamp: str
    captured_timestamp: str
    metadata: Optional[Dict] = None

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionRecord":
        """Create from database row."""
        return cls(**data)


@dataclass
class DecisionOutcome:
    """Represents the actual outcome of a decision."""
    id: str
    decision_id: str
    outcome_status: str  # "Pending" | "In Progress" | "Completed" | "Failed"
    result_summary: str
    effectiveness_score: Optional[int]  # 1-5 scale
    lessons_learned: Optional[str]
    captured_timestamp: str
    outcome_timestamp: str


class LearningLoopService:
    """Backend service for decision capture and outcome tracking."""

    def __init__(self, supabase_client=None):
        """
        Initialize learning loop service.

        Args:
            supabase_client: CommanderSupabaseClient instance
                            If None, service is disabled (graceful degradation)
        """
        self.supabase = supabase_client
        self.enabled = supabase_client is not None
        log.info(f"LearningLoopService initialized (enabled={self.enabled})")

    def record_decision(
        self,
        mission_id: str,
        recommendation_id: str,
        recommendation_text: str,
        human_decision: str,
        decision_maker: str,
        decision_reason: str = None,
        decision_timestamp: datetime = None,
        provider_metadata: Optional[ProviderMetadata] = None,
    ) -> Optional[DecisionRecord]:
        """
        Record a human decision on a research recommendation.

        Phase B1A requirement: "Decision can be recorded via API"

        Args:
            mission_id: Parent mission ID (e.g., "MSN-0055B")
            recommendation_id: Original recommendation that was decided upon
            recommendation_text: Full text of recommendation (for audit)
            human_decision: Classification: "Accepted", "Rejected", "Modified to X", etc.
            decision_maker: Slack user ID or identifier
            decision_reason: Why was this decision made? (optional, extensible)
            decision_timestamp: When decision was made (default: now)
            provider_metadata: ProviderMetadata for recommendation provenance (optional)
                - provider_name: e.g., "google", "openrouter", "ollama"
                - model_name: e.g., "gemini-3.5-flash-lite"
                - provider_route: e.g., "primary", "fallback"
                - research_execution_id: Links to specific research execution

        Returns:
            DecisionRecord if successful, None if service disabled or error

        Raises:
            ValueError: if required fields missing or invalid
        """
        if not self.enabled:
            log.warning("LearningLoopService disabled; decision not recorded")
            return None

        # Validate required fields
        if not all([mission_id, recommendation_id, human_decision, decision_maker]):
            raise ValueError("Missing required decision fields")

        # Default timestamp to now
        if decision_timestamp is None:
            decision_timestamp = datetime.utcnow()
        elif isinstance(decision_timestamp, str):
            decision_timestamp = datetime.fromisoformat(decision_timestamp)

        # Generate canonical ID
        decision_id = self._generate_decision_id()

        # Prepare metadata (provider provenance + extensible)
        metadata = None
        if provider_metadata is not None:
            metadata = provider_metadata.to_dict()
            log.debug(f"[DECISION] Provider metadata captured: {metadata}")

        # Build record
        decision_data = {
            "id": decision_id,
            "mission_id": mission_id,
            "recommendation_id": recommendation_id,
            "recommendation_text": recommendation_text,
            "human_decision": human_decision,
            "decision_maker": decision_maker,
            "decision_reason": decision_reason or "",
            "decision_timestamp": decision_timestamp.isoformat(),
            "captured_timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }

        try:
            # Insert via Supabase (SERVICE_ROLE_KEY)
            response = self.supabase.insert(
                "decision_records",
                decision_data,
            )
            log.info(f"Decision recorded: {decision_id} for mission {mission_id}")
            if provider_metadata:
                log.info(f"  Provider: {provider_metadata.provider_name} / {provider_metadata.model_name}")
                log.info(f"  Route: {provider_metadata.provider_route}")
            return DecisionRecord.from_dict(decision_data)

        except Exception as e:
            log.error(f"Failed to record decision: {e}", exc_info=True)
            return None

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        """
        Retrieve a previously recorded decision.

        Args:
            decision_id: Canonical decision ID (DEC-REC-YYYYMMDD-HHMMSS)

        Returns:
            DecisionRecord if found, None otherwise
        """
        if not self.enabled:
            return None

        try:
            response = self.supabase.select(
                "decision_records",
                filter_="id.eq." + decision_id,
            )
            if response and len(response) > 0:
                return DecisionRecord.from_dict(response[0])
            return None

        except Exception as e:
            log.error(f"Failed to retrieve decision {decision_id}: {e}", exc_info=True)
            return None

    def get_decisions_for_mission(self, mission_id: str) -> List[DecisionRecord]:
        """
        Retrieve all decisions made for a specific mission.

        Phase B1A requirement: "Decision linked to mission"

        Args:
            mission_id: Parent mission ID

        Returns:
            List of DecisionRecord objects (empty list if none found)
        """
        if not self.enabled:
            return []

        try:
            response = self.supabase.select(
                "decision_records",
                filter_="mission_id.eq." + mission_id,
            )
            return [DecisionRecord.from_dict(r) for r in (response or [])]

        except Exception as e:
            log.error(f"Failed to retrieve decisions for mission {mission_id}: {e}", exc_info=True)
            return []

    def record_outcome(
        self,
        decision_id: str,
        outcome_status: str,
        result_summary: str,
        effectiveness_score: Optional[int] = None,
        lessons_learned: Optional[str] = None,
        outcome_timestamp: datetime = None,
    ) -> Optional[DecisionOutcome]:
        """
        Record the outcome of a decision.

        Phase B1B requirement: "Outcome can be recorded"

        Args:
            decision_id: Parent decision ID
            outcome_status: "Pending" | "In Progress" | "Completed" | "Failed"
            result_summary: What actually happened
            effectiveness_score: 1-5 scale (optional, can be added later)
            lessons_learned: What did we learn? (optional)
            outcome_timestamp: When outcome became known (default: now)

        Returns:
            DecisionOutcome if successful, None if error
        """
        if not self.enabled:
            log.warning("LearningLoopService disabled; outcome not recorded")
            return None

        # Validate required fields
        if not all([decision_id, outcome_status, result_summary]):
            raise ValueError("Missing required outcome fields")

        if outcome_status not in ["Pending", "In Progress", "Completed", "Failed"]:
            raise ValueError(f"Invalid outcome_status: {outcome_status}")

        if effectiveness_score is not None:
            if not 1 <= effectiveness_score <= 5:
                raise ValueError("effectiveness_score must be 1-5 or None")

        # Default timestamp
        if outcome_timestamp is None:
            outcome_timestamp = datetime.utcnow()
        elif isinstance(outcome_timestamp, str):
            outcome_timestamp = datetime.fromisoformat(outcome_timestamp)

        # Generate canonical ID
        outcome_id = self._generate_outcome_id()

        # Schedule follow-up (Phase B1E)
        followup_scheduled = None
        if outcome_status in ["Pending", "In Progress"]:
            # Default: check again in 7 days
            followup_scheduled = (datetime.utcnow() + timedelta(days=7)).isoformat()

        # Build record
        outcome_data = {
            "id": outcome_id,
            "decision_id": decision_id,
            "outcome_status": outcome_status,
            "result_summary": result_summary,
            "effectiveness_score": effectiveness_score,
            "lessons_learned": lessons_learned or "",
            "captured_timestamp": datetime.utcnow().isoformat(),
            "outcome_timestamp": outcome_timestamp.isoformat(),
            "followup_scheduled_for": followup_scheduled,
            "quality_score": None,  # Will be filled by quality_scoring.py
            "scoring_reason": None,
            "memory_feedback_applied": False,
        }

        try:
            # Insert via Supabase
            response = self.supabase.insert(
                "decision_outcomes",
                outcome_data,
            )
            log.info(f"Outcome recorded: {outcome_id} for decision {decision_id}")

            # Enqueue for follow-up if needed (Phase B1E)
            if outcome_status in ["Pending", "In Progress"]:
                self._enqueue_followup(decision_id, followup_scheduled)

            return DecisionOutcome(**outcome_data)

        except Exception as e:
            log.error(f"Failed to record outcome: {e}", exc_info=True)
            return None

    def get_outcome(self, outcome_id: str) -> Optional[DecisionOutcome]:
        """Retrieve a previously recorded outcome."""
        if not self.enabled:
            return None

        try:
            response = self.supabase.select(
                "decision_outcomes",
                filter_="id.eq." + outcome_id,
            )
            if response and len(response) > 0:
                return DecisionOutcome(**response[0])
            return None

        except Exception as e:
            log.error(f"Failed to retrieve outcome {outcome_id}: {e}", exc_info=True)
            return None

    def get_pending_decisions(self) -> List[str]:
        """
        Get all decisions awaiting outcome.

        Phase B1E: Used by cron job to identify what needs follow-up.

        Returns:
            List of decision IDs that have no outcome or incomplete outcome
        """
        if not self.enabled:
            return []

        try:
            # Query: decisions without outcome or incomplete outcome
            query = """
                SELECT dr.id
                FROM decision_records dr
                LEFT JOIN decision_outcomes do ON dr.id = do.decision_id
                WHERE do.id IS NULL
                   OR do.outcome_status IN ('Pending', 'In Progress')
                LIMIT 100
            """
            response = self.supabase.query(query)
            return [r["id"] for r in (response or [])]

        except Exception as e:
            log.error(f"Failed to get pending decisions: {e}", exc_info=True)
            return []

    def _generate_decision_id(self) -> str:
        """Generate canonical decision ID: DEC-REC-YYYYMMDD-HHMMSS"""
        now = datetime.utcnow()
        return f"DEC-REC-{now.strftime('%Y%m%d-%H%M%S')}"

    def _generate_outcome_id(self) -> str:
        """Generate canonical outcome ID: OUT-YYYYMMDD-HHMMSS"""
        now = datetime.utcnow()
        return f"OUT-{now.strftime('%Y%m%d-%H%M%S')}"

    def _enqueue_followup(self, decision_id: str, scheduled_for: str) -> bool:
        """
        Phase B1E: Enqueue decision for followup.

        Args:
            decision_id: Decision to follow up on
            scheduled_for: ISO timestamp for when to check

        Returns:
            True if enqueued, False if error
        """
        if not self.enabled:
            return False

        try:
            followup_data = {
                "decision_id": decision_id,
                "check_at": scheduled_for,
                "reminder_level": "reminder_week1",
                "status": "enqueued",
            }
            self.supabase.insert("decision_followup_queue", followup_data)
            log.info(f"Decision {decision_id} enqueued for followup on {scheduled_for}")
            return True

        except Exception as e:
            log.warning(f"Failed to enqueue followup for {decision_id}: {e}")
            return False


# =============================================================================
# INTEGRATION POINT: Research Command Handler
# =============================================================================
# Example usage in slack-bot/commands/research_command.py:
#
# def handle_research_response(mission_id, recommendation, user_id):
#     """After research completes and recommendation is sent to user."""
#     from slack_bot.lib.learning_loop_service import LearningLoopService
#     from tools.supabase.client import CommanderSupabaseClient
#
#     # Initialize service with backend client
#     client = CommanderSupabaseClient()
#     learning_loop = LearningLoopService(supabase_client=client)
#
#     # Wait for user decision (Slack modal or command)
#     # Then record decision:
#     decision = learning_loop.record_decision(
#         mission_id=mission_id,
#         recommendation_id=recommendation.id,
#         recommendation_text=recommendation.text,
#         human_decision="Accepted",  # From user action
#         decision_maker=user_id,
#         decision_reason="User confirmed recommendation via Slack",
#     )
#
#     # Later, when outcome becomes known:
#     outcome = learning_loop.record_outcome(
#         decision_id=decision.id,
#         outcome_status="Completed",
#         result_summary="Vendor evaluation completed; selected Vendor X",
#         effectiveness_score=5,
#         lessons_learned="Fast vendor comparison; good due diligence"
#     )
#
#     # Quality scoring (Phase B1C) happens automatically via quality_scoring.py
#     # Memory feedback (Phase B1D) happens automatically via memory_feedback.py

log.info("LearningLoopService module loaded")
