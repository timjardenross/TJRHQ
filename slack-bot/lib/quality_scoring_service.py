#!/usr/bin/env python3
"""
MSN-0060B Phase B1C: Quality Scoring Service

Scores decision outcomes for effectiveness (1-5 scale).
Links outcomes to quality scores for analysis.

Design: Minimal MVP
- Scores outcome effectiveness (1-5 scale)
- Generates scoring reasons
- Captures provider/model/route attribution
- Enables provider quality analysis

Authority Model:
- Backend service scores outcomes
- All scoring advisory (non-binding)
- Scores based on outcome status only
- Extensible for B1D feedback loops

Public API:
    quality_scoring = QualityScoring(supabase_client)
    quality_score = quality_scoring.score_outcome(outcome_id, status, notes)
    provider_stats = quality_scoring.get_provider_quality()
    model_stats = quality_scoring.get_model_quality()
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

class EffectivenessScore(Enum):
    """Effectiveness score values (1.0 - 5.0)."""
    INEFFECTIVE = 1.0          # Rejected/not executed
    BELOW_EXPECTED = 2.0       # Deferred indefinitely
    FAIR = 3.0                 # Modified, deferred temporarily
    ACCEPTABLE = 3.5           # Modified beneficially
    GOOD = 4.0                 # Implemented with modifications
    EXCELLENT = 5.0            # Implemented as planned
    PENDING = None             # Unknown status


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class QualityScore:
    """
    Quality score for a decision outcome.

    Represents effectiveness assessment of a decision based on actual outcome.
    Links back to original decision and outcome for traceability.
    """

    # Identity
    id: str  # SCO-YYYYMMDD-HHMMSS
    outcome_id: str
    decision_id: str

    # Scoring
    effectiveness_score: Optional[float]  # 1.0 - 5.0
    scoring_reason: str

    # Attribution
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    provider_route: Optional[str] = None

    # Timestamps
    scored_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Supabase insert."""
        return {
            "id": self.id,
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "effectiveness_score": self.effectiveness_score,
            "scoring_reason": self.scoring_reason,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "provider_route": self.provider_route,
            "scored_at": self.scored_at,
        }


@dataclass
class ProviderQuality:
    """Provider quality summary."""
    provider_name: str
    scored_decisions: int
    avg_score: float
    min_score: float
    max_score: float
    score_variance: float


@dataclass
class ModelQuality:
    """Model quality summary."""
    model_name: str
    provider_name: str
    scored_decisions: int
    avg_score: float
    min_score: float
    max_score: float


@dataclass
class RouteQuality:
    """Routing effectiveness summary."""
    provider_route: str
    decisions: int
    avg_score: float
    high_quality_count: int
    low_quality_count: int


# ============================================================================
# Quality Scoring Service
# ============================================================================

class QualityScoring:
    """
    Service for scoring decision outcomes for effectiveness.

    B1C Phase: Scores what actually happened after decisions.
    Enables quality analysis by provider, model, and routing strategy.
    """

    def __init__(self, supabase_client=None):
        """
        Initialize quality scoring service.

        Args:
            supabase_client: Supabase client (optional, can be set later)
        """
        self.supabase_client = supabase_client
        log.info("[quality-scoring] QualityScoring service initialized")

    def score_outcome(
        self,
        outcome_id: str,
        decision_id: str,
        outcome_status: str,
        implementation_notes: Optional[str] = None,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_route: Optional[str] = None,
        scored_at: Optional[str] = None,
<<<<<<< Updated upstream
=======
        feedback_loops=None,
>>>>>>> Stashed changes
    ) -> Optional[QualityScore]:
        """
        Score outcome for effectiveness.

        MSN-0060B B1C: Score what actually happened after decision.
<<<<<<< Updated upstream
=======
        MSN-0060B B1D: Automatically generate feedback signal from score.
>>>>>>> Stashed changes

        Args:
            outcome_id: FK to decision_outcomes(id)
            decision_id: FK to decision_records(id)
            outcome_status: Outcome status (Implemented, Modified, Deferred, Rejected, Unknown)
            implementation_notes: Notes on what was actually done
            provider_name: AI provider (Google, OpenRouter, Ollama)
            model_name: Model used (Gemini, Mistral, Qwen)
            provider_route: Routing strategy (Primary, Fallback, Local)
            scored_at: When scored (default: now)
<<<<<<< Updated upstream
=======
            feedback_loops: Optional FeedbackLoops service for B1D integration
>>>>>>> Stashed changes

        Returns:
            QualityScore if successful, None if error
        """

        # Calculate score
        score = self._calculate_score(outcome_status, implementation_notes)

        # Generate reason
        reason = self._generate_reason(score, outcome_status)

        # Generate score ID
        score_id = self._generate_score_id()

        # Use provided timestamp or current time
        if scored_at is None:
            scored_at = datetime.utcnow().isoformat()

        # Create quality score record
        quality_score = QualityScore(
            id=score_id,
            outcome_id=outcome_id,
            decision_id=decision_id,
            effectiveness_score=score,
            scoring_reason=reason,
            provider_name=provider_name,
            model_name=model_name,
            provider_route=provider_route,
            scored_at=scored_at,
        )

        # Persist if client available
        if self.supabase_client:
            try:
                response = (
                    self.supabase_client.table("quality_scores")
                    .insert(quality_score.to_dict())
                    .execute()
                )

                log.info(
                    f"[quality-scoring] Outcome scored: score_id={score_id}, "
                    f"outcome_id={outcome_id}, effectiveness={score}"
                )
<<<<<<< Updated upstream
=======

                # ====================================================================
                # B1D INTEGRATION: Generate feedback signal from quality score
                # ====================================================================
                if feedback_loops and score is not None:
                    try:
                        signal = feedback_loops.generate_feedback(
                            score_id=score_id,
                            decision_id=decision_id,
                            provider_name=provider_name,
                            effectiveness_score=score,
                            model_name=model_name,
                            provider_route=provider_route
                        )

                        if signal:
                            log.info(
                                f"[quality-scoring→b1d] Feedback signal generated: "
                                f"signal_id={signal.id}, action={signal.suggested_action}, "
                                f"delta={signal.effectiveness_delta:+.1f}"
                            )
                        else:
                            log.debug(
                                f"[quality-scoring→b1d] No feedback signal (no delta or error)"
                            )

                    except Exception as e:
                        log.error(
                            f"[quality-scoring→b1d] Error generating feedback: "
                            f"{type(e).__name__}: {str(e)[:100]}"
                        )
                        # Don't block quality scoring if feedback fails (non-critical)

                elif not feedback_loops and score is not None:
                    log.debug(
                        f"[quality-scoring→b1d] Feedback loops not configured, "
                        f"skipping B1D integration"
                    )

>>>>>>> Stashed changes
                return quality_score

            except Exception as e:
                log.error(
                    f"[quality-scoring] Failed to score outcome: {type(e).__name__}: {str(e)[:100]}"
                )
                return None
        else:
            log.debug(f"[quality-scoring] Outcome scored (not persisted): {score_id}")
            return quality_score

    def get_provider_quality(self) -> list[ProviderQuality]:
        """
        Get provider quality summary.

        Returns statistics on provider effectiveness.

        Returns:
            List of ProviderQuality records, ordered by avg_score DESC
        """

        if not self.supabase_client:
            log.error("[quality-scoring] Supabase client not configured")
            return []

        try:
            response = (
                self.supabase_client.table("v_provider_quality")
                .select("*")
                .order("avg_score", desc=True)
                .execute()
            )

            qualities = []
            for data in response.data or []:
                quality = ProviderQuality(
                    provider_name=data.get("provider_name"),
                    scored_decisions=data.get("scored_decisions", 0),
                    avg_score=float(data.get("avg_score", 0)),
                    min_score=float(data.get("min_score", 0)),
                    max_score=float(data.get("max_score", 0)),
                    score_variance=float(data.get("score_variance", 0)),
                )
                qualities.append(quality)

            log.debug(
                f"[quality-scoring] Retrieved quality for {len(qualities)} providers"
            )
            return qualities

        except Exception as e:
            log.error(
                f"[quality-scoring] Failed to retrieve provider quality: {type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def get_model_quality(self) -> list[ModelQuality]:
        """
        Get model quality summary.

        Returns statistics on model effectiveness by provider.

        Returns:
            List of ModelQuality records, ordered by avg_score DESC
        """

        if not self.supabase_client:
            log.error("[quality-scoring] Supabase client not configured")
            return []

        try:
            response = (
                self.supabase_client.table("v_model_quality")
                .select("*")
                .order("avg_score", desc=True)
                .execute()
            )

            qualities = []
            for data in response.data or []:
                quality = ModelQuality(
                    model_name=data.get("model_name"),
                    provider_name=data.get("provider_name"),
                    scored_decisions=data.get("scored_decisions", 0),
                    avg_score=float(data.get("avg_score", 0)),
                    min_score=float(data.get("min_score", 0)),
                    max_score=float(data.get("max_score", 0)),
                )
                qualities.append(quality)

            log.debug(f"[quality-scoring] Retrieved quality for {len(qualities)} models")
            return qualities

        except Exception as e:
            log.error(
                f"[quality-scoring] Failed to retrieve model quality: {type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def get_route_quality(self) -> list[RouteQuality]:
        """
        Get routing strategy quality summary.

        Returns effectiveness of each routing strategy.

        Returns:
            List of RouteQuality records, ordered by avg_score DESC
        """

        if not self.supabase_client:
            log.error("[quality-scoring] Supabase client not configured")
            return []

        try:
            response = (
                self.supabase_client.table("v_route_quality")
                .select("*")
                .order("avg_score", desc=True)
                .execute()
            )

            qualities = []
            for data in response.data or []:
                quality = RouteQuality(
                    provider_route=data.get("provider_route"),
                    decisions=data.get("decisions", 0),
                    avg_score=float(data.get("avg_score", 0)),
                    high_quality_count=data.get("high_quality_count", 0),
                    low_quality_count=data.get("low_quality_count", 0),
                )
                qualities.append(quality)

            log.debug(f"[quality-scoring] Retrieved quality for {len(qualities)} routes")
            return qualities

        except Exception as e:
            log.error(
                f"[quality-scoring] Failed to retrieve route quality: {type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def _calculate_score(
        self, outcome_status: str, implementation_notes: Optional[str] = None
    ) -> Optional[float]:
        """
        Calculate effectiveness score based on outcome status.

        Scoring algorithm:
        - Implemented (no modifications) = 5.0 (excellent)
        - Implemented (with modifications) = 4.0 (good)
        - Modified (beneficial) = 3.5 (acceptable)
        - Modified (other) = 3.0 (fair)
        - Deferred (temporary) = 3.0 (fair)
        - Deferred (indefinite) = 2.0 (below expected)
        - Rejected = 1.0 (ineffective)
        - Unknown = None (pending)

        Args:
            outcome_status: Outcome status value
            implementation_notes: Optional notes on outcome

        Returns:
            Effectiveness score (1.0-5.0) or None if Unknown/pending
        """

        notes = (implementation_notes or "").lower()

        if outcome_status == "Implemented":
            # Excellent by default, downgrade if modified
            if "modified" in notes or "change" in notes:
                return 4.0  # Good: implemented with modifications
            else:
                return 5.0  # Excellent: implemented as decided

        elif outcome_status == "Modified":
            # Fair/Acceptable based on modification quality
            if "positive" in notes or "better" in notes or "improved" in notes:
                return 3.5  # Acceptable: beneficial modification
            else:
                return 3.0  # Fair: modified but functional

        elif outcome_status == "Deferred":
            # Below expected/Fair based on deferral timeline
            if "temporary" in notes or "short-term" in notes:
                return 3.0  # Fair: temporarily deferred
            else:
                return 2.0  # Below expected: indefinitely deferred

        elif outcome_status == "Rejected":
            # Ineffective: not executed
            return 1.0

        elif outcome_status == "Unknown":
            # Pending: status unclear
            return None

        else:
            # Unknown status type
            log.warning(f"[quality-scoring] Unknown outcome status: {outcome_status}")
            return None

    def _generate_reason(self, score: Optional[float], outcome_status: str) -> str:
        """
        Generate explanation for effectiveness score.

        Args:
            score: Effectiveness score (1.0-5.0 or None)
            outcome_status: Outcome status

        Returns:
            Human-readable reason for score
        """

        if score is None:
            return "Outcome status unknown, pending clarification"

        elif score == 5.0:
            return "Decision executed as planned with positive results"

        elif score == 4.0:
            return "Decision executed with minor modifications, achieved objectives"

        elif score == 3.5:
            return "Decision modified during implementation, modifications were beneficial"

        elif score == 3.0:
            return "Decision deferred initially but completed with acceptable results"

        elif score == 2.0:
            return "Decision was deferred and not yet completed"

        elif score == 1.0:
            return "Decision was rejected and never executed"

        else:
            return f"Outcome scored at {score} based on {outcome_status} status"

    def _generate_score_id(self) -> str:
        """
        Generate canonical quality score ID: SCO-YYYYMMDD-HHMMSS.

        Format: SCO-YYYYMMDD-HHMMSS
        Example: SCO-20260610-143000

        Returns:
            Unique, sortable quality score ID
        """
        now = datetime.utcnow()
        return now.strftime("SCO-%Y%m%d-%H%M%S")
