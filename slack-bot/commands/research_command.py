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
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)


# ============================================================================
# Public API
# ============================================================================

def handle_research_request(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """
    Handle research request from Commander routing.

    Called when Commander detects "research" intent in user message.
    Example: "@Commander TJR research operational resilience trends in banking"

    Args:
        text: Raw text from user (with "research" keyword removed by caller)
        user_id: Slack user ID (for authorization/logging)
        channel_id: Slack channel ID (for logging)

    Returns:
        Slack-formatted markdown response string
    """

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

    # Step 3: Import orchestration module
    try:
        _bot_dir = Path(__file__).resolve().parent.parent
        if str(_bot_dir) not in sys.path:
            sys.path.insert(0, str(_bot_dir))

        # Import orchestrator
        from core.coordination.research_orchestration import ResearchOrchestrator

    except ImportError as e:
        log.error("[research] Could not import orchestrator: %s", e)
        return (
            ":x: Number One research orchestration unavailable.\n"
            "Error: Research delegation module not found."
        )

    # Step 4: Execute research mission
    log.info("[research] Starting research mission")
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
            ":x: Research mission failed.\n"
            f"Error: {str(e)[:100]}"
        )

    # Step 5: Format result for Slack
    message_text = _format_research_result(result)

    # Step 6: Guardrail — if formatted message is empty or too short, return explicit fallback
    if not message_text or len(message_text.strip()) < 20:
        log.error("[research] Formatted message is empty or too short: %d chars", len(message_text or ""))
        message_text = (
            "Number One Research Delegation failed before a briefing could be generated.\n"
            "Check bot logs for details.\n"
            f"Mission ID: {result.mission_id}\n"
            f"Status: {result.status}"
        )

    # Step 7: Prepare for Phase 5 logging (save mission/decision)
    # TODO: Phase 5 — integrate with mission_to_memory and decision_to_memory
    if result.status != "error":
        _queue_mission_logging(result, user_id)

    return message_text


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
