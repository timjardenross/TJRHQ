#!/usr/bin/env python3
"""MSN-0054 — Commander research delegation handler

Implements research delegation for the Number One Research Mission MVP.

Trigger: @Commander TJR research <topic>
Example: @Commander TJR research operational resilience trends in banking

Design:
- Integrates with existing Commander mention routing in app.py
- Commander bridge detects "research" intent from user message
- Routes to research handler
- Calls core/coordination/research_orchestration.py
- Formats ResearchMissionResult as Slack briefing
- Posts structured message with findings and recommendation
- Logs mission + decision (Phase 5)

Architecture:
- Non-blocking (failures don't crash Slack bot)
- Advisory-only (Number One recommends, Captain decides)
- Reuses existing Commander routing (no new slash commands)
- Can be invoked as: @Commander research <topic>

Public API:
    handle_research_request(text, user_id, channel_id) -> str (Slack-formatted response)
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Callable, Any, Optional

log = logging.getLogger(__name__)


# ============================================================================
# Research Mission Queue (MSN-0054E)
# ============================================================================

# In-memory FIFO queue for research missions
_research_queue = deque()  # Queue of (topic, user_id, channel_id, thread_ts)
_research_lock = threading.Lock()
_research_executing = False

def _generate_queue_mission_id() -> str:
    """Generate unique mission ID for queue tracking."""
    from datetime import datetime
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[:14]
    return f"QUEUED-{ts}"


# ============================================================================
# Public API
# ============================================================================

def handle_research_request(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """
    Handle research request from Commander routing with FIFO queue (MSN-0054E).

    Called when Commander detects "research" intent in user message.
    Example: "@Commander TJR research operational resilience trends in banking"

    If a research mission is already executing, queues the request and returns
    a position indicator. Otherwise, executes immediately.

    Args:
        text: Raw text from user (with "research" keyword removed by caller)
        user_id: Slack user ID (for authorization/logging)
        channel_id: Slack channel ID (for logging)

    Returns:
        Slack-formatted markdown response string (or queue position message)
    """

    global _research_lock, _research_queue, _research_executing

    log.info(
        "[research] Handling research request: user=%s channel=%s topic_len=%d",
        user_id, channel_id, len(text),
    )

    # Step 1: Validate topic
    validation_error = _validate_research_topic(text)
    if validation_error:
        log.warning("[research] Validation failed: %s", validation_error)
        return validation_error

    # Step 2: Validate authorization (Captain/XO/designated researchers)
    # TODO: Phase 5 — implement authorization checking via Supabase
    # For now, allow all Slack users (can restrict later)
    log.info("[research] Authorization: allowing all users (unrestricted in MVP)")

    # Step 3: Try to acquire research lock (non-blocking)
    # MSN-0054E: Check if another mission is executing
    acquired = _research_lock.acquire(blocking=False)

    if not acquired:
        # Another mission is executing, queue this request
        queue_mission_id = _generate_queue_mission_id()
        _research_queue.append({
            "topic": text.strip(),
            "user_id": user_id,
            "channel_id": channel_id,
        })
        position = len(_research_queue)
        log.warning(
            "[research] Mission queued: mission_id=%s position=%d user=%s channel=%s",
            queue_mission_id, position, user_id, channel_id,
        )
        return (
            f"Research mission queued. Position: {position}\n"
            f"_Mission ID: `{queue_mission_id}`_\n\n"
            f"Your research will begin when the current mission completes.\n"
            f"I will post results in this thread."
        )

    # Lock acquired, execute mission
    _research_executing = True
    try:
        message_text = _execute_research_mission(text.strip(), user_id, channel_id)
    finally:
        # Release lock and process queue
        _research_executing = False
        _research_lock.release()
        _process_research_queue()

    return message_text


def _execute_research_mission(
    text: str,
    user_id: str | None,
    channel_id: str | None,
) -> str:
    """Execute a single research mission (internal, locked)."""

    # Step 1: Import orchestration module
    try:
        _bot_dir = Path(__file__).resolve().parent.parent
        if str(_bot_dir) not in sys.path:
            sys.path.insert(0, str(_bot_dir))

        # Import orchestrator
        from core.coordination.research_orchestration import ResearchOrchestrator

    except ImportError as e:
        log.error("[research] Could not import orchestrator: %s", e)
        return (
            "❌ Number One research orchestration unavailable.\n"
            "Error: Research delegation module not found."
        )

    # Step 2: Execute research mission
    log.info("[research] Starting research mission (executing)")
    try:
        orchestrator = ResearchOrchestrator()
        result = orchestrator.run_research_mission(text.strip())

        log.info(
            "[research] Mission complete: id=%s status=%s tasks=%d/%d provider=%s",
            result.mission_id,
            result.status,
            result.tasks_completed,
            result.task_count,
            result.primary_provider,
        )

    except Exception as e:
        log.error("[research] Orchestration failed: %s — %s", type(e).__name__, e)
        return (
            "❌ Research mission failed.\n"
            f"Error: {str(e)[:100]}"
        )

    # Step 3: Format result for Slack
    message_text = _format_research_result(result)

    # Step 4: Guardrail — if formatted message is empty or too short, return explicit fallback
    if not message_text or len(message_text.strip()) < 20:
        log.error("[research] Formatted message is empty or too short: %d chars", len(message_text or ""))
        message_text = (
            "Number One Research Delegation failed before a briefing could be generated.\n"
            "Check bot logs for details.\n"
            f"Mission ID: {result.mission_id}\n"
            f"Status: {result.status}"
        )

    # Step 5: Prepare for Phase 5 logging (save mission/decision)
    # TODO: Phase 5 — integrate with mission_to_memory and decision_to_memory
    if result.status != "error":
        _queue_mission_logging(result, user_id)

    return message_text


def _process_research_queue() -> None:
    """Process queued research requests one by one."""
    global _research_lock, _research_queue

    while len(_research_queue) > 0:
        # Acquire lock for next queued mission
        _research_lock.acquire()

        if len(_research_queue) == 0:
            _research_lock.release()
            break

        # Dequeue next mission
        mission = _research_queue.popleft()
        position = len(_research_queue)  # Remaining queue size

        log.info(
            "[research-queue] Processing queued mission: user=%s channel=%s remaining=%d",
            mission["user_id"], mission["channel_id"], position,
        )

        try:
            # Execute queued mission with original context
            message_text = _execute_research_mission(
                mission["topic"],
                mission["user_id"],
                mission["channel_id"],
            )
            log.info("[research-queue] Queued mission complete, response: %d chars", len(message_text))

        except Exception as e:
            log.error("[research-queue] Queued mission execution failed: %s", e)
            message_text = f"❌ Research mission failed: {str(e)[:100]}"

        finally:
            _research_lock.release()


# ============================================================================
# Validation
# ============================================================================

def _validate_research_topic(topic: str) -> str | None:
    """
    Validate research topic.

    Args:
        topic: Raw topic text from command

    Returns:
        Error message if invalid, None if valid
    """

    if not topic or not topic.strip():
        return (
            ":x: Usage: `/xo research <topic>`\n"
            "Example: `/xo research What are best practices for API rate limiting?`"
        )

    topic_clean = topic.strip()

    if len(topic_clean) < 10:
        return (
            ":x: Research topic too short.\n"
            "Minimum 10 characters required.\n"
            f"Provided: {len(topic_clean)} chars"
        )

    if len(topic_clean) > 1000:
        return (
            ":x: Research topic too long.\n"
            "Maximum 1000 characters allowed.\n"
            f"Provided: {len(topic_clean)} chars"
        )

    return None


# ============================================================================
# Formatting
# ============================================================================

def _format_research_result(result) -> str:
    """
    Format ResearchMissionResult as plain-text Slack message.

    Args:
        result: ResearchMissionResult object

    Returns:
        Slack-formatted markdown string
    """

    # Status indicator (use Unicode emojis instead of Slack emoji codes to avoid markdown parsing issues)
    if result.status == "success":
        status_indicator = "✅"
        status_text = "Research Complete"
    elif result.status == "partial":
        status_indicator = "⚠️"
        status_text = "Partial Results"
    else:
        status_indicator = "❌"
        status_text = "Research Failed"

    # Build message (plain-text first line to avoid Slack markdown parsing as empty heading)
    message = f"Number One Research Delegation — {status_text}\n"
    message += f"{status_indicator} Status: {status_text}\n\n"
    message += f"*Mission ID:* `{result.mission_id}`\n"
    message += f"*Timestamp:* {result.timestamp}\n\n"

    # Task execution summary
    message += f"*Task Execution:* {result.tasks_completed}/{result.task_count} tasks complete\n"
    if result.primary_provider:
        message += f"*Primary Provider:* `{result.primary_provider}`\n"
    message += "\n"

    # Task breakdown — only show if tasks actually decomposed
    if result.task_breakdown and len(result.task_breakdown) > 0:
        message += "*Task Breakdown:*\n"
        for idx, task_desc in enumerate(result.task_breakdown, start=1):
            # Find corresponding task result for status
            task_result = next(
                (t for t in result.task_results if t.order_index == idx),
                None
            )
            if task_result and task_result.status == "complete":
                message += f"  {idx}. ✓ {task_desc}\n"
            else:
                message += f"  {idx}. ✗ {task_desc}\n"
        message += "\n"

        # Provider path telemetry
        if result.provider_paths:
            message += "*Provider Path:*\n"
            for idx, path in enumerate(result.provider_paths, start=1):
                message += f"  {idx}. {path}\n"
            message += "\n"
    elif result.status == "error" and result.task_count == 0:
        # Explicit error message when task decomposition failed
        message += "*Research Failure Reason:*\n"
        if result.errors:
            for error in result.errors:
                message += f"  • {error}\n"
        else:
            message += "  • Task decomposition failed (check Ollama connectivity and logs)\n"
        message += "\n*Next Steps:*\n"
        message += "  1. Verify Ollama is running (`curl http://localhost:11434`)\n"
        message += "  2. Check bot logs for detailed error messages\n"
        message += "  3. Retry the research request\n\n"

    # Consolidated findings
    if result.consolidated_findings and result.consolidated_findings.strip() != "No findings generated from research tasks.":
        message += "*Consolidated Findings:*\n"
        message += f"```{result.consolidated_findings}```\n\n"
    elif result.status != "error":
        message += "*Consolidated Findings:*\n"
        message += f"```{result.consolidated_findings or 'No findings generated.'}```\n\n"

    # Recommendation
    if result.recommendation:
        message += "*Number One Recommendation:*\n"
        message += f"_{result.recommendation}_\n"
        message += f"_(Confidence: {result.confidence:.0%})_\n\n"
    else:
        if result.status != "error":
            message += "*Recommendation:* No actionable recommendation from findings.\n\n"

    # Errors (if any, and not already shown in failure reason)
    if result.errors and result.status != "error":
        message += "*Errors/Warnings:*\n"
        for error in result.errors:
            message += f"  • {error}\n"
        message += "\n"

    # Footer
    message += "---\n"
    message += "_Research findings are advisory only. Captain/XO decision required._\n"

    return message




# ============================================================================
# Logging & Persistence (Phase 5)
# ============================================================================

def _queue_mission_logging(result, user_id: str | None) -> None:
    """
    Queue mission and decision for logging to Supabase.

    TODO: Phase 5 — Integrate with mission_to_memory and decision_to_memory.

    Args:
        result: ResearchMissionResult object
        user_id: Slack user ID (creator)
    """

    try:
        # TODO: Phase 5 implementation
        # from commands.mission_to_memory import save_mission_after_creation
        # from commands.decision_to_memory import save_decision_after_logging
        #
        # # Create mission record
        # save_mission_after_creation(
        #     mission_id=result.mission_id,
        #     title=f"Research: {result.research_topic[:50]}",
        #     user_id=user_id or "slack-bot",
        # )
        #
        # # If recommendation exists, create decision
        # if result.recommendation:
        #     decision_id = f"D-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        #     save_decision_after_logging(
        #         decision_id=decision_id,
        #         statement=result.recommendation,
        #         rationale=result.consolidated_findings,
        #         user_id=user_id or "slack-bot",
        #     )

        log.info("[research] Mission logging queued (Phase 5 integration pending)")

    except Exception as e:
        log.warning("[research] Failed to queue mission logging: %s", e)
        # Non-blocking: research already delivered to user




# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    print("\n=== Research Request Handler Test ===\n")

    # Test cases
    test_cases = [
        ("Valid topic", "What are best practices for API rate limiting?"),
        ("Too short", "API rate"),
        ("Empty", ""),
        ("Too long", "x" * 2000),
    ]

    for test_name, topic in test_cases:
        print(f"Test: {test_name}")
        print(f"  Topic: {topic[:50]}..." if len(topic) > 50 else f"  Topic: {topic}")

        response = handle_research_request(topic, "test-user", "test-channel")

        if response.startswith(":x:"):
            print(f"  Status: error")
            print(f"  Message: {response[:80]}")
        else:
            print(f"  Status: success")
            print(f"  Message length: {len(response)} chars")
            if "MSN-" in response:
                # Extract mission ID
                import re
                match = re.search(r"MSN-\d{8}-\d{6}", response)
                if match:
                    print(f"  Mission ID: {match.group()}")

        print()

    print("=== Test Complete ===\n")
