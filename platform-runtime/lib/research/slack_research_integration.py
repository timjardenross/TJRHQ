#!/usr/bin/env python3
"""Slack Research Integration.

Minimal, clean adapter between Slack command handling and ResearchOrchestrator.
Keeps the public API expected by the rest of the bot while avoiding merge damage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class CommandStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"
    RETRYING = "retrying"


@dataclass
class QueuedCommand:
    command_id: str
    user_id: str
    channel_id: str
    thread_ts: Optional[str]
    research_query: str
    created_at: datetime = datetime.utcnow()
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime = datetime.utcnow()
    status: CommandStatus = CommandStatus.QUEUED
    error_message: Optional[str] = None

    def should_retry(self) -> bool:
        return self.retry_count < self.max_retries and datetime.utcnow() >= self.next_retry_at

    def calculate_next_retry(self) -> datetime:
        backoff_seconds = min(2 ** self.retry_count, 60)
        return datetime.utcnow() + timedelta(seconds=backoff_seconds)


@dataclass
class SlackMessage:
    user_id: str
    channel_id: str
    thread_ts: Optional[str]
    text: str
    timestamp: str


class SlackResearchIntegration:
    """Adapter for Slack research commands."""

    def __init__(self, orchestrator: object):
        self.orchestrator = orchestrator
        log.info("[slack-research] Integration initialized")

    async def handle_research_command(
        self,
        command: str,
        user_id: str,
        channel_id: str,
        thread_ts: Optional[str] = None,
    ) -> str:
        query = self._parse_command(command)
        if not query:
            return "No research query found."

        try:
            result = self.orchestrator.orchestrate(query)
            if hasattr(result, "to_dict"):
                payload = result.to_dict()
                answer = payload.get("consolidated_findings") or payload.get("recommendation") or "Research completed."
            else:
                answer = str(result)
            return self._format_answer_for_slack(answer)
        except Exception as exc:
            log.error("[slack-research] command failed: %s", exc, exc_info=True)
            return f"Research failed: {type(exc).__name__}"

    async def handle_research_mention(
        self,
        text: str,
        user_id: str,
        channel_id: str,
        thread_ts: Optional[str] = None,
    ) -> str:
        return await self.handle_research_command(text, user_id, channel_id, thread_ts)

    def _parse_command(self, command: str) -> Optional[str]:
        if not command:
            return None
        text = command.strip()
        prefixes = ["/research", "research"]
        for prefix in prefixes:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break
        return text or None

    def _format_answer_for_slack(self, answer: str) -> str:
        return answer.strip()

    def _format_citations(self, citations: list[str]) -> str:
        return "\n".join(f"- {c}" for c in citations)

    def _format_metadata(self, confidence: float = 0.0, source_count: int = 0, execution_time_s: float = 0.0, cost: float = 0.0) -> str:
        return (
            f"_Confidence: {confidence:.0%} | "
            f"Sources: {source_count} | "
            f"Time: {execution_time_s:.1f}s | "
            f"Cost: ${cost:.4f}_"
        )

    def get_queue_status(self) -> Dict[str, Any]:
        return {"queued": 0, "retrying": 0, "failed": 0}

