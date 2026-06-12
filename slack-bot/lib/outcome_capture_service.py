#!/usr/bin/env python3
"""
MSN-0060B Phase B1B: Outcome Capture Service

Records what actually happened after decisions were made.
Links outcomes back to decision_records for complete traceability.

Design: Minimal MVP
- Records outcome status and implementation notes
- Defers effectiveness scoring to B1C Quality Scoring phase
- Maintains decision_records foreign key for traceability
- Enables E2E chain: Research → Recommendation → Decision → Outcome

Authority Model:
- Captain/XO can record outcomes for decisions
- All execution is advisory-only (non-binding)
- Outcome recording is idempotent (can update notes)

Public API:
    outcome_capture = OutcomeCapture(supabase_client)
    outcome = outcome_capture.record_outcome(decision_id, status, notes)
    outcome = outcome_capture.get_outcome(outcome_id)
    outcomes = outcome_capture.get_outcomes_for_decision(decision_id)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any
from enum import Enum

log = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class OutcomeStatus(Enum):
    """Outcome status values."""
    IMPLEMENTED = "Implemented"  # Done as decided
    MODIFIED = "Modified"         # Done differently
    DEFERRED = "Deferred"         # Postponed
    REJECTED = "Rejected"         # Not done
    UNKNOWN = "Unknown"           # Unclear status

    @classmethod
    def valid_values(cls) -> list[str]:
        """Get all valid status values."""
        return [s.value for s in cls]


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DecisionOutcome:
    """
    Outcome of a decision.

    Represents what actually happened after a decision was made.
    Links back to original decision via decision_id.
    """

    # Identity
    id: str  # OUT-YYYYMMDD-HHMMSS
    decision_id: str

    # Outcome details
    outcome_status: str  # Implemented, Modified, Deferred, Rejected, Unknown
    implementation_notes: Optional[str] = None

    # Timestamps
    outcome_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Supabase insert."""
        return {
            "id": self.id,
            "decision_id": self.decision_id,
            "outcome_status": self.outcome_status,
            "implementation_notes": self.implementation_notes,
            "outcome_timestamp": self.outcome_timestamp,
        }


# ============================================================================
# Outcome Capture Service
# ============================================================================

class OutcomeCapture:
    """
    Service for recording and managing decision outcomes.

    B1B Phase: Records what actually happened after decisions.
    Enables complete E2E traceability chain.
    """

    def __init__(self, supabase_client=None):
        """
        Initialize outcome capture service.

        Args:
            supabase_client: Supabase client (optional, can be set later)
        """
        self.supabase_client = supabase_client
        log.info("[outcome-capture] OutcomeCapture service initialized")

    def record_outcome(
        self,
        decision_id: str,
        status: str,
        implementation_notes: Optional[str] = None,
        outcome_timestamp: Optional[str] = None,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_route: Optional[str] = None,
        quality_scoring_service=None,
        feedback_loops_service=None,
    ) -> Optional[DecisionOutcome]:
        """
        Record outcome for a decision AND trigger quality scoring (B1C→B1D).

        MSN-0060B B1B: Record what actually happened after decision.
        MSN-0060B B1C: Automatically score outcome effectiveness and generate feedback

        Args:
            decision_id: FK to decision_records(id)
            status: Outcome status (Implemented, Modified, Deferred, Rejected, Unknown)
            implementation_notes: What was actually done vs. what was decided
            outcome_timestamp: When outcome occurred (default: now)
            provider_name: (NEW) Provider that made the recommendation
            model_name: (NEW) Model used for recommendation
            provider_route: (NEW) Route taken (Primary, Fallback, etc.)
            quality_scoring_service: (NEW) B1C Quality Scoring service for auto-scoring
            feedback_loops_service: (NEW) B1D Feedback Loops for auto-feedback

        Returns:
            DecisionOutcome if successful, None if error

        Raises:
            ValueError: If status invalid or decision_id invalid
        """

        # Validate status
        if status not in OutcomeStatus.valid_values():
            valid = ", ".join(OutcomeStatus.valid_values())
            raise ValueError(f"Invalid outcome status: {status}. Valid: {valid}")

        # Validate decision_id
        if not decision_id or not isinstance(decision_id, str):
            raise ValueError(f"Invalid decision_id: {decision_id}")

        # Generate outcome ID
        outcome_id = self._generate_outcome_id()

        # Use provided timestamp or current time
        if outcome_timestamp is None:
            outcome_timestamp = datetime.utcnow().isoformat()

        # Create outcome record
        outcome = DecisionOutcome(
            id=outcome_id,
            decision_id=decision_id,
            outcome_status=status,
            implementation_notes=implementation_notes,
            outcome_timestamp=outcome_timestamp,
        )

        # Persist if client available
        if self.supabase_client:
            try:
                response = (
                    self.supabase_client.table("decision_outcomes")
                    .insert(outcome.to_dict())
                    .execute()
                )

                log.info(
                    f"[outcome-capture] Outcome recorded: outcome_id={outcome_id}, "
                    f"decision_id={decision_id}, status={status}"
                )

                # ================================================================
                # MSN-0060B B1C→B1D: Auto-score outcome and generate feedback
                # ================================================================
                if quality_scoring_service and outcome_id:
                    try:
                        quality_score = quality_scoring_service.score_outcome(
                            outcome_id=outcome_id,
                            decision_id=decision_id,
                            outcome_status=status,
                            provider_name=provider_name,
                            model_name=model_name,
                            provider_route=provider_route,
                            feedback_loops=feedback_loops_service,
                        )

                        if quality_score:
                            log.info(
                                f"[outcome-capture→b1c] Quality scored: {quality_score.effectiveness_score} "
                                f"(feedback signal generated: {quality_score.id})"
                            )
                        else:
                            log.warning(f"[outcome-capture→b1c] Quality scoring returned None")

                    except Exception as e:
                        log.error(
                            f"[outcome-capture→b1c] Quality scoring failed: "
                            f"{type(e).__name__}: {str(e)[:100]}"
                        )
                        # Non-blocking; outcome still recorded even if scoring fails

                return outcome

            except Exception as e:
                log.error(
                    f"[outcome-capture] Failed to record outcome: {type(e).__name__}: {str(e)[:100]}"
                )
                return None
        else:
            log.debug(
                f"[outcome-capture] Outcome created (not persisted): outcome_id={outcome_id}"
            )
            return outcome

    def get_outcome(self, outcome_id: str) -> Optional[DecisionOutcome]:
        """
        Retrieve outcome by ID.

        Args:
            outcome_id: Outcome ID (OUT-YYYYMMDD-HHMMSS)

        Returns:
            DecisionOutcome if found, None otherwise
        """

        if not self.supabase_client:
            log.error("[outcome-capture] Supabase client not configured")
            return None

        try:
            response = (
                self.supabase_client.table("decision_outcomes")
                .select("*")
                .eq("id", outcome_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                data = response.data[0]
                return DecisionOutcome(
                    id=data["id"],
                    decision_id=data["decision_id"],
                    outcome_status=data["outcome_status"],
                    implementation_notes=data.get("implementation_notes"),
                    outcome_timestamp=data["outcome_timestamp"],
                    created_at=data.get("created_at"),
                )
            else:
                log.debug(f"[outcome-capture] Outcome not found: {outcome_id}")
                return None

        except Exception as e:
            log.error(
                f"[outcome-capture] Failed to retrieve outcome: {type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def get_outcomes_for_decision(self, decision_id: str) -> list[DecisionOutcome]:
        """
        Get all outcomes for a decision.

        Enables traceability: Decision → Outcomes

        Args:
            decision_id: Decision ID (DEC-REC-YYYYMMDD-HHMMSS)

        Returns:
            List of DecisionOutcome records (empty if none found)
        """

        if not self.supabase_client:
            log.error("[outcome-capture] Supabase client not configured")
            return []

        try:
            response = (
                self.supabase_client.table("decision_outcomes")
                .select("*")
                .eq("decision_id", decision_id)
                .order("outcome_timestamp", desc=True)
                .execute()
            )

            outcomes = []
            for data in response.data or []:
                outcome = DecisionOutcome(
                    id=data["id"],
                    decision_id=data["decision_id"],
                    outcome_status=data["outcome_status"],
                    implementation_notes=data.get("implementation_notes"),
                    outcome_timestamp=data["outcome_timestamp"],
                    created_at=data.get("created_at"),
                )
                outcomes.append(outcome)

            log.debug(
                f"[outcome-capture] Retrieved {len(outcomes)} outcomes for decision: {decision_id}"
            )
            return outcomes

        except Exception as e:
            log.error(
                f"[outcome-capture] Failed to retrieve outcomes: {type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def get_outcomes_by_status(self, status: str) -> list[DecisionOutcome]:
        """
        Get all outcomes with specific status.

        Args:
            status: Outcome status (Implemented, Modified, Deferred, Rejected, Unknown)

        Returns:
            List of matching DecisionOutcome records
        """

        if status not in OutcomeStatus.valid_values():
            log.error(f"[outcome-capture] Invalid status: {status}")
            return []

        if not self.supabase_client:
            log.error("[outcome-capture] Supabase client not configured")
            return []

        try:
            response = (
                self.supabase_client.table("decision_outcomes")
                .select("*")
                .eq("outcome_status", status)
                .order("outcome_timestamp", desc=True)
                .execute()
            )

            outcomes = []
            for data in response.data or []:
                outcome = DecisionOutcome(
                    id=data["id"],
                    decision_id=data["decision_id"],
                    outcome_status=data["outcome_status"],
                    implementation_notes=data.get("implementation_notes"),
                    outcome_timestamp=data["outcome_timestamp"],
                    created_at=data.get("created_at"),
                )
                outcomes.append(outcome)

            log.debug(
                f"[outcome-capture] Retrieved {len(outcomes)} outcomes with status: {status}"
            )
            return outcomes

        except Exception as e:
            log.error(
                f"[outcome-capture] Failed to retrieve outcomes by status: {type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def _generate_outcome_id(self) -> str:
        """
        Generate canonical outcome ID: OUT-YYYYMMDD-HHMMSS.

        Format: OUT-YYYYMMDD-HHMMSS
        Example: OUT-20260610-143000

        Returns:
            Unique, sortable outcome ID
        """
        now = datetime.utcnow()
        return now.strftime("OUT-%Y%m%d-%H%M%S")
