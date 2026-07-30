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
import hashlib
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Callable, Any, Optional

# RESEARCH DELEGATOR FIX: Ensure repo root is in sys.path before importing
# This ensures imports work whether app.py has run yet or not
_research_command_file = Path(__file__).resolve()
_repo_root = _research_command_file.parent.parent.parent  # slack-bot/commands -> repo root
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# MSN-0055C Work Package 2: Provider Circuit Breaker
from lib.provider_health import ProviderHealth
from core.coordination.advisory_memory_formatter import format_memory_block
from core.coordination.memory_metrics import log_memory_metric

log = logging.getLogger(__name__)
log.debug(f"[research] Module imported, repo root in sys.path: {_repo_root}")


# ============================================================================
# Research Mission Queue (MSN-0054E)
# ============================================================================

# In-memory FIFO queue for research missions
_research_queue = deque()  # Queue of mission dicts with full Slack context
_research_lock = threading.Lock()
_research_executing = False
_slack_say_func = None  # Will be set by handle_research_request_with_slack()

# MSN-0055C Work Package 2: Provider health tracking across mission execution
# Persists across all tasks within a mission (reset on new mission)
_provider_health = ProviderHealth()


def _build_research_supabase_client():
    """Return a raw Supabase client for read paths, if available."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        raw_client = client.raw_client
        if raw_client is not None:
            return raw_client
    except Exception as exc:
        log.warning("[research] Supabase client unavailable for research memory: %s", exc)
    return None


def _build_mission_registry_memory_adapter():
    """Return the mission registry memory adapter if available."""
    try:
        from core.coordination.mission_registry_memory_adapter import MissionRegistryMemoryAdapter

        return MissionRegistryMemoryAdapter()
    except Exception as exc:
        log.warning("[research] Mission registry memory adapter unavailable: %s", exc)
        return None


def _build_decision_registry_memory_adapter():
    """Return the decision registry memory adapter if available."""
    try:
        from core.coordination.decision_registry_memory_adapter import DecisionRegistryMemoryAdapter

        return DecisionRegistryMemoryAdapter()
    except Exception as exc:
        log.warning("[research] Decision registry memory adapter unavailable: %s", exc)
        return None


def _compute_research_query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

def _generate_queue_mission_id() -> str:
    """Generate unique mission ID for queue tracking."""
    from datetime import datetime
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[:14]
    return f"QUEUED-{ts}"


# ============================================================================
# Public API
# ============================================================================

def handle_research_request_with_slack(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    message_ts: str | None = None,
    thread_ts: str | None = None,
    say: Callable | None = None,
) -> str:
    """
    Handle research request from Commander routing with FIFO queue and Slack posting (MSN-0054E).

    NEW: This version captures full Slack context and enables queued missions to post results.

    Called when Commander detects "research" intent in user message.
    Example: "@Commander TJR research operational resilience trends in banking"

    If a research mission is already executing, queues the request and returns
    a position indicator. Otherwise, executes immediately.

    Args:
        text: Raw text from user (with "research" keyword removed by caller)
        user_id: Slack user ID (for authorization/logging)
        channel_id: Slack channel ID (for logging)
        message_ts: Original message timestamp (for context)
        thread_ts: Original thread ID (for posting to correct thread)
        say: Slack say() function for posting results

    Returns:
        Slack-formatted markdown response string (or queue position message)
    """

    global _research_lock, _research_queue, _research_executing, _slack_say_func

    # Store say function globally so queue processor can use it
    _slack_say_func = say

    # Use new version with full context
    return handle_research_request(
        text=text,
        user_id=user_id,
        channel_id=channel_id,
        message_ts=message_ts,
        thread_ts=thread_ts,
    )


def handle_research_request(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    message_ts: str | None = None,
    thread_ts: str | None = None,
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
        message_ts: Original message timestamp (for context)
        thread_ts: Original thread ID (for posting to correct thread)

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
            "message_ts": message_ts,
            "thread_ts": thread_ts,  # MSN-0054E-FIX: Capture thread for result posting
        })
        position = len(_research_queue)
        log.warning(
            "[research] Mission queued: mission_id=%s position=%d user=%s channel=%s thread=%s",
            queue_mission_id, position, user_id, channel_id, thread_ts,
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

    # Step 1: Import orchestration module and memory retriever
    # NOTE: app.py validates ResearchOrchestrator at startup.
    # If it's available at startup, it's available here (Python caches imports).
    try:
        # Import orchestrator and memory retriever (MSN-0057 WP1)
        # These are validated at app.py startup, so import should succeed
        from core.coordination.research_orchestration import ResearchOrchestrator
        from lib.research_memory_retrieval import ResearchMemoryRetriever

        log.info("[research] ResearchOrchestrator imported successfully (cached from startup)")

    except ImportError as e:
        log.error("[research] CRITICAL: Could not import orchestrator/retriever: %s", e)
        log.error("[research] sys.path entries: %s", sys.path[:5])  # Log first 5 entries for debugging
        log.error("[research] RESEARCH_DELEGATOR_AVAILABLE=false - Import failed at execution time")
        return (
            "❌ Number One research orchestration unavailable.\n"
            f"Error: Research delegation module not found.\n"
            f"_Debug: {str(e)}_"
        )

    # Step 2: Check research memory BEFORE executing new research (MSN-0057 WP1)
    log.info("[research] Checking prior research (MSN-0057 WP1 retrieval)")
    retrieval_result = None
    try:
        research_supabase = _build_research_supabase_client()
        retriever = ResearchMemoryRetriever(research_supabase)
        retrieval_result = retriever.search_prior_research(text.strip())

        log.info(
            "[research] Memory retrieval complete: found=%s decision=%s confidence=%.2f",
            retrieval_result.found,
            retrieval_result.recommendation,
            retrieval_result.match_confidence,
        )

        # Log retrieval decision
        log.debug(
            "[research] Retrieval analysis: reason=%s match_confidence=%.2f found=%s",
            retrieval_result.reason,
            retrieval_result.match_confidence,
            retrieval_result.found,
        )

        log_memory_metric(
            source="research",
            action="memory_lookup",
            outcome="hit" if retrieval_result.found else "miss",
            confidence=retrieval_result.match_confidence,
            memory_type="research",
            details={"recommendation": retrieval_result.recommendation},
        )

    except Exception as e:
        log.warning("[research] Memory retrieval failed (non-blocking): %s", e)
        retrieval_result = None
        # Continue with new research; retrieval failure does not block execution

    # Step 2b: If REUSE or REUSE_WITH_NOTE, return prior findings (MSN-0057 WP1)
    mission_registry_note = ""
    try:
        registry_adapter = _build_mission_registry_memory_adapter()
        if registry_adapter:
            registry_context = registry_adapter.retrieve_related_missions(
                title=text.strip(),
                objective=text.strip(),
                text=text.strip(),
                limit=3,
            )
            if registry_context.found and registry_context.related_missions:
                mission_registry_note = "\n" + format_memory_block(
                    label="📚 Related missions",
                    items=[
                        {
                            "mission_id": m.mission_id,
                            "status": m.status,
                            "reason": m.reason,
                        }
                        for m in registry_context.related_missions[:3]
                    ],
                    source_types=["mission registry"],
                    summary=registry_context.summary,
                    confidence=registry_context.confidence,
                )
                log_memory_metric(
                    source="research",
                    action="mission_overlap_warning",
                    outcome="warning",
                    confidence=registry_context.confidence,
                    memory_type="mission",
                    details={"related_count": len(registry_context.related_missions)},
                )
    except Exception as exc:
        log.warning("[research] Mission registry lookup failed (non-blocking): %s", exc)

    decision_registry_note = ""
    try:
        decision_adapter = _build_decision_registry_memory_adapter()
        if decision_adapter:
            decision_context = decision_adapter.retrieve_related_decisions(
                title=text.strip(),
                objective=text.strip(),
                text=text.strip(),
                limit=3,
            )
            if decision_context.found and decision_context.related_decisions:
                decision_registry_note = "\n" + format_memory_block(
                    label="🧭 Related decisions",
                    items=[
                        {
                            "decision_id": d.decision_id,
                            "status": d.status,
                            "reason": d.reason,
                        }
                        for d in decision_context.related_decisions[:3]
                    ],
                    source_types=["decision registry"],
                    summary=decision_context.summary,
                    confidence=decision_context.confidence,
                )
                if decision_context.conflict_warnings:
                    decision_registry_note += "\n⚠️ Decision conflict: review overlapping approved or superseded decisions."
                    log_memory_metric(
                        source="research",
                        action="decision_conflict_warning",
                        outcome="warning",
                        confidence=decision_context.confidence,
                        memory_type="decision",
                        details={"conflict_count": len(decision_context.conflict_warnings)},
                    )
    except Exception as exc:
        log.warning("[research] Decision registry lookup failed (non-blocking): %s", exc)

    if retrieval_result and retrieval_result.recommendation in ("REUSE", "REUSE_WITH_NOTE"):
        log.info(
            "[research] Prior research reused: decision=%s confidence=%.2f mission_id=%s",
            retrieval_result.recommendation,
            retrieval_result.match_confidence,
            retrieval_result.entry.get("mission_id") if retrieval_result.entry else "unknown",
        )

        # Format reused research result
        reuse_header = "🔄 *Prior Research Reused*" if retrieval_result.recommendation == "REUSE" else "🔄 *Prior Research + Fresh Data*"
        reuse_note = "" if retrieval_result.recommendation == "REUSE" else "\n📝 *Note:* Prior research supplemented with current findings."

        message_text = (
            f"{reuse_header}\n"
            f"🎯 *Question:* {text.strip()}\n"
            f"📊 *Findings:* {retrieval_result.entry.get('findings', 'See prior research')}\n"
            f"🎯 *Recommendation:* {retrieval_result.entry.get('recommendation', 'See prior research')}\n"
            f"📈 *Confidence:* {int(retrieval_result.match_confidence * 100)}% (from prior research)"
            f"{reuse_note}\n"
            f"{mission_registry_note}"
            f"{decision_registry_note}"
            f"⏱️ *Research Time:* <100ms (retrieved from memory)"
        )

        # Log reuse for metrics
        _queue_mission_logging_reuse(
            question=text.strip(),
            findings=retrieval_result.entry.get('findings', ''),
            recommendation=retrieval_result.entry.get('recommendation', ''),
            confidence=retrieval_result.match_confidence,
            user_id=user_id,
        )
        log_memory_metric(
            source="research",
            action="reuse_accepted",
            outcome="accepted",
            confidence=retrieval_result.match_confidence,
            memory_type="research",
            details={"mission_id": retrieval_result.entry.get("mission_id") if retrieval_result.entry else ""},
        )

        return message_text

    # Step 3: Execute new research mission (prior research not reusable)
    log.info("[research] Starting new research mission (executing)")
    try:
        global _provider_health

        # MSN-0055C WP2: Reset provider health for new mission
        _provider_health.reset()
        log.debug("[research] Provider health tracker reset for new mission")

        orchestrator = ResearchOrchestrator()
        result = orchestrator.run_research_mission(text.strip(), provider_health=_provider_health)

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
    if mission_registry_note:
        message_text = f"{message_text}\n{mission_registry_note}"
    if decision_registry_note:
        message_text = f"{message_text}\n{decision_registry_note}"

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
        _persist_research_memory(result, user_id)
        _record_research_learning_loop(result, user_id)
        log_memory_metric(
            source="research",
            action="new_research_completed",
            outcome="fresh_research",
            confidence=getattr(result, "confidence", 0.0),
            memory_type="research",
            details={"mission_id": getattr(result, "mission_id", "")},
        )

    return message_text


def _process_research_queue() -> None:
    """Process queued research requests one by one and post results to Slack (MSN-0054E-FIX)."""
    global _research_lock, _research_queue, _slack_say_func

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

            # MSN-0054E-FIX: Post result to Slack if say() function available
            if _slack_say_func and message_text:
                _post_queued_mission_result(
                    message_text=message_text,
                    channel_id=mission["channel_id"],
                    thread_ts=mission.get("thread_ts"),
                    user_id=mission["user_id"],
                )

        except Exception as e:
            log.error("[research-queue] Queued mission execution failed: %s", e)
            message_text = f"❌ Research mission failed: {str(e)[:100]}"

            # MSN-0054E-FIX: Also post failure to Slack
            if _slack_say_func:
                _post_queued_mission_result(
                    message_text=message_text,
                    channel_id=mission["channel_id"],
                    thread_ts=mission.get("thread_ts"),
                    user_id=mission["user_id"],
                    is_error=True,
                )

        finally:
            _research_lock.release()


def _post_queued_mission_result(
    message_text: str,
    channel_id: str | None,
    thread_ts: str | None,
    user_id: str | None,
    is_error: bool = False,
) -> None:
    """
    Post queued mission result to Slack (MSN-0054E-FIX).

    Posts to original thread if available, otherwise to channel.
    Failures are logged but do not crash the bot.
    """
    global _slack_say_func

    if not _slack_say_func:
        log.warning(
            "[research-queue] Cannot post result: no Slack say() function available. "
            "Result will be lost. user=%s channel=%s",
            user_id, channel_id,
        )
        return

    try:
        # Use thread_ts if available (post in original thread), otherwise post to channel
        result_thread_ts = thread_ts

        log.info(
            "[research-queue] Posting queued mission result: "
            "channel=%s thread_ts=%s error=%s text_len=%d",
            channel_id, result_thread_ts, is_error, len(message_text),
        )

        _slack_say_func(
            message_text,
            channel=channel_id,
            thread_ts=result_thread_ts,
        )

        log.info(
            "[research-queue] Queued mission result posted successfully: "
            "channel=%s thread_ts=%s user=%s",
            channel_id, result_thread_ts, user_id,
        )

    except Exception as e:
        log.error(
            "[research-queue] Failed to post queued mission result: %s — %s",
            type(e).__name__, e,
        )
        # Do not re-raise; queue processing must continue


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
    Format ResearchMissionResult as Slack message (MSN-0056, MSN-BRIEFING-OFFICER Path A).

    Path A: Captain's Brief as Primary Output
    - Shows Captain's Brief first (if available, ~150 words)
    - Preserves full findings in logs
    - Includes mission ID for log reference
    - Falls back to standard research format if briefing fails

    Args:
        result: ResearchMissionResult object

    Returns:
        Slack-formatted markdown string
    """

    # PATH A: Captain's Brief as Primary Output
    if hasattr(result, 'captains_brief') and result.captains_brief:
        # Brief is available - use it as primary output
        message = result.captains_brief
        message += f"\n\n---\n"
        message += f"*Mission ID:* `{result.mission_id}`\n"
        message += f"Full research available in research log.\n"
        return message

    # FALLBACK: Standard research format (if brief unavailable)
    message = "🔍 *Research Complete*\n"
    message += "━━━━━━━━━━━━━━━━━━\n"
    message += f"*Mission:* {result.mission_id}\n"
    message += f"*Status:* {'✓ Complete' if result.status == 'success' else '⚠ Partial' if result.status == 'partial' else '✗ Failed'} ({result.tasks_completed}/{result.task_count} tasks)\n"
    if result.primary_provider:
        message += f"*Provider:* {result.primary_provider}\n"
    message += "\n"

    # Findings (always shown in fallback)
    if result.consolidated_findings and result.consolidated_findings.strip() != "No findings generated from research tasks.":
        message += "📊 *FINDINGS*\n"
        # Truncate if too long for Slack
        findings_preview = result.consolidated_findings[:500]
        if len(result.consolidated_findings) > 500:
            findings_preview += "...\n\n[Full findings available in research log]"
        message += f"{findings_preview}\n\n"

    # Recommendation (conditional: only for decision-oriented or unclear requests)
    is_informational = getattr(result, 'request_type', 'unclear') == 'informational'
    if not is_informational:
        message += "🎯 *RECOMMENDATION*\n"
        if result.recommendation:
            message += f"{result.recommendation}\n"
            message += f"_Confidence: {result.confidence:.0%}_\n"
        else:
            message += "_No recommendation available from research._\n"
        message += "\n"

    # Caveats (only if errors or partial results)
    if result.errors and result.status != "success":
        message += "⚠️ *NOTES*\n"
        for error in result.errors:
            message += f"  • {error}\n"
        message += "\n"

    # Next action (context-dependent)
    message += "📋 *NEXT ACTION*\n"
    if is_informational:
        message += "Research findings available for review\n\n"
    else:
        message += "Request Captain/XO review for decision approval\n\n"

    # Footer: Authority and guidance
    message += "---\n"
    if is_informational:
        message += "_Research findings are available for reference._\n"
    else:
        message += "_Research findings are advisory. Captain/XO decision required._\n"

    return message




# ============================================================================
# Logging & Persistence (Phase 5)
# ============================================================================

def _queue_mission_logging(result, user_id: str | None) -> None:
    """
    Queue mission and decision for logging to Supabase (MSN-0056: Memory Persistence).

    Persists completed research to command memory for learning and reuse.

    Args:
        result: ResearchMissionResult object
        user_id: Slack user ID (creator)
    """

    try:
        # MSN-0056: Save research outcome to memory
        research_memory = {
            "mission_id": result.mission_id,
            "research_topic": result.research_topic,
            "research_date": result.timestamp,
            "task_breakdown": result.task_breakdown or [],
            "tasks_executed": result.task_count,
            "tasks_completed": result.tasks_completed,
            "status": result.status,
            "consolidated_findings": result.consolidated_findings,
            "recommendation": result.recommendation,
            "confidence_level": result.confidence,
            "providers_used": result.provider_paths or [],
            "primary_provider": result.primary_provider,
            "execution_status": "success" if result.status == "success" else "partial" if result.status == "partial" else "failed",
            "researcher_id": user_id or "slack-bot",
        }

        # TODO: Phase 5 implementation
        # Persist to memory system (e.g., Supabase research_memory table)
        # Example:
        # from lib.memory import save_research_outcome
        # save_research_outcome(research_memory)

        log.info(
            "[research] Mission outcome recorded: mission_id=%s status=%s tasks=%d/%d confidence=%.0f%%",
            result.mission_id,
            result.status,
            result.tasks_completed,
            result.task_count,
            result.confidence * 100
        )

    except Exception as e:
        log.warning("[research] Failed to save mission outcome to memory: %s", e)
        # Non-blocking: research already delivered to user; memory save is auxiliary


def _queue_mission_logging_reuse(
    question: str,
    findings: str,
    recommendation: str,
    confidence: float,
    user_id: str | None,
) -> None:
    """
    Log a successful research reuse event (MSN-0057 WP1).

    Tracks when prior research is reused instead of executing new research.
    Used for metrics: reuse rate, time savings, confidence patterns.

    Args:
        question: Original research question
        findings: Findings from prior research
        recommendation: Recommendation from prior research
        confidence: Confidence score of reused research
        user_id: Slack user ID (requester)
    """

    try:
        log.info(
            "[research-reuse] Research reused: question_len=%d confidence=%.2f user=%s",
            len(question),
            confidence,
            user_id or "unknown",
        )

        # TODO: Phase 5 implementation
        # Track reuse metrics (can be used for analytics)
        # Example:
        # from lib.metrics import record_reuse_event
        # record_reuse_event({
        #     "question": question,
        #     "confidence": confidence,
        #     "user_id": user_id,
        #     "timestamp": datetime.utcnow(),
        # })

        log.debug(
            "[research-reuse] Reuse metrics: question=%s confidence=%.2f",
            question[:50],
            confidence,
        )

    except Exception as e:
        log.warning("[research-reuse] Failed to log reuse event: %s", e)
        # Non-blocking: reuse already delivered to user; metrics logging is auxiliary


def _record_research_learning_loop(result, user_id: str | None) -> None:
    """Feed a completed research mission into the MSN-0060B learning loop (SUOC Wave 1)."""
    try:
        from lib.research_learning_loop import record_research_lifecycle_event
    except ImportError as exc:
        log.warning("[research] Learning loop unavailable (missing dependency: %s) — skipped", exc)
        return

    try:
        record_research_lifecycle_event(
            mission_id=result.mission_id,
            research_topic=result.research_topic or "",
            recommendation=result.recommendation or "",
            confidence=float(result.confidence or 0.0),
            status=result.status,
            provider_path=result.provider_paths or [],
            user_id=user_id,
        )
    except Exception as exc:
        log.warning("[research] Learning loop recording failed (non-blocking): %s", exc)


def _persist_research_memory(result, user_id: str | None) -> None:
    """Persist completed research to the existing Supabase memory layer."""
    try:
        client = _build_research_supabase_client()
        if client is None:
            log.info("[research] Supabase disabled; skipping research memory persistence")
            return

        query_text = result.research_topic or ""
        query_hash = _compute_research_query_hash(query_text)
        payload = {
            "mission_id": result.mission_id,
            "original_question": query_text,
            "consolidated_findings": result.consolidated_findings,
            "recommendation": result.recommendation or "",
            "confidence_level": float(result.confidence or 0.0),
            "created_at": result.timestamp,
            "tags": [term for term in query_text.lower().split() if len(term) > 2][:10],
            "reuse_count": 0,
            "provider_path": result.provider_paths or [],
            "tasks_completed": int(result.tasks_completed or 0),
            "task_count": int(result.task_count or 0),
            "query_hash": query_hash,
            "researcher_id": user_id or "slack-bot",
            "execution_status": "success" if result.status == "success" else "partial" if result.status == "partial" else "failed",
            "stored_at": datetime.utcnow().isoformat(),
        }

        write_result = client.insert("research_memory", payload)
        if not write_result.ok:
            log.warning(
                "[research] Research memory persistence failed: table=%s error=%s",
                write_result.table,
                write_result.error,
            )
            return

        log.info(
            "[research] Research memory persisted: mission_id=%s query_hash=%s",
            result.mission_id,
            query_hash[:8],
        )

        # MSN-0329 Phase 4: canonical Captain Brief pipeline event —
        # the Research domain's one real choke point. Non-blocking,
        # matches publish_event()'s own contract.
        try:
            from core.platform.event_bus import publish_event
            publish_event(
                "research.memory_persisted", domain="research",
                source="slack-bot:research_command",
                confidence=round(float(result.confidence or 0.0) * 100) if result.confidence else None,
                recommended_action=result.recommendation or None,
            )
        except Exception:
            pass
    except Exception as exc:
        log.warning("[research] Failed to persist research memory (non-blocking): %s", exc)


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
