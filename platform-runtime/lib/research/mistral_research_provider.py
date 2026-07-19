#!/usr/bin/env python3
"""
Mistral Research Scout Provider Implementation

Executes research tasks via Mistral's Research Scout Agent API.

IMPORTANT VALIDATION NOTES:
- Response parsing is PROVISIONAL
- Actual schema will be validated in PHASE-2A-MISTRAL-VALIDATION
- All assumptions are encapsulated here only
- Schema changes won't affect other components (Registry, Memory, Slack)

TODO: Update response parsing once actual schema is validated
  Tracked in: PHASE-2A-MISTRAL-VALIDATION
"""

from __future__ import annotations

import os
import logging
import time
import re
from typing import Optional
from abc import abstractmethod

from research_provider import (
    ResearchProvider,
    ResearchTask,
    Citation,
    EvidencePack,
    ResearchStatus,
)

log = logging.getLogger(__name__)


class MistralResearchProvider(ResearchProvider):
    """
    Mistral Research Scout Agent implementation.

    Uses beta.conversations.start() API to execute research tasks.

    PROVISIONAL: Response schema assumptions will be validated in Phase 2A.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_version: Optional[str] = None,
    ):
        """
        Initialize Mistral Research Provider.

        Args:
            api_key: Mistral API key (default: MISTRAL_API_KEY env var)
            agent_id: Research Scout Agent ID (default: MISTRAL_AGENT_ID env var)
            agent_version: Agent version (default: MISTRAL_AGENT_VERSION env var)

        TODO: Validate credentials on initialization once schema is confirmed
        """
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        self.agent_id = agent_id or os.getenv("MISTRAL_AGENT_ID")
        self.agent_version = agent_version or os.getenv(
            "MISTRAL_AGENT_VERSION", "latest"
        )
        self.model = "mistral-research-scout"
        self.client = None

        if not self.api_key:
            log.warning("[mistral] MISTRAL_API_KEY not configured")

        self._init_client()

    def _init_client(self):
        """Initialize Mistral client."""
        if not self.api_key:
            log.warning("[mistral] Cannot initialize client without API key")
            return

        try:
            # Try new SDK
            try:
                from mistralai.client import MistralClient

                self.client = MistralClient(api_key=self.api_key)
            except ImportError:
                # Try legacy SDK
                from mistral_sdk import MistralClient

                self.client = MistralClient(api_key=self.api_key)

            log.info("[mistral] Client initialized successfully")
        except ImportError as e:
            log.error(f"[mistral] Failed to import Mistral SDK: {e}")
        except Exception as e:
            log.error(f"[mistral] Failed to initialize client: {e}")

    def execute_research(
        self,
        task: ResearchTask,
        mission_id: str,
        task_index: int,
        timeout_seconds: int = 90,
    ) -> EvidencePack:
        """
        Execute research task via Mistral Research Scout Agent.

        TODO: This response parsing is PROVISIONAL and will be updated
              once PHASE-2A-MISTRAL-VALIDATION is complete.

        Args:
            task: Research task specification
            mission_id: Parent mission ID
            task_index: Task index in sequence
            timeout_seconds: Max execution time

        Returns:
            EvidencePack with research findings
        """

        if not self.client:
            return self._create_error_pack(
                task,
                mission_id,
                task_index,
                ResearchStatus.FAILED,
                "Mistral client not initialized",
            )

        start_time = time.time()

        try:
            # TODO: PROVISIONAL - Confirm actual API endpoint and parameters
            # Expected endpoint: client.beta.conversations.start()
            response = self.client.beta.conversations.start(
                agent_id=self.agent_id,
                agent_version=self.agent_version,
                messages=[{"role": "user", "content": task.description}],
            )

            # TODO: PROVISIONAL - Confirm actual response structure
            # Current assumptions (to be validated):
            # - response.choices[0].message.content contains the answer
            # - OR response.message.content contains the answer
            # - OR response.content contains the answer
            answer = self._extract_answer(response)

            if not answer:
                return self._create_error_pack(
                    task,
                    mission_id,
                    task_index,
                    ResearchStatus.FAILED,
                    "Could not extract answer from response",
                )

            # TODO: PROVISIONAL - Confirm citation extraction
            citations = self._extract_citations(answer)

            # TODO: PROVISIONAL - Confirm token usage and metadata
            tokens_used = self._extract_tokens_used(response)

            latency_ms = int((time.time() - start_time) * 1000)

            log.info(
                f"[mistral] Research successful: task_id={task.task_id}, "
                f"tokens={tokens_used}, latency_ms={latency_ms}"
            )

            return EvidencePack(
                task_id=task.task_id,
                task_index=task_index,
                mission_id=mission_id,
                parent_question=task.focus_area,
                research_task=task.description,
                provider="mistral",
                model=self.model,
                provider_agent_id=self.agent_id,
                provider_agent_version=self.agent_version,
                answer=answer,
                citations=citations,
                confidence=0.85,  # TODO: Adjust based on actual response quality metrics
                status=ResearchStatus.SUCCESS,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

        except TimeoutError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            log.warning(f"[mistral] Request timeout after {timeout_seconds}s")
            return self._create_error_pack(
                task,
                mission_id,
                task_index,
                ResearchStatus.TIMEOUT,
                f"Request timeout after {timeout_seconds}s",
                latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            # Check for specific error types
            if "429" in error_msg or "rate" in error_msg.lower():
                status = ResearchStatus.RATE_LIMITED
                log.warning(f"[mistral] Rate limited: {error_msg[:100]}")
            elif "401" in error_msg or "auth" in error_msg.lower():
                status = ResearchStatus.FAILED
                log.error(f"[mistral] Authentication failed: {error_msg[:100]}")
            else:
                status = ResearchStatus.FAILED
                log.error(
                    f"[mistral] Research failed: {type(e).__name__}: {error_msg[:100]}"
                )

            return self._create_error_pack(
                task,
                mission_id,
                task_index,
                status,
                error_msg[:200],
                latency_ms,
            )

    def _extract_answer(self, response) -> Optional[str]:
        """
        Extract research answer from response.

        TODO: PROVISIONAL - Actual extraction path to be validated
        Currently tries multiple paths to handle response structure variations.
        """
        # Try standard chat completion path
        if hasattr(response, "choices") and response.choices:
            if hasattr(response.choices[0], "message"):
                if hasattr(response.choices[0].message, "content"):
                    return response.choices[0].message.content

        # Try direct message path
        if hasattr(response, "message") and hasattr(response.message, "content"):
            return response.message.content

        # Try content path
        if hasattr(response, "content"):
            return response.content

        # Try messages array path
        if hasattr(response, "messages") and response.messages:
            last_message = response.messages[-1]
            if hasattr(last_message, "content"):
                return last_message.content

        # Could not extract
        log.warning(
            f"[mistral] Could not extract answer from response type: {type(response)}"
        )
        return None

    def _extract_citations(self, text: str) -> list[Citation]:
        """
        Extract citations from answer text.

        TODO: PROVISIONAL - Citation format to be validated with actual responses
        Currently looks for [n] patterns and attempts URL extraction.
        """
        citations = []

        # Pattern 1: [1], [2], etc.
        numbered_pattern = r"\[(\d+)\]"
        for match in re.finditer(numbered_pattern, text):
            citations.append(Citation(text=f"[{match.group(1)}]"))

        # Pattern 2: [source_text](url)
        markdown_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        for match in re.finditer(markdown_pattern, text):
            source_text = match.group(1)
            url = match.group(2)
            citations.append(Citation(text=source_text, url=url))

        # Pattern 3: URLs in text
        url_pattern = r"https?://[^\s]+"
        for match in re.finditer(url_pattern, text):
            url = match.group(0)
            if not any(c.url == url for c in citations):
                citations.append(Citation(text="Source", url=url))

        log.info(
            f"[mistral] Extracted {len(citations)} citations from answer"
        )
        return citations

    def _extract_tokens_used(self, response) -> Optional[int]:
        """
        Extract token usage from response.

        TODO: PROVISIONAL - Token field location to be validated
        """
        # Try usage object path
        if hasattr(response, "usage"):
            if hasattr(response.usage, "total_tokens"):
                return response.usage.total_tokens
            if hasattr(response.usage, "completion_tokens"):
                # Estimate total
                prompt_tokens = (
                    response.usage.prompt_tokens
                    if hasattr(response.usage, "prompt_tokens")
                    else 0
                )
                completion_tokens = response.usage.completion_tokens
                return prompt_tokens + completion_tokens

        # Try direct field path
        if hasattr(response, "tokens_used"):
            return response.tokens_used

        # Try metrics object
        if hasattr(response, "metrics") and hasattr(response.metrics, "tokens"):
            return response.metrics.tokens

        log.debug("[mistral] Could not extract token usage from response")
        return None

    def get_provider_name(self) -> str:
        """Return provider identifier."""
        return "mistral"

    def get_model_name(self) -> str:
        """Return current model identifier."""
        return self.model

    def health_check(self) -> bool:
        """
        Check if Mistral provider is available.

        TODO: PROVISIONAL - Health check endpoint to be validated
        """
        if not self.client or not self.api_key:
            return False

        try:
            # Simple health check: call with minimal query
            response = self.client.beta.conversations.start(
                agent_id=self.agent_id,
                agent_version=self.agent_version,
                messages=[{"role": "user", "content": "ping"}],
            )
            log.debug("[mistral] Health check passed")
            return True
        except Exception as e:
            log.warning(f"[mistral] Health check failed: {str(e)[:100]}")
            return False

    def can_retry(self, evidence_pack: EvidencePack) -> bool:
        """
        Determine if task should be retried.

        Retryable errors: TIMEOUT, RATE_LIMITED
        Non-retryable: FAILED (auth, not found, etc.)
        """
        return evidence_pack.status in [
            ResearchStatus.TIMEOUT,
            ResearchStatus.RATE_LIMITED,
        ]
