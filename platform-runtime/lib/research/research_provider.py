#!/usr/bin/env python3
"""
Research Provider Abstraction Layer

Defines the interface and base classes for research providers.
Supports Mistral, Gemini, and local fallback implementations.

Design Goal:
- Decouple research workflow from specific provider
- Enable provider swapping and fallback
- Capture metadata consistently across providers
- Support future provider additions

Public API:
    ResearchTask — Input specification for research
    EvidencePack — Output from research execution
    ResearchProvider — Abstract interface all providers implement
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
from enum import Enum

log = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ResearchStatus(str, Enum):
    """Research task execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ResearchTask:
    """Individual research task specification."""
    task_id: str
    description: str  # The actual research question/request
    focus_area: str   # Topic/context (for categorization)
    priority: int = 1  # Priority order (1=highest)
    max_tokens: int = 2000  # Max output tokens


@dataclass
class Citation:
    """Source citation from research output."""
    text: str  # Citation text or label [1], [2], etc.
    url: Optional[str] = None  # Source URL if available
    source_title: Optional[str] = None  # Source title


@dataclass
class EvidencePack:
    """Output from a single research task execution."""

    # Task identification
    task_id: str
    task_index: int
    mission_id: str
    parent_question: str
    research_task: str

    # Provider metadata
    provider: str  # "mistral", "gemini", "ollama", "none"
    model: str  # Specific model used
    provider_agent_id: Optional[str] = None
    provider_agent_version: Optional[str] = None

    # Research output
    answer: str = ""  # Main research findings
    citations: List[Citation] = field(default_factory=list)
    confidence: float = 0.5  # Confidence in answer (0.0-1.0)

    # Execution metadata
    status: str = ResearchStatus.SUCCESS
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: int = 0

    # Timestamps
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    # Learning Loop Integration (NEW)
    quality_score: Optional[float] = None
    # MSN-0060B B1C Quality Scoring: 0.0-1.0
    # Set by Quality Scoring Service after user feedback
    # Used by Adaptive Routing (B1A) for future provider selection

    feedback_prompt: Optional[str] = None
    # User feedback or quality assessment
    # Triggers Learning Loop feedback loop
    # Example: "Was this answer helpful?" → quality_score

    contradiction_detected: Optional[bool] = None
    # True if sources contradict each other
    # False if sources align
    # None if not analyzed
    # Indicates need for synthesis refinement

    decomposition_reason: Optional[str] = None
    # Why this task was created
    # Set by GeminiXODecomposer
    # Used for research memory analytics
    # Example: "Primary research on APRA CPS 230 requirements"

    source_count: Optional[int] = None
    # Number of unique sources in citations
    # Used for research quality metrics
    # Helps identify breadth of evidence

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "task_id": self.task_id,
            "task_index": self.task_index,
            "mission_id": self.mission_id,
            "parent_question": self.parent_question,
            "research_task": self.research_task,
            "provider": self.provider,
            "model": self.model,
            "provider_agent_id": self.provider_agent_id,
            "provider_agent_version": self.provider_agent_version,
            "answer": self.answer,
            "citations": [
                {
                    "text": c.text,
                    "url": c.url,
                    "source_title": c.source_title,
                }
                for c in self.citations
            ],
            "confidence": self.confidence,
            "status": self.status,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
            # Learning Loop Integration Fields (NEW)
            "quality_score": self.quality_score,
            "feedback_prompt": self.feedback_prompt,
            "contradiction_detected": self.contradiction_detected,
            "decomposition_reason": self.decomposition_reason,
            "source_count": self.source_count,
        }

    @property
    def is_success(self) -> bool:
        """True if research executed successfully."""
        return self.status == ResearchStatus.SUCCESS

    @property
    def is_failure(self) -> bool:
        """True if research failed."""
        return self.status in [
            ResearchStatus.FAILED,
            ResearchStatus.TIMEOUT,
            ResearchStatus.NOT_FOUND,
        ]

    @property
    def is_retriable(self) -> bool:
        """True if this error warrants retry."""
        return self.status in [
            ResearchStatus.TIMEOUT,
            ResearchStatus.RATE_LIMITED,
        ]


# ============================================================================
# Abstract Provider Interface
# ============================================================================


class ResearchProvider(ABC):
    """
    Abstract interface for research providers.
    All research providers must implement this interface.
    """

    @abstractmethod
    def execute_research(
        self,
        task: ResearchTask,
        mission_id: str,
        task_index: int,
        timeout_seconds: int = 90,
    ) -> EvidencePack:
        """
        Execute a single research task.

        Args:
            task: Research task specification
            mission_id: Parent mission identifier
            task_index: Position in task sequence (0-indexed)
            timeout_seconds: Maximum execution time

        Returns:
            EvidencePack with findings and metadata

        Note:
            Must never raise exceptions. Always return EvidencePack
            with status=failed if execution fails.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Return provider identifier.
        Examples: "mistral", "gemini", "ollama"
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return current model identifier."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if provider is available and operational.

        Returns:
            True if provider is ready, False if unavailable
        """
        pass

    @abstractmethod
    def can_retry(self, evidence_pack: EvidencePack) -> bool:
        """
        Determine if task should be retried.

        Args:
            evidence_pack: Failed execution result

        Returns:
            True if retry is appropriate, False otherwise
        """
        pass

    def _create_error_pack(
        self,
        task: ResearchTask,
        mission_id: str,
        task_index: int,
        status: str,
        error_message: str,
        latency_ms: int = 0,
    ) -> EvidencePack:
        """Helper to create error evidence packs."""
        return EvidencePack(
            task_id=task.task_id,
            task_index=task_index,
            mission_id=mission_id,
            parent_question=task.focus_area,
            research_task=task.description,
            provider=self.get_provider_name(),
            model=self.get_model_name(),
            provider_agent_id=None,
            provider_agent_version=None,
            answer="",
            citations=[],
            confidence=0.0,
            status=status,
            error=error_message,
            tokens_used=None,
            latency_ms=latency_ms,
        )


# ============================================================================
# Provider Registry for Fallback Logic
# ============================================================================


class ResearchProviderRegistry:
    """
    Manages multiple research providers and fallback chains.

    Enables trying providers in priority order until one succeeds.
    Supports graceful degradation if primary provider fails.
    """

    def __init__(self):
        self.providers: dict[str, ResearchProvider] = {}
        self.priority_list: list[tuple[int, str]] = []  # (priority, name)

    def register(
        self, provider: ResearchProvider, priority: int = 10
    ) -> None:
        """
        Register a research provider.

        Args:
            provider: ResearchProvider implementation
            priority: Priority score (higher = tried first)
        """
        name = provider.get_provider_name()
        self.providers[name] = provider
        self.priority_list.append((priority, name))
        self.priority_list.sort(reverse=True)
        log.info(
            f"[research-provider-registry] Registered {name} "
            f"(priority={priority})"
        )

    def execute_with_fallback(
        self,
        task: ResearchTask,
        mission_id: str,
        task_index: int,
        timeout_seconds: int = 90,
    ) -> EvidencePack:
        """
        Execute research task, trying providers in priority order.

        Falls through provider list until one succeeds.
        Logs provider attempts and failures for debugging.

        Args:
            task: Research task
            mission_id: Parent mission ID
            task_index: Task index in sequence
            timeout_seconds: Max execution time per provider

        Returns:
            EvidencePack from first successful provider,
            or error pack if all providers fail
        """

        providers_attempted = []

        for priority, provider_name in self.priority_list:
            provider = self.providers[provider_name]
            providers_attempted.append(provider_name)

            # Check provider health
            try:
                if not provider.health_check():
                    log.warning(
                        f"[research-provider-registry] {provider_name} "
                        f"health check failed; skipping"
                    )
                    continue
            except Exception as e:
                log.warning(
                    f"[research-provider-registry] {provider_name} "
                    f"health check error: {e}"
                )
                continue

            # Execute research
            try:
                log.info(
                    f"[research-provider-registry] Attempting {provider_name} "
                    f"for task {task.task_id}"
                )
                result = provider.execute_research(
                    task, mission_id, task_index, timeout_seconds
                )

                if result.is_success:
                    log.info(
                        f"[research-provider-registry] {provider_name} "
                        f"succeeded (tokens={result.tokens_used})"
                    )
                    return result

                # Task failed but provider is working
                if not result.is_retriable:
                    log.warning(
                        f"[research-provider-registry] {provider_name} "
                        f"failed (non-retriable): {result.error}"
                    )
                    # Try next provider
                    continue

                # Task timeout or rate limit - might retry same provider
                log.warning(
                    f"[research-provider-registry] {provider_name} "
                    f"retriable failure: {result.error}"
                )
                continue

            except Exception as e:
                log.error(
                    f"[research-provider-registry] {provider_name} "
                    f"exception: {type(e).__name__}: {str(e)[:100]}"
                )
                continue

        # All providers exhausted
        log.error(
            f"[research-provider-registry] All providers exhausted "
            f"(attempted: {', '.join(providers_attempted)})"
        )

        # Return failure pack with all providers attempted
        return EvidencePack(
            task_id=task.task_id,
            task_index=task_index,
            mission_id=mission_id,
            parent_question=task.focus_area,
            research_task=task.description,
            provider="none",
            model="none",
            answer="",
            citations=[],
            confidence=0.0,
            status=ResearchStatus.FAILED,
            error=f"All providers exhausted: {', '.join(providers_attempted)}",
        )

    def list_providers(self) -> list[str]:
        """Return list of registered providers in priority order."""
        return [name for _, name in self.priority_list]
