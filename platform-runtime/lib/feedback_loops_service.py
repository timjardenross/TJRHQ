#!/usr/bin/env python3
"""
MSN-0060B Phase B1D: Feedback Loops Service

Generates feedback signals from quality scores.
Tracks provider quality and enables adaptive routing.

Design: Minimal MVP
- Generates feedback signals (outcome → provider quality change)
- Tracks provider quality metrics (rolling averages, trends)
- Enables adaptive routing based on quality history
- Defers predictive scoring to B1E

Authority Model:
- Feedback service generates signals autonomously
- Signals advisory (inform routing, not enforce)
- Provider quality tracked continuously
- Extensible for B1E predictive scoring

Public API:
    feedback_loops = FeedbackLoops(supabase_client)
    signal = feedback_loops.generate_feedback(quality_score)
    provider_stats = feedback_loops.get_provider_quality(provider_name)
    routing_order = feedback_loops.suggest_routing()
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

class FeedbackAction(Enum):
    """Suggested routing action based on feedback."""
    INCREASE = "increase"      # Provider quality improving, increase weight
    DECREASE = "decrease"      # Provider quality declining, decrease weight
    MAINTAIN = "maintain"      # Provider quality stable, maintain weight


class QualityTrend(Enum):
    """Quality trend direction."""
    UP = "up"           # Quality improving
    DOWN = "down"       # Quality declining
    STABLE = "stable"   # Quality stable


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class FeedbackSignal:
    """
    Feedback signal from quality score.

    Represents how well a provider performed on a decision.
    Informs adaptive routing and continuous improvement.
    """

    # Identity
    id: str  # FBK-YYYYMMDD-HHMMSS
    score_id: str
    decision_id: str

    # Attribution
    provider_name: str

    # Feedback (required before defaults)
    effectiveness_delta: float  # Score vs. baseline delta
    suggested_action: str  # "increase", "decrease", "maintain"

    # Optional fields with defaults
    model_name: Optional[str] = None
    provider_route: Optional[str] = None
    feedback_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary for Supabase insert."""
        return {
            "id": self.id,
            "score_id": self.score_id,
            "decision_id": self.decision_id,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "provider_route": self.provider_route,
            "effectiveness_delta": self.effectiveness_delta,
            "suggested_action": self.suggested_action,
            "feedback_timestamp": self.feedback_timestamp,
        }


@dataclass
class ProviderQuality:
    """Provider quality metrics and trend."""
    provider_name: str
    model_name: Optional[str]
    provider_route: Optional[str]
    decisions_count: int
    avg_effectiveness: float
    effectiveness_trend: str  # "up", "down", "stable"
    quality_tier: str  # "high", "medium", "low"
    last_score_date: Optional[str]


# ============================================================================
# Feedback Loops Service
# ============================================================================

class FeedbackLoops:
    """
    Service for generating feedback signals and tracking provider quality.

    B1D Phase: Enables continuous learning through feedback loops.
    Generates signals for adaptive routing and quality improvement.
    """

    # Provider baseline effectiveness (default)
    DEFAULT_BASELINE = 3.0

    def __init__(self, supabase_client=None):
        """
        Initialize feedback loops service.

        Args:
            supabase_client: Supabase client (optional, can be set later)
        """
        self.supabase_client = supabase_client
        log.info("[feedback-loops] FeedbackLoops service initialized")

    def generate_feedback(
        self,
        score_id: str,
        decision_id: str,
        provider_name: str,
        effectiveness_score: Optional[float],
        model_name: Optional[str] = None,
        provider_route: Optional[str] = None,
    ) -> Optional[FeedbackSignal]:
        """
        Generate feedback signal from quality score.

        MSN-0060B B1D: Create feedback signal for provider quality tracking.

        Args:
            score_id: Quality score ID (SCO-YYYYMMDD-HHMMSS)
            decision_id: Decision record ID
            provider_name: AI provider (Google, OpenRouter, Ollama)
            effectiveness_score: Quality score (1.0-5.0) or None
            model_name: Model name (Gemini, Mistral, Qwen)
            provider_route: Routing strategy (Primary, Fallback, Local)

        Returns:
            FeedbackSignal if successful, None if error
        """

        # Skip if score is unknown/pending
        if effectiveness_score is None:
            log.debug(
                f"[feedback-loops] Skipping feedback for unknown score: {score_id}"
            )
            return None

        # Get provider baseline
        baseline = self._get_provider_baseline(provider_name, model_name, provider_route)

        # Calculate delta (score - baseline)
        delta = effectiveness_score - baseline

        # Suggest action based on delta
        if delta > 0.5:
            action = FeedbackAction.INCREASE.value
        elif delta < -0.5:
            action = FeedbackAction.DECREASE.value
        else:
            action = FeedbackAction.MAINTAIN.value

        # Create feedback signal
        signal_id = self._generate_feedback_id()
        signal = FeedbackSignal(
            id=signal_id,
            score_id=score_id,
            decision_id=decision_id,
            provider_name=provider_name,
            model_name=model_name,
            provider_route=provider_route,
            effectiveness_delta=delta,
            suggested_action=action,
        )

        # Persist if client available
        if self.supabase_client:
            try:
                response = (
                    self.supabase_client.table("feedback_signals")
                    .insert(signal.to_dict())
                    .execute()
                )

                log.info(
                    f"[feedback-loops] Feedback signal generated: signal_id={signal_id}, "
                    f"provider={provider_name}, delta={delta:.1f}, action={action}"
                )

                # Update provider quality metrics
                self._update_provider_quality(signal)

                return signal

            except Exception as e:
                log.error(
                    f"[feedback-loops] Failed to generate feedback: {type(e).__name__}: {str(e)[:100]}"
                )
                return None
        else:
            log.debug(f"[feedback-loops] Feedback signal created (not persisted): {signal_id}")
            return signal

    def get_provider_quality(
        self, provider_name: str, model_name: Optional[str] = None
    ) -> Optional[ProviderQuality]:
        """
        Get provider quality metrics.

        Args:
            provider_name: AI provider name
            model_name: Optional model name for specific model quality

        Returns:
            ProviderQuality record if found, None otherwise
        """

        if not self.supabase_client:
            log.error("[feedback-loops] Supabase client not configured")
            return None

        try:
            # Query provider_quality_history or recalculate from quality_scores
            # For now, query provider_quality_trend view
            response = (
                self.supabase_client.table("v_provider_quality_trend")
                .select("*")
                .eq("provider_name", provider_name)
                .execute()
            )

            if response.data and len(response.data) > 0:
                data = response.data[0]
                return ProviderQuality(
                    provider_name=data.get("provider_name"),
                    model_name=data.get("model_name"),
                    provider_route=data.get("provider_route"),
                    decisions_count=data.get("total_decisions", 0),
                    avg_effectiveness=float(data.get("avg_effectiveness", 0)),
                    effectiveness_trend=data.get("trend", "stable"),
                    quality_tier=data.get("quality_tier", "medium"),
                    last_score_date=data.get("latest_score_date"),
                )
            else:
                log.debug(f"[feedback-loops] No quality data found for provider: {provider_name}")
                return None

        except Exception as e:
            log.error(
                f"[feedback-loops] Failed to retrieve provider quality: {type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def suggest_routing(self) -> list:
        """
        Suggest routing order based on provider quality.

        Returns providers ordered by effectiveness score.

        Returns:
            List of (provider_name, avg_score) tuples, ordered by score DESC
        """

        if not self.supabase_client:
            log.error("[feedback-loops] Supabase client not configured")
            return []

        try:
            # Query v_provider_quality_trend view
            response = (
                self.supabase_client.table("v_provider_quality_trend")
                .select("provider_name, avg_effectiveness")
                .order("avg_effectiveness", desc=True)
                .execute()
            )

            routing_order = []
            for data in response.data or []:
                routing_order.append(
                    (data.get("provider_name"), float(data.get("avg_effectiveness", 0)))
                )

            log.debug(
                f"[feedback-loops] Suggested routing order: {[p[0] for p in routing_order]}"
            )
            return routing_order

        except Exception as e:
            log.error(
                f"[feedback-loops] Failed to suggest routing: {type(e).__name__}: {str(e)[:100]}"
            )
            return []

    def get_provider_trend(self, provider_name: str) -> Optional[str]:
        """
        Get provider quality trend.

        Args:
            provider_name: AI provider name

        Returns:
            Trend string: "up", "down", or "stable"
        """

        quality = self.get_provider_quality(provider_name)
        if quality:
            return quality.effectiveness_trend
        return None

    def _get_provider_baseline(
        self,
        provider_name: str,
        model_name: Optional[str] = None,
        provider_route: Optional[str] = None,
    ) -> float:
        """
        Get provider baseline (average effectiveness).

        Uses provider quality history if available, otherwise uses default.

        Args:
            provider_name: AI provider name
            model_name: Optional model name
            provider_route: Optional routing strategy

        Returns:
            Baseline effectiveness score (default: 3.0)
        """

        # Query provider_quality_history for baseline
        if self.supabase_client:
            try:
                response = (
                    self.supabase_client.table("provider_quality_history")
                    .select("avg_effectiveness")
                    .eq("provider_name", provider_name)
                    .execute()
                )

                if response.data and len(response.data) > 0:
                    avg = response.data[0].get("avg_effectiveness")
                    if avg is not None:
                        return float(avg)
            except Exception as e:
                log.debug(
                    f"[feedback-loops] Could not get baseline for {provider_name}: {e}"
                )

        # Default baseline
        return self.DEFAULT_BASELINE

    def _update_provider_quality(self, signal: FeedbackSignal):
        """
        Update provider quality metrics after feedback signal.

        Recalculates rolling average and trend.

        Args:
            signal: FeedbackSignal that was just generated
        """

        if not self.supabase_client:
            return

        try:
            # Get or create provider_quality_history record
            response = (
                self.supabase_client.table("provider_quality_history")
                .select("*")
                .eq("provider_name", signal.provider_name)
                .eq("model_name", signal.model_name)
                .eq("provider_route", signal.provider_route)
                .execute()
            )

            # Recalculate metrics from quality_scores table
            quality_response = (
                self.supabase_client.table("quality_scores")
                .select("effectiveness_score")
                .eq("provider_name", signal.provider_name)
                .execute()
            )

            scores = [
                s["effectiveness_score"]
                for s in (quality_response.data or [])
                if s["effectiveness_score"] is not None
            ]

            if not scores:
                return

            # Calculate metrics
            avg_effectiveness = sum(scores) / len(scores)
            count = len(scores)

            # Determine trend
            if count >= 2:
                recent_avg = sum(scores[-min(5, count) :]) / min(5, count)
                if recent_avg > avg_effectiveness + 0.5:
                    trend = "up"
                elif recent_avg < avg_effectiveness - 0.5:
                    trend = "down"
                else:
                    trend = "stable"
            else:
                trend = "stable"

            # Update or insert
            history_id = f"HIS-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

            update_data = {
                "decisions_count": count,
                "avg_effectiveness": round(avg_effectiveness, 1),
                "effectiveness_trend": trend,
                "last_score_date": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
            }

            if response.data and len(response.data) > 0:
                # Update existing
                self.supabase_client.table("provider_quality_history").update(
                    update_data
                ).eq("provider_name", signal.provider_name).execute()
            else:
                # Insert new
                insert_data = {
                    "id": history_id,
                    "provider_name": signal.provider_name,
                    "model_name": signal.model_name,
                    "provider_route": signal.provider_route,
                    **update_data,
                }
                self.supabase_client.table("provider_quality_history").insert(
                    insert_data
                ).execute()

            log.debug(
                f"[feedback-loops] Updated provider quality: {signal.provider_name}, "
                f"avg={round(avg_effectiveness, 1)}, trend={trend}"
            )

        except Exception as e:
            log.error(
                f"[feedback-loops] Failed to update provider quality: {type(e).__name__}: {str(e)[:100]}"
            )

    def _generate_feedback_id(self) -> str:
        """
        Generate canonical feedback signal ID: FBK-YYYYMMDD-HHMMSS.

        Format: FBK-YYYYMMDD-HHMMSS
        Example: FBK-20260610-143000

        Returns:
            Unique, sortable feedback signal ID
        """
        now = datetime.utcnow()
        return now.strftime("FBK-%Y%m%d-%H%M%S")
