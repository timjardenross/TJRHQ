#!/usr/bin/env python3
"""
Learning Loop Bridge — Research Orchestration ↔ MSN-0060B Integration

Connects Research Orchestration Level 2 outputs to MSN-0060B learning loop.

Workflow:
    1. Research Orchestration generates FinalAnswer
    2. Learning Loop Bridge captures research metadata
    3. Outcome Capture Service records decision
    4. Quality Scoring Service (B1C) evaluates quality
    5. Adaptive Routing (B1A) adjusts provider selection
    6. Learning Loop completes

Provider-Agnostic Design:
    - Works with any research provider
    - EvidencePack fields are provider-independent
    - Quality feedback is provider-agnostic
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

log = logging.getLogger(__name__)

# Lazy import so the bridge remains usable even if the quality scoring module
# is absent in non-standard deployments.
try:
    from lib.quality_scoring_service import QualityScoring as _QualityScoring
    _QUALITY_SCORING_AVAILABLE = True
except ImportError:
    _QUALITY_SCORING_AVAILABLE = False
    log.warning(
        "[learning-loop-bridge] quality_scoring_service unavailable; "
        "quality scoring will be skipped in record_decision_outcome()"
    )


# =====================================================================
# Data Structures
# =====================================================================


@dataclass
class ResearchDecision:
    """Record of research-informed decision for learning loop."""

    mission_id: str
    user_id: str
    original_query: str
    final_answer: str
    sources: List[str]
    evidence_packs: List[dict] = field(default_factory=list)
    decomposition_reason: Optional[str] = None
    provider_used: Optional[str] = None
    tokens_used: int = 0
    execution_time_ms: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    # Learning Loop fields (initially set, updated by B1C)
    quality_score: Optional[float] = None  # Set by Quality Scoring Service
    user_satisfaction: Optional[float] = None  # From user feedback
    confidence: float = 0.8
    contradiction_detected: bool = False


# =====================================================================
# Learning Loop Bridge
# =====================================================================


class LearningLoopBridge:
    """
    Bridge between Research Orchestration and MSN-0060B learning loop.

    Captures research outputs and feeds them into the learning loop
    for quality scoring, feedback, and adaptive routing improvements.

    Example:
        bridge = LearningLoopBridge(
            outcome_capture_service,
            research_memory_service
        )
        decision = bridge.capture_research_decision(
            final_answer,
            evidence_packs,
            user_id
        )
    """

    def __init__(
        self,
        outcome_capture_service: object,  # OutcomeCaptureService
        research_memory_service: object,  # ResearchMemoryService
        supabase_client=None,
    ):
        """
        Initialize Learning Loop Bridge.

        Args:
            outcome_capture_service: MSN-0060B outcome capture
            research_memory_service: Research evidence storage
            supabase_client: Optional Supabase client forwarded to
                QualityScoring so outcome scoring is persisted.  When
                omitted, a scoring instance is still created but scores
                are not written to the database.
        """
        self.outcome_capture = outcome_capture_service
        self.research_memory = research_memory_service

        # Wire the real QualityScoring service so record_decision_outcome()
        # can pass it through to record_outcome(), closing the B1C loop.
        if _QUALITY_SCORING_AVAILABLE:
            self._quality_scoring = _QualityScoring(supabase_client)
        else:
            self._quality_scoring = None

        log.info("[learning-loop-bridge] Initialized")

    def capture_research_decision(
        self,
        final_answer: object,  # FinalAnswer
        evidence_packs: List[object],  # List[EvidencePack]
        user_id: str,
    ) -> ResearchDecision:
        """
        Capture research decision for learning loop.

        Bridges research orchestration outputs to MSN-0060B outcome capture.

        Args:
            final_answer: FinalAnswer from GeminiSynthesizer
            evidence_packs: List of EvidencePack from research
            user_id: Slack user ID

        Returns:
            ResearchDecision ready for outcome capture
        """
        mission_id = getattr(final_answer, "mission_id", "unknown")
        original_query = getattr(final_answer, "original_query", "")
        answer_text = getattr(final_answer, "answer", "")
        sources = [
            getattr(source, "url", "") or getattr(source, "text", "")
            for source in getattr(final_answer, "sources", [])
        ]
        confidence = getattr(final_answer, "confidence", 0.8)
        execution_time = getattr(final_answer, "execution_time_ms", 0)

        log.info(
            f"[learning-loop-bridge] Capturing research decision: "
            f"mission_id={mission_id}, user_id={user_id}"
        )

        # Extract evidence pack metadata
        evidence_dicts = []
        provider_used = None
        total_tokens = 0

        for pack in evidence_packs:
            pack_dict = (
                pack.to_dict() if hasattr(pack, "to_dict") else {}
            )
            evidence_dicts.append(pack_dict)

            # Track provider (assumes all use same provider)
            if not provider_used:
                provider_used = pack_dict.get("provider", "unknown")

            # Sum tokens
            total_tokens += pack_dict.get("tokens_used", 0) or 0

        # Create research decision
        decision = ResearchDecision(
            mission_id=mission_id,
            user_id=user_id,
            original_query=original_query,
            final_answer=answer_text,
            sources=sources,
            evidence_packs=evidence_dicts,
            provider_used=provider_used,
            tokens_used=total_tokens,
            execution_time_ms=execution_time,
            confidence=confidence,
        )

        log.info(
            f"[learning-loop-bridge] Research decision captured: "
            f"confidence={decision.confidence}, tokens={decision.tokens_used}"
        )

        return decision

    def record_decision_outcome(
        self,
        decision: ResearchDecision,
        outcome_id: str,
        outcome_description: Optional[str] = None,
    ) -> bool:
        """
        Record research decision outcome for learning loop.

        Args:
            decision: ResearchDecision from capture_research_decision()
            outcome_id: Outcome ID from MSN-0060B
            outcome_description: Description of outcome

        Returns:
            True if recorded successfully
        """
        try:
            log.info(
                f"[learning-loop-bridge] Recording outcome: "
                f"outcome_id={outcome_id}, mission_id={decision.mission_id}"
            )

            # Record with the real outcome capture contract so the loop closes
            status = "Implemented" if outcome_description else "Unknown"
            outcome_notes = outcome_description or (
                f"Research outcome captured for mission {decision.mission_id}"
            )

            outcome = self.outcome_capture.record_outcome(
                decision_id=decision.mission_id,
                status=status,
                implementation_notes=outcome_notes,
                provider_name=getattr(decision, "provider_used", None),
                model_name=None,
                provider_route=None,
                # Pass the real scoring service so the B1C quality scoring
                # chain fires automatically inside OutcomeCapture.
                quality_scoring_service=self._quality_scoring,
            )

            if outcome:
                log.info(
                    f"[learning-loop-bridge] Outcome recorded successfully: "
                    f"decision_id={decision.mission_id}, outcome_id={outcome.id}"
                )
            else:
                log.warning(
                    f"[learning-loop-bridge] Outcome capture returned no record: "
                    f"decision_id={decision.mission_id}"
                )

            log.info(
                f"[learning-loop-bridge] Outcome bridge context: "
                f"bridge_outcome_id={outcome_id}, mission_id={decision.mission_id}"
            )

            return True

        except Exception as e:
            log.error(
                f"[learning-loop-bridge] Failed to record outcome: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return False

    def update_research_quality_score(
        self,
        mission_id: str,
        quality_score: float,
    ) -> bool:
        """
        Update research quality score from Quality Scoring Service (B1C).

        Called by MSN-0060B Quality Scoring Service after evaluation.

        Args:
            mission_id: Research mission ID
            quality_score: Quality score (0.0-1.0) from B1C

        Returns:
            True if updated successfully
        """
        try:
            log.info(
                f"[learning-loop-bridge] Updating quality score: "
                f"mission_id={mission_id}, score={quality_score}"
            )

            # Find evidence by mission_id and update quality_score
            evidence_packs = self.research_memory.find_by_mission(mission_id)

            for pack in evidence_packs:
                pack["quality_score"] = quality_score

                # Re-store with updated quality score
                self.research_memory.store_evidence(
                    pack,
                    pack.get("query_hash", ""),
                )

            log.info(
                f"[learning-loop-bridge] Quality score updated: "
                f"{len(evidence_packs)} evidence packs"
            )

            return True

        except Exception as e:
            log.error(
                f"[learning-loop-bridge] Failed to update quality score: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return False

    def get_research_for_adaptive_routing(
        self,
        mission_id: str,
    ) -> dict:
        """
        Retrieve research quality data for Adaptive Routing (B1A).

        Called by MSN-0060B Adaptive Routing to optimize provider selection.

        Args:
            mission_id: Research mission ID

        Returns:
            Dict with quality metrics for routing decisions
        """
        try:
            log.info(
                f"[learning-loop-bridge] Retrieving research for routing: "
                f"mission_id={mission_id}"
            )

            # Get evidence from memory
            evidence_packs = self.research_memory.find_by_mission(mission_id)

            if not evidence_packs:
                return {
                    "mission_id": mission_id,
                    "found": False,
                    "error": "No evidence found",
                }

            # Extract routing-relevant metrics
            providers = set()
            quality_scores = []
            tokens_used = 0

            for pack in evidence_packs:
                providers.add(pack.get("provider", "unknown"))
                if pack.get("quality_score"):
                    quality_scores.append(pack.get("quality_score"))
                tokens_used += pack.get("tokens_used", 0) or 0

            result = {
                "mission_id": mission_id,
                "found": True,
                "providers_used": list(providers),
                "average_quality_score": (
                    sum(quality_scores) / len(quality_scores)
                    if quality_scores
                    else None
                ),
                "tokens_used": tokens_used,
                "evidence_count": len(evidence_packs),
            }

            log.info(
                f"[learning-loop-bridge] Routing data retrieved: "
                f"avg_quality={result.get('average_quality_score')}"
            )

            return result

        except Exception as e:
            log.error(
                f"[learning-loop-bridge] Failed to get routing data: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return {
                "mission_id": mission_id,
                "found": False,
                "error": str(e)[:100],
            }

    def close_learning_loop(
        self,
        mission_id: str,
        quality_score: float,
        user_satisfaction: Optional[float] = None,
    ) -> bool:
        """
        Close learning loop: record quality and satisfaction.

        Called at end of MSN-0060B feedback cycle.

        Args:
            mission_id: Research mission ID
            quality_score: Quality score from B1C
            user_satisfaction: User satisfaction rating (optional)

        Returns:
            True if loop closed successfully
        """
        try:
            log.info(
                f"[learning-loop-bridge] Closing learning loop: "
                f"mission_id={mission_id}, quality={quality_score}"
            )

            # Update quality score
            self.update_research_quality_score(mission_id, quality_score)

            # Get routing data for next iteration
            routing_data = self.get_research_for_adaptive_routing(mission_id)

            log.info(
                f"[learning-loop-bridge] Learning loop closed: "
                f"routing_data={routing_data.get('average_quality_score')}"
            )

            return True

        except Exception as e:
            log.error(
                f"[learning-loop-bridge] Failed to close loop: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return False
