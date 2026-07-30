#!/usr/bin/env python3
"""
MSN-0060B Phase B1D→B1A: Adaptive Routing Service

Uses provider quality data from B1D feedback loops to make intelligent routing decisions.
Enables quality-based provider selection instead of static/round-robin.

Architecture:
- Backend-only access (SERVICE_ROLE_KEY via FeedbackLoops)
- Non-blocking (failures don't crash routing; logged for audit)
- Quality-ranked fallback chain
- Default fallback if no quality data

Public API:
    adaptive_routing = AdaptiveRoutingService(feedback_loops_service)
    providers = adaptive_routing.get_routing_order()
    provider = adaptive_routing.select_provider()
    routing = adaptive_routing.log_routing_decision(decision_id, selected_provider)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple

log = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ProviderRanking:
    """Provider ranked by quality score."""
    rank: int
    provider_name: str
    avg_effectiveness: float
    quality_tier: str  # high, medium, low
    effectiveness_trend: str  # up, down, stable
    decisions_count: int


@dataclass
class RoutingDecision:
    """Routing decision record."""
    decision_id: str
    primary_provider: str
    fallback_provider: str
    fallback_chain: List[str]
    routing_rationale: str
    quality_data_available: bool
    timestamp: str


# ============================================================================
# Adaptive Routing Service
# ============================================================================

class AdaptiveRoutingService:
    """
    Service for adaptive provider selection based on quality data.

    B1D→B1A Integration: Uses feedback_loops to rank providers by quality.
    """

    def __init__(self, feedback_loops_service=None):
        """
        Initialize adaptive routing service.

        Args:
            feedback_loops_service: FeedbackLoops service for quality data
        """
        self.feedback_loops = feedback_loops_service
        log.info("[adaptive-routing] AdaptiveRoutingService initialized")

    def get_routing_order(self) -> List[ProviderRanking]:
        """
        Get providers ranked by quality.

        Returns:
            List of ProviderRanking, ordered by quality (highest first)
        """

        # Default providers if no quality data
        default_order = [
            ("Google", 3.0, "medium"),
            ("OpenRouter", 3.0, "medium"),
            ("Ollama", 3.0, "medium"),
        ]

        if not self.feedback_loops:
            log.warning("[adaptive-routing] FeedbackLoops not configured, using default providers")
            return [
                ProviderRanking(
                    rank=i + 1,
                    provider_name=provider,
                    avg_effectiveness=quality,
                    quality_tier=tier,
                    effectiveness_trend="stable",
                    decisions_count=0,
                )
                for i, (provider, quality, tier) in enumerate(default_order)
            ]

        try:
            # Get provider quality from B1D
            provider_quality = self.feedback_loops.get_provider_quality()

            if not provider_quality:
                log.info("[adaptive-routing] No provider quality data available, using defaults")
                return [
                    ProviderRanking(
                        rank=i + 1,
                        provider_name=provider,
                        avg_effectiveness=quality,
                        quality_tier=tier,
                        effectiveness_trend="stable",
                        decisions_count=0,
                    )
                    for i, (provider, quality, tier) in enumerate(default_order)
                ]

            # Rank providers
            rankings = []
            for rank, quality in enumerate(provider_quality, 1):
                ranking = ProviderRanking(
                    rank=rank,
                    provider_name=quality.provider_name,
                    avg_effectiveness=quality.avg_effectiveness,
                    quality_tier=quality.quality_tier,
                    effectiveness_trend=quality.effectiveness_trend,
                    decisions_count=quality.decisions_count,
                )
                rankings.append(ranking)

            log.info(f"[adaptive-routing] Provider ranking ({len(rankings)} providers):")
            for ranking in rankings:
                log.info(
                    f"  {ranking.rank}. {ranking.provider_name}: "
                    f"{ranking.avg_effectiveness:.1f}/5.0 ({ranking.quality_tier}) - "
                    f"{ranking.decisions_count} decisions"
                )

            return rankings

        except Exception as e:
            log.error(
                f"[adaptive-routing] Error getting provider quality: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            log.warning("[adaptive-routing] Falling back to default providers")
            return [
                ProviderRanking(
                    rank=i + 1,
                    provider_name=provider,
                    avg_effectiveness=quality,
                    quality_tier=tier,
                    effectiveness_trend="stable",
                    decisions_count=0,
                )
                for i, (provider, quality, tier) in enumerate(default_order)
            ]

    def select_provider(self) -> Tuple[str, List[str]]:
        """
        Select primary and fallback providers.

        Returns:
            Tuple of (primary_provider, fallback_chain)
        """

        routing_order = self.get_routing_order()

        if not routing_order:
            log.warning("[adaptive-routing] No routing order available")
            return ("Google", ["OpenRouter", "Ollama"])

        # Primary provider (highest quality)
        primary = routing_order[0].provider_name

        # Fallback chain (remaining providers in quality order)
        fallback_chain = [r.provider_name for r in routing_order[1:]]

        log.info(f"[adaptive-routing] Primary: {primary}, Fallback: {fallback_chain}")

        return primary, fallback_chain

    def log_routing_decision(
        self,
        decision_id: str,
        selected_provider: str,
        routing_rationale: str = "",
    ) -> RoutingDecision:
        """
        Log routing decision for audit trail.

        Args:
            decision_id: Decision being routed
            selected_provider: Selected provider
            routing_rationale: Why this provider was selected

        Returns:
            RoutingDecision record
        """

        primary, fallback = self.select_provider()
        routing_order = self.get_routing_order()

        quality_data_available = len(routing_order) > 0 and any(
            r.decisions_count > 0 for r in routing_order
        )

        # Calculate rationale if not provided
        if not routing_rationale:
            if quality_data_available:
                primary_quality = routing_order[0].avg_effectiveness if routing_order else 0
                second_quality = routing_order[1].avg_effectiveness if len(routing_order) > 1 else 0
                gap = primary_quality - second_quality
                routing_rationale = (
                    f"{primary} leads by {gap:.1f} quality points "
                    f"({primary_quality:.1f} vs {second_quality:.1f})"
                )
            else:
                routing_rationale = "Using default provider (no quality data)"

        decision = RoutingDecision(
            decision_id=decision_id,
            primary_provider=primary,
            fallback_provider=fallback[0] if fallback else "Ollama",
            fallback_chain=fallback,
            routing_rationale=routing_rationale,
            quality_data_available=quality_data_available,
            timestamp=datetime.utcnow().isoformat(),
        )

        log.info(f"[adaptive-routing] Routing decision logged:")
        log.info(f"  Decision: {decision_id}")
        log.info(f"  Primary: {decision.primary_provider}")
        log.info(f"  Fallback: {decision.fallback_chain}")
        log.info(f"  Rationale: {routing_rationale}")

        return decision

    def suggest_routing(
        self,
        decision_id: str = None,
    ) -> List[Tuple[str, float]]:
        """
        Suggest routing order with quality scores.

        B1D integration: Returns provider ranking from quality history.

        Args:
            decision_id: Optional decision ID for logging

        Returns:
            List of (provider_name, quality_score) tuples, ranked by quality
        """

        routing_order = self.get_routing_order()

        result = [
            (r.provider_name, r.avg_effectiveness)
            for r in routing_order
        ]

        if decision_id:
            log.info(
                f"[adaptive-routing] Routing suggestion for {decision_id}: "
                f"{[(p, f'{q:.1f}') for p, q in result]}"
            )

        return result
