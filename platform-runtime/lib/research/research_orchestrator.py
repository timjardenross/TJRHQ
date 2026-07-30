#!/usr/bin/env python3
"""
Research Orchestrator — End-to-End Mission Execution

Coordinates all Research Orchestration Level 2 components into a complete,
end-to-end research workflow.

Architecture:
    User Query (Slack)
        ↓
    GeminiXODecomposer (Phase 2B.1)
        └─ mission = decomposer.decompose_mission(request)
        ↓
    TaskExecutor (Phase 2B.2) — CONCURRENT EXECUTION
        └─ evidence_packs = executor.execute_mission_concurrent(mission)
        ↓
    GeminiSynthesizer (Phase 2B.4)
        └─ final_answer = synthesizer.synthesize_research(...)
        ↓
    Return FinalAnswer to Slack (Phase 2B.6)

Provider-Agnostic Design:
    - Orchestrates ONLY Phase 2B components
    - No provider-specific logic
    - Metrics collection provider-independent
    - Future-proof architecture
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)


# =====================================================================
# Data Structures
# =====================================================================


@dataclass
class ResearchExecutionMetrics:
    """Metrics from complete research mission execution."""

    mission_id: str
    total_execution_time_ms: int
    decomposition_time_ms: int
    execution_time_ms: int
    synthesis_time_ms: int
    total_tokens_used: int
    total_evidence_packs: int
    successful_packs: int
    failed_packs: int
    cache_hits: int
    total_cost_estimate: float


# =====================================================================
# Research Orchestrator
# =====================================================================


class ResearchOrchestrator:
    """
    Execute complete research missions end-to-end.

    Coordinates:
    1. Mission decomposition (GeminiXODecomposer)
    2. Task execution (TaskExecutor with concurrent support)
    3. Evidence synthesis (GeminiSynthesizer)
    4. Metrics collection

    Example:
        orchestrator = ResearchOrchestrator(
            decomposer,
            executor,
            synthesizer
        )
        final_answer = await orchestrator.execute_research_mission(
            mission_id="msn-001",
            user_query="What is APRA CPS 230?"
        )
    """

    def __init__(
        self,
        decomposer: object,  # GeminiXODecomposer
        executor: object,  # TaskExecutor
        synthesizer: object,  # GeminiSynthesizer
    ):
        """
        Initialize Research Orchestrator.

        Args:
            decomposer: GeminiXODecomposer instance
            executor: TaskExecutor instance
            synthesizer: GeminiSynthesizer instance
        """
        self.decomposer = decomposer
        self.executor = executor
        self.synthesizer = synthesizer
        self.metrics = None

        log.info(
            "[research-orchestrator] Initialized with "
            "decomposer, executor, and synthesizer"
        )

    async def execute_research_mission(
        self,
        mission_id: str,
        user_query: str,
        context: Optional[str] = None,
        priority: str = "medium",
    ) -> object:
        """
        Execute complete research mission.

        Workflow:
        1. Decompose mission into tasks
        2. Execute all tasks concurrently
        3. Synthesize results into final answer
        4. Collect metrics

        Args:
            mission_id: Unique mission identifier
            user_query: User's research question
            context: Optional context for decomposition
            priority: Priority level (low, medium, high)

        Returns:
            FinalAnswer with synthesized research result
        """
        log.info(
            f"[research-orchestrator] Starting mission {mission_id}: "
            f"{user_query[:80]}..."
        )

        start_time = asyncio.get_event_loop().time()

        try:
            # ===================================================================
            # STEP 1: DECOMPOSE MISSION
            # ===================================================================

            decomp_start = asyncio.get_event_loop().time()

            log.info(
                f"[research-orchestrator] Step 1: Decomposing mission..."
            )

            from gemini_xo_decomposer import MissionRequest

            request = MissionRequest(
                mission_id=mission_id,
                user_query=user_query,
                context=context,
                priority=priority,
            )

            mission = self.decomposer.decompose_mission(request)

            decomp_time = (
                asyncio.get_event_loop().time() - decomp_start
            ) * 1000

            log.info(
                f"[research-orchestrator] Decomposition complete: "
                f"{len(mission.tasks)} tasks, "
                f"confidence={mission.confidence}"
            )

            # ===================================================================
            # STEP 2: EXECUTE TASKS (CONCURRENT)
            # ===================================================================

            exec_start = asyncio.get_event_loop().time()

            log.info(
                f"[research-orchestrator] Step 2: Executing tasks "
                f"concurrently..."
            )

            evidence_packs = (
                await self.executor.execute_mission_concurrent(mission)
            )

            exec_time = (asyncio.get_event_loop().time() - exec_start) * 1000

            successful = sum(
                1 for pack in evidence_packs
                if getattr(pack, "status", None) == "success"
            )

            log.info(
                f"[research-orchestrator] Execution complete: "
                f"{successful}/{len(evidence_packs)} successful, "
                f"{exec_time:.0f}ms"
            )

            # ===================================================================
            # STEP 3: SYNTHESIZE RESULTS
            # ===================================================================

            synth_start = asyncio.get_event_loop().time()

            log.info(
                f"[research-orchestrator] Step 3: Synthesizing results..."
            )

            final_answer = self.synthesizer.synthesize_research(
                mission_id=mission_id,
                original_query=user_query,
                evidence_packs=evidence_packs,
                synthesis_instructions=mission.synthesis_instructions,
            )

            synth_time = (
                asyncio.get_event_loop().time() - synth_start
            ) * 1000

            log.info(
                f"[research-orchestrator] Synthesis complete: "
                f"confidence={final_answer.confidence}, "
                f"{len(final_answer.sources)} citations"
            )

            # ===================================================================
            # STEP 4: COLLECT METRICS
            # ===================================================================

            total_time = (
                asyncio.get_event_loop().time() - start_time
            ) * 1000

            metrics = self._collect_metrics(
                mission_id,
                total_time,
                decomp_time,
                exec_time,
                synth_time,
                evidence_packs,
            )

            self.metrics = metrics

            log.info(
                f"[research-orchestrator] Mission complete: "
                f"{total_time:.0f}ms total, "
                f"{metrics.total_tokens_used} tokens, "
                f"${metrics.total_cost_estimate:.4f}"
            )

            return final_answer

        except Exception as e:
            log.error(
                f"[research-orchestrator] Mission failed: "
                f"{type(e).__name__}: {str(e)[:200]}"
            )

            # Return error response
            from gemini_synthesizer import FinalAnswer

            return FinalAnswer(
                mission_id=mission_id,
                original_query=user_query,
                answer=f"Research mission failed: {str(e)[:500]}",
                confidence=0.0,
            )

    def _collect_metrics(
        self,
        mission_id: str,
        total_time_ms: float,
        decomp_time_ms: float,
        exec_time_ms: float,
        synth_time_ms: float,
        evidence_packs: list,
    ) -> ResearchExecutionMetrics:
        """
        Collect execution metrics.

        Args:
            mission_id: Mission identifier
            total_time_ms: Total execution time
            decomp_time_ms: Decomposition time
            exec_time_ms: Execution time
            synth_time_ms: Synthesis time
            evidence_packs: List of evidence packs

        Returns:
            ResearchExecutionMetrics object
        """
        successful = sum(
            1 for pack in evidence_packs
            if getattr(pack, "status", None) == "success"
        )
        failed = len(evidence_packs) - successful

        total_tokens = sum(
            getattr(pack, "tokens_used", 0) or 0
            for pack in evidence_packs
        )

        total_cost = total_tokens * 0.00001

        metrics = ResearchExecutionMetrics(
            mission_id=mission_id,
            total_execution_time_ms=int(total_time_ms),
            decomposition_time_ms=int(decomp_time_ms),
            execution_time_ms=int(exec_time_ms),
            synthesis_time_ms=int(synth_time_ms),
            total_tokens_used=total_tokens,
            total_evidence_packs=len(evidence_packs),
            successful_packs=successful,
            failed_packs=failed,
            cache_hits=0,  # TODO: Track actual cache hits
            total_cost_estimate=round(total_cost, 4),
        )

        log.info(
            f"[research-orchestrator] Metrics: "
            f"{int(total_time_ms)}ms total, "
            f"{total_tokens} tokens, "
            f"${total_cost:.4f}"
        )

        return metrics

    def get_last_metrics(self) -> Optional[ResearchExecutionMetrics]:
        """
        Get metrics from last mission execution.

        Returns:
            ResearchExecutionMetrics or None
        """
        return self.metrics
