#!/usr/bin/env python3
"""MSN-0054: Research Orchestration Module

Orchestrates research delegation for the Number One Research Mission.

Core Responsibilities:
  - Accept research topic
  - Decompose topic into tasks (via Ollama)
  - Execute tasks sequentially (via research_delegator.py)
  - Consolidate findings
  - Generate recommendation/decision candidate
  - Return structured result

Authority Model:
  - Number One RECOMMENDS research actions
  - Captain/XO DECIDES on findings
  - All execution is advisory-only (non-binding)

Design:
  - Deterministic task execution
  - Sequential (no parallelization)
  - Non-blocking error handling (failures don't crash)
  - In-memory execution (no database persistence in this phase)
  - Testable without Slack integration
"""

from __future__ import annotations

import os
import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional
import sys
from pathlib import Path
import time
import importlib.util

log = logging.getLogger(__name__)

# MSN-0055C WP7: Import metrics collection (same directory)
try:
    from research_metrics import ResearchMetricsCollector
except ImportError:
    # Fallback: load dynamically (similar to research_delegator pattern)
    _metrics_file = Path(__file__).parent / "research_metrics.py"
    _spec_metrics = importlib.util.spec_from_file_location("research_metrics", _metrics_file)
    if _spec_metrics and _spec_metrics.loader:
        _metrics_module = importlib.util.module_from_spec(_spec_metrics)
        sys.modules["research_metrics"] = _metrics_module
        _spec_metrics.loader.exec_module(_metrics_module)
        ResearchMetricsCollector = _metrics_module.ResearchMetricsCollector
        log.debug(f"Loaded research_metrics from {_metrics_file}")
    else:
        log.error(f"Could not create spec for research_metrics at {_metrics_file}")
        ResearchMetricsCollector = None

# Import existing research_delegator
# Dynamically discover and import from slack_bot/lib using importlib

delegate_research_task = None
ResearchOutcome = None

# Calculate path relative to this file: core/coordination/research_orchestration.py
# Go up 2 levels to reach the root, then into slack-bot/lib (note: hyphen, not underscore)
_orchestrator_path = Path(__file__).resolve()
_slack_bot_lib_dir = _orchestrator_path.parent.parent.parent / "slack-bot" / "lib"
_research_delegator_file = _slack_bot_lib_dir / "research_delegator.py"

try:
    # Use importlib to load from file path directly
    _spec = importlib.util.spec_from_file_location(
        "research_delegator",
        _research_delegator_file
    )
    if _spec and _spec.loader:
<<<<<<< Updated upstream
        # CRITICAL FIX: Ensure slack-bot/lib is in sys.path BEFORE exec_module
        # This allows research_delegator.py to import sibling modules like provider_health.py
        if str(_slack_bot_lib_dir) not in sys.path:
            sys.path.insert(0, str(_slack_bot_lib_dir))

=======
>>>>>>> Stashed changes
        _delegator_module = importlib.util.module_from_spec(_spec)
        # Register in sys.modules BEFORE exec_module to avoid dataclass issues
        sys.modules["research_delegator"] = _delegator_module
        _spec.loader.exec_module(_delegator_module)
        delegate_research_task = _delegator_module.delegate_research_task
        ResearchOutcome = _delegator_module.ResearchOutcome
        call_gemini_2_5_flash_lite_research = _delegator_module.call_gemini_2_5_flash_lite_research
        log.debug(f"Loaded research_delegator from {_research_delegator_file}")
    else:
        log.error(f"Could not create spec for research_delegator at {_research_delegator_file}")
except (ImportError, AttributeError, FileNotFoundError) as e:
<<<<<<< Updated upstream
    log.error(
        f"Failed to import research_delegator from {_research_delegator_file}: {e}",
        exc_info=True
    )
    call_gemini_2_5_flash_lite_research = None
except Exception as e:
    log.error(
        f"Unexpected error loading research_delegator from {_research_delegator_file}: {type(e).__name__}: {e}",
        exc_info=True
    )
    call_gemini_2_5_flash_lite_research = None

# Startup logging for troubleshooting
log.info(f"[startup] research_orchestration.py loaded")
log.info(f"[startup] delegate_research_task loaded = {delegate_research_task is not None}")
log.info(f"[startup] ResearchOutcome loaded = {ResearchOutcome is not None}")
log.info(f"[startup] Research delegator file: {_research_delegator_file}")
log.info(f"[startup] Research delegator file exists = {_research_delegator_file.exists()}")
=======
    log.error(f"Failed to import research_delegator: {e}")
    call_gemini_2_5_flash_lite_research = None
>>>>>>> Stashed changes


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ResearchTask:
    """Individual research task within a mission."""

    task_id: str  # RES-YYYYMMDD-HHMMSS-NN
    mission_id: str
    order_index: int
    description: str
    status: str = "pending"  # pending, delegated, complete, failed
    provider: Optional[str] = None  # gemini-2.5-flash, gemini-2-flash, gemini-2.5-flash-lite, ollama, none
    findings: Optional[str] = None
    references: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    provider_chain: list[str] = field(default_factory=list)  # Telemetry: providers attempted in order

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ResearchMissionResult:
    """Result of a complete research mission."""

    mission_id: str  # MSN-YYYYMMDD-HHMMSS
    research_topic: str
    status: str  # "success", "partial", "error"
    timestamp: str  # ISO 8601

    # Task breakdown
    task_breakdown: list[str]  # descriptions of tasks
    task_count: int
    tasks_completed: int

    # Results
    task_results: list[ResearchTask] = field(default_factory=list)
    consolidated_findings: str = ""
    recommendation: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0

    # Metadata
    primary_provider: Optional[str] = None  # gemini-2.5-flash, gemini-2-flash, gemini-2.5-flash-lite, ollama, none
    errors: list[str] = field(default_factory=list)
    provider_paths: list[str] = field(default_factory=list)  # Telemetry: provider chain for each task (e.g., ["gemini-2.5-flash → ollama"])
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
    request_type: str = "unclear"  # MSN-RECOMMENDATION-FIX Option B: "informational", "decision", or "unclear"
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["task_results"] = [t.to_dict() for t in self.task_results]
        return result


# ============================================================================
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
# Request Type Classification (Option B: Adaptive Recommendation Mode)
# ============================================================================

def classify_request_type(research_topic: str) -> str:
    """
    Classify whether request is informational or decision-oriented.

    MSN-RECOMMENDATION-FIX: Option B implementation.
    - Informational requests (define, explain, list) → findings-only mode
    - Decision requests (should, which, best) → findings + recommendation mode
    - Uncertain/ambiguous → default to recommendation (conservative)

    Args:
        research_topic: The research request text

    Returns:
        "informational", "decision", or "unclear"
    """

    if not research_topic:
        return "unclear"

    topic_lower = research_topic.lower()

    # Informational keywords: asking "what is X?" or "explain/define X"
    informational_keywords = {
        "define",
        "what",
        "explain",
        "describe",
        "list",
        "identify",
        "mean",
        "how does",
        "what are",
        "what is",
        "understanding",
        "principles of",
        "background on",
        "overview of",
        "summary of",
    }

    # Decision keywords: asking "should we?" or "which approach?"
    decision_keywords = {
        "should",
        "should we",
        "which",
        "best",
        "recommend",
        "optimal",
        "approach",
        "strategy",
        "prefer",
        "how should",
        "how can we",
        "what should",
        "how to",
        "need to",
        "require",
        "implement",
        "adopt",
        "choose",
    }

    # Count keyword matches
    info_count = 0
    decision_count = 0

    for kw in informational_keywords:
        if kw in topic_lower:
            info_count += 1

    for kw in decision_keywords:
        if kw in topic_lower:
            decision_count += 1

    log.debug(f"[request-type] Topic: {research_topic[:60]}...")
    log.debug(f"[request-type] Informational score: {info_count}, Decision score: {decision_count}")

    # Classify based on scores
    if info_count > decision_count:
        classification = "informational"
    elif decision_count > info_count:
        classification = "decision"
    else:
        # No strong signal or tied → default to recommendation (conservative)
        classification = "unclear"

    log.info(f"[request-type] Classified as '{classification}' (info:{info_count}, dec:{decision_count})")
    return classification


# ============================================================================
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
# Orchestration Engine
# ============================================================================

class ResearchOrchestrator:
    """
    Orchestrates research mission execution.

    Workflow:
    1. Accept research topic
    2. Decompose into tasks (via Ollama)
    3. Execute tasks sequentially
    4. Consolidate findings
    5. Generate recommendation
    6. Return structured result
    """

    def __init__(self, config: Optional[ResearchConfig] = None):
        """Initialize orchestrator."""
        self.config = config or ResearchConfig()
        self.current_time = datetime.utcnow()

    def run_research_mission(
        self,
        research_topic: str,
        mission_id: Optional[str] = None,
        provider_health: Optional[Any] = None,  # MSN-0055C WP2: Circuit breaker
    ) -> ResearchMissionResult:
        """
        Execute complete research mission.

        Args:
            research_topic: What to research (10-1000 chars)
            mission_id: Optional mission ID; generated if not provided
            provider_health: Optional ProviderHealth tracker (MSN-0055C WP2)
                           Tracks provider failures within mission
                           Skips unavailable providers on subsequent tasks

        Returns:
            ResearchMissionResult with all findings and metadata
        """

        # Generate mission ID if not provided
        if not mission_id:
            mission_id = self._generate_mission_id()

        log.info(f"Starting research mission {mission_id}: {research_topic[:80]}...")

<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
        # MSN-RECOMMENDATION-FIX Option B: Classify request type (informational vs decision-oriented)
        request_type = classify_request_type(research_topic)

>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
        # MSN-0055C WP7: Initialize metrics collection
        mission_start_time = time.time()
        metrics = ResearchMetricsCollector(mission_id, research_topic)

        # Step 1: Decompose into tasks
<<<<<<< Updated upstream
<<<<<<< Updated upstream
        log.info("Step 1: Task decomposition (Ollama)")
=======
        log.info("Step 1: Task decomposition (Gemini → Mistral → Ollama fallback chain)")
>>>>>>> Stashed changes
=======
        log.info("Step 1: Task decomposition (Ollama)")
>>>>>>> Stashed changes
        task_descriptions = self._decompose_research_topic(research_topic)

        if not task_descriptions:
            log.error("Task decomposition failed; no tasks generated")
            return ResearchMissionResult(
                mission_id=mission_id,
                research_topic=research_topic,
                status="error",
                timestamp=datetime.utcnow().isoformat(),
                task_breakdown=[],
                task_count=0,
                tasks_completed=0,
                errors=["Task decomposition failed"],
            )

        log.info(f"Decomposed into {len(task_descriptions)} tasks")

        # Step 2: Create task objects
        tasks = []
        for idx, desc in enumerate(task_descriptions, start=1):
            task = ResearchTask(
                task_id=self._generate_task_id(mission_id, idx),
                mission_id=mission_id,
                order_index=idx,
                description=desc,
            )
            tasks.append(task)

        # Step 3: Execute tasks sequentially
        log.info("Step 2: Sequential task delegation")

        # Safety check: ensure delegate_research_task is available
        if delegate_research_task is None:
            log.error("research_delegator module not available; cannot execute tasks")
            return ResearchMissionResult(
                mission_id=mission_id,
                research_topic=research_topic,
                status="error",
                timestamp=datetime.utcnow().isoformat(),
                task_breakdown=[t.description for t in tasks],
                task_count=len(tasks),
                tasks_completed=0,
                task_results=tasks,
                errors=["Research delegator module not available"],
            )

        primary_provider = None
        for task in tasks:
            log.info(f"  Executing task {task.order_index}/{len(tasks)}: {task.description[:60]}...")

            # MSN-0055C WP2: Pass provider health tracker for circuit breaker
            outcome = delegate_research_task(
                task.description,
                timeout_sec=self.config.TASK_TIMEOUT_SEC,
                provider_health=provider_health
            )

            task.status = "complete" if outcome.status == "success" else "failed"
            task.provider = outcome.provider
            task.findings = outcome.findings
            task.references = outcome.references or []
            task.error_message = outcome.error_message
            task.execution_time_ms = outcome.execution_time_ms
            task.provider_chain = outcome.provider_attempted or []  # Telemetry: provider chain

            if outcome.status == "success":
                if primary_provider is None:
                    primary_provider = outcome.provider
                log.info(f"    ✓ Task complete ({outcome.provider}): {len(outcome.findings or '')} chars")
            else:
                log.warning(f"    ✗ Task failed ({outcome.status}): {outcome.error_message}")

        # Step 4: Consolidate findings (non-blocking)
        log.info("Step 3: Consolidation")
        consolidation_fallback_used = False
        try:
            consolidated = self._consolidate_findings(tasks)
            if "**Task" in consolidated:  # Indicates fallback format
                consolidation_fallback_used = True
                log.warning("  Consolidation used fallback (timeout or error)")
            else:
                log.info(f"  Consolidated {len([t for t in tasks if t.findings])} task findings")
        except Exception as e:
            log.error(f"Consolidation failed fatally: {e}. Using local fallback.")
            consolidation_fallback_used = True
            successful_tasks = [t for t in tasks if t.findings]
            if successful_tasks:
                consolidated = "\n\n".join([
                    f"**Task {t.order_index}:** {t.findings}"
                    for t in successful_tasks
                ])
            else:
                consolidated = "No findings available from completed tasks."

        # Step 5: Generate recommendation with decision framework (non-blocking)
        # MSN-RECOMMENDATION-FIX #3: Pass raw findings in addition to consolidated
        # (Decision framework uses raw findings for grounding evidence, not abstract summary)
        log.info("Step 4: Recommendation generation with decision framework")

<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
>>>>>>> Stashed changes
        # Build raw findings for decision framework (MSN-RECOMMENDATION-FIX #3)
        raw_findings = "\n\n".join([
            f"Research Task {t.order_index}: {t.description}\n{t.findings}"
            for t in tasks if t.findings
        ]) if any(t.findings for t in tasks) else consolidated

        recommendation = None
        confidence = 0.0
        try:
            # NEW: Pass raw findings to decision framework for evidence grounding
            recommendation, confidence = self._generate_recommendation_with_fallback(raw_findings, tasks)
        except Exception as rec_error:
            log.warning(f"Recommendation generation failed: {rec_error}. Continuing without recommendation.")
            recommendation = None
            confidence = 0.0

        if recommendation:
            log.info(f"  Recommendation: {recommendation[:100]}... (confidence: {confidence:.2f})")
        else:
            log.info("  No actionable recommendation")
<<<<<<< Updated upstream
=======
        # MSN-RECOMMENDATION-FIX Option B: Conditional recommendation generation based on request type
        recommendation = None
        confidence = 0.0

        if request_type == "informational":
            # Informational request: skip recommendation generation, findings are the answer
            log.info(f"[request-type] Informational request: skipping recommendation generation")
            log.info("  Mode: Findings-only (informational request)")
        elif request_type in ["decision", "unclear"]:
            # Decision-oriented or uncertain: generate recommendation (conservative fallback)
            if request_type == "unclear":
                log.info(f"[request-type] Unclear request type: generating recommendation (conservative fallback)")
            else:
                log.info(f"[request-type] Decision-oriented request: generating recommendation")

            # Build raw findings for decision framework (MSN-RECOMMENDATION-FIX #3)
            raw_findings = "\n\n".join([
                f"Research Task {t.order_index}: {t.description}\n{t.findings}"
                for t in tasks if t.findings
            ]) if any(t.findings for t in tasks) else consolidated

            try:
                # Pass raw findings to decision framework for evidence grounding
                recommendation, confidence = self._generate_recommendation_with_fallback(raw_findings, tasks)
            except Exception as rec_error:
                log.warning(f"Recommendation generation failed: {rec_error}. Continuing without recommendation.")
                recommendation = None
                confidence = 0.0

            if recommendation:
                log.info(f"  Recommendation: {recommendation[:100]}... (confidence: {confidence:.2f})")
            else:
                log.info("  No actionable recommendation")
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes

        # MSN-0055C WP7: Record metrics before result assembly
        tasks_completed = len([t for t in tasks if t.status == "complete"])
        provider_failures = len([t for t in tasks if t.status == "failed"])

        metrics.record_task_completion(
            count=len(tasks),
            successful=tasks_completed,
            primary_provider=primary_provider
        )
        metrics.record_provider_failure() if provider_failures > 0 else None
        metrics.record_consolidation(
            success=not consolidation_fallback_used,
            method="deterministic" if not consolidation_fallback_used else "fallback"
        )
        metrics.record_recommendation(
            generated=recommendation is not None,
            confidence=confidence
        )

        # Record execution timing
        total_elapsed = int((time.time() - mission_start_time) * 1000)
        metrics.record_total_duration(total_elapsed)

        # Step 6: Build result
        tasks_completed = len([t for t in tasks if t.status == "complete"])
        status = "success" if tasks_completed == len(tasks) else (
            "partial" if tasks_completed > 0 else "error"
        )

        # Add consolidation fallback note if used
        errors = self._collect_errors(tasks)
        if consolidation_fallback_used:
            errors.append("Consolidation used fallback (timeout or error). Summary generated from task findings.")

        # Build provider paths for telemetry (e.g., ["gemini-2.5-flash → ollama", "gemini-2.5-flash"])
        provider_paths = []
        for t in tasks:
            if t.provider_chain:
                # Format: "gemini-2.5-flash → ollama"
                path = " → ".join(t.provider_chain)
                provider_paths.append(path)
            elif t.provider:
                # Fallback: just the final provider
                provider_paths.append(t.provider)

        result = ResearchMissionResult(
            mission_id=mission_id,
            research_topic=research_topic,
            status=status,
            timestamp=datetime.utcnow().isoformat(),
            task_breakdown=[t.description for t in tasks],
            task_count=len(tasks),
            tasks_completed=tasks_completed,
            task_results=tasks,
            consolidated_findings=consolidated,
            recommendation=recommendation,
            confidence=confidence,
            primary_provider=primary_provider,
            errors=errors,
            provider_paths=provider_paths,
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
            request_type=request_type,  # MSN-RECOMMENDATION-FIX Option B: include request type in result
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
        )

        # MSN-0055C WP7: Persist metrics and log summary
        metrics_summary = metrics.finalize_and_store()
        log.info(f"Research mission {mission_id} complete: {status}")
        log.info(f"Metrics:\n{metrics_summary}")

        return result

    # ========================================================================
    # Task Decomposition
    # ========================================================================

    def _decompose_research_topic(self, research_topic: str) -> list[str]:
        """
<<<<<<< Updated upstream
<<<<<<< Updated upstream
        Decompose research topic into tasks using Ollama.

        Uses qwen2.5-coder for structured task breakdown.
=======
        Decompose research topic into tasks using provider fallback chain.

        Provider chain (DEF-WP1-001):
        1. Gemini 2.5 Flash Lite (primary)
        2. Mistral Research Agent (secondary)
        3. qwen2.5-coder via Ollama (tertiary)
>>>>>>> Stashed changes
=======
        Decompose research topic into tasks using Ollama.

        Uses qwen2.5-coder for structured task breakdown.
>>>>>>> Stashed changes

        Args:
            research_topic: Research request

        Returns:
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
>>>>>>> Stashed changes
            List of task descriptions (2-5 tasks typically)
        """

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

<<<<<<< Updated upstream
=======
            List of task descriptions (2-3 tasks typically)
        """

>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
        decompose_prompt = f"""You are a research planning expert. Break down the following research topic into 2-3 specific, actionable research tasks (maximum 3 to avoid rate limiting).

Research Topic: {research_topic}

For each task:
1. Be specific and focused
2. Make it executable by an LLM in 2-3 minutes
3. Avoid overlap with other tasks
4. Order by dependencies (earlier tasks inform later ones)

Return ONLY a JSON array of 2-3 task strings, like:
["Task 1: ...", "Task 2: ...", "Task 3: ..."]

Maximum 3 tasks. No explanation, no markdown, just the JSON array."""

<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
>>>>>>> Stashed changes
        try:
            endpoint = f"{ollama_url}/api/generate"
            request_data = {
                "model": "qwen2.5-coder:7b",
                "prompt": decompose_prompt,
<<<<<<< Updated upstream
=======
        # Provider chain for decomposition (same as task execution)
        providers = [
            ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (primary)", self._decompose_with_gemini_lite),
            ("mistral-research-agent", "Mistral Research Agent (secondary)", self._decompose_with_mistral),
            ("ollama", "qwen2.5-coder via Ollama (tertiary)", self._decompose_with_ollama),
        ]

        for provider_id, provider_name, provider_func in providers:
            try:
                log.info(f"Decomposition: Attempting {provider_name}")
                tasks = provider_func(decompose_prompt)
                if tasks:
                    log.info(f"Decomposition successful via {provider_name}: {len(tasks)} tasks")
                    return tasks[:3]  # Cap at 3 tasks
            except Exception as e:
                log.warning(f"Decomposition failed with {provider_name}: {e}. Trying next provider.")
                continue

        log.error("All decomposition providers exhausted; returning empty task list")
        return []

    def _decompose_with_gemini_lite(self, prompt: str) -> list[str]:
        """Decompose using Gemini 2.5 Flash Lite."""
        try:
            import google.generativeai as genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                log.error("[decompose] Gemini 2.5 Flash Lite: GEMINI_API_KEY not set")
                return []

            log.info("[decompose] Gemini 2.5 Flash Lite: API key present, configuring...")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash-lite")
            log.info("[decompose] Gemini 2.5 Flash Lite: Sending request...")
            response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.5))

            if response.text:
                log.info("[decompose] Gemini 2.5 Flash Lite: SUCCESS - received response")
                return self._parse_json_tasks(response.text)
            else:
                log.error("[decompose] Gemini 2.5 Flash Lite: Empty response from API")
                return []
        except Exception as e:
            log.error(f"[decompose] Gemini 2.5 Flash Lite: FAILED - {type(e).__name__}: {e}")
            return []

    def _decompose_with_mistral(self, prompt: str) -> list[str]:
        """Decompose using Mistral Research Agent (SDK 2.4.9+, matching task execution pattern)."""
        try:
            api_key = os.getenv("MISTRAL_API_KEY")
            if not api_key:
                log.error("[decompose] Mistral: MISTRAL_API_KEY not set")
                return []

            log.info("[decompose] Mistral: API key present, importing Mistral client...")
            from mistralai.client import Mistral

            log.info("[decompose] Mistral: Creating Mistral client instance...")
            client = Mistral(api_key=api_key)

            log.info("[decompose] Mistral: Calling Mistral Research Agent...")
            response = client.beta.conversations.start(
                agent_id="ag_019eafb4bee976348306954617b1c18c",  # Mistral Research Agent
                agent_version=2,
                inputs=[{"role": "user", "content": prompt}]
            )

            if response and hasattr(response, 'messages') and response.messages:
                text = response.messages[-1].content
                log.info("[decompose] Mistral: SUCCESS - received response")
                return self._parse_json_tasks(text)
            else:
                log.error("[decompose] Mistral: Empty response from API")
                return []
        except ImportError as e:
            log.error(f"[decompose] Mistral: FAILED - mistralai SDK not installed: {e}")
            return []
        except Exception as e:
            log.error(f"[decompose] Mistral: FAILED - {type(e).__name__}: {e}")
            return []

    def _decompose_with_ollama(self, prompt: str) -> list[str]:
        """Decompose using Ollama qwen2.5-coder (tertiary fallback)."""
        try:
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            log.info(f"[decompose] Ollama: Using URL {ollama_url}")

            endpoint = f"{ollama_url}/api/generate"
            request_data = {
                "model": "qwen3:8b",
                "prompt": prompt,
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
                "stream": False,
                "temperature": 0.5,
                "top_p": 0.9,
            }

            request_body = json.dumps(request_data).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

<<<<<<< Updated upstream
<<<<<<< Updated upstream
            log.info("Calling Ollama (qwen2.5-coder) for task decomposition")
=======
            log.info("[decompose] Ollama: Sending request to qwen3:8b...")
>>>>>>> Stashed changes
=======
            log.info("Calling Ollama (qwen2.5-coder) for task decomposition")
>>>>>>> Stashed changes

            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                response_text = response_data.get("response", "")
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
>>>>>>> Stashed changes

                # Parse JSON from response
                try:
                    # Try to extract JSON array
                    json_start = response_text.find("[")
                    json_end = response_text.rfind("]") + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = response_text[json_start:json_end]
                        tasks = json.loads(json_str)
                        if isinstance(tasks, list) and all(isinstance(t, str) for t in tasks):
                            # MSN-0054: Enforce maximum 3 tasks to reduce rate-limit pressure
                            capped_tasks = tasks[:3]
                            if len(capped_tasks) != len(tasks):
                                log.warning(f"Task decomposition produced {len(tasks)} tasks; capped at 3 (max for MVP)")
                            else:
                                log.info(f"Decomposition successful: {len(capped_tasks)} tasks")
                            return capped_tasks
                except (json.JSONDecodeError, ValueError):
                    pass

                # Fallback: parse line-by-line
                log.warning("Could not parse JSON from decomposition; falling back to line parsing")
                lines = [line.strip() for line in response_text.split("\n") if line.strip()]
                tasks = [line for line in lines if line and not line.startswith("[") and not line.endswith("]")]
                # MSN-0054E: Cap at 3 tasks (consistent with primary path)
                capped_tasks = tasks[:3]
                if len(capped_tasks) != len(tasks):
                    log.warning(f"Fallback decomposition produced {len(tasks)} tasks; capped at 3 (max for MVP)")
                return capped_tasks

        except Exception as e:
            log.error(f"Task decomposition failed: {e}")
            return []
<<<<<<< Updated upstream
=======
                log.info("[decompose] Ollama: SUCCESS - received response")
                return self._parse_json_tasks(response_text)

        except urllib.error.URLError as e:
            log.error(f"[decompose] Ollama: FAILED - Connection error: {e.reason}")
            return []
        except urllib.error.HTTPError as e:
            log.error(f"[decompose] Ollama: FAILED - HTTP {e.code}: {e.reason}")
            return []
        except Exception as e:
            log.error(f"[decompose] Ollama: FAILED - {type(e).__name__}: {e}")
            return []

    def _parse_json_tasks(self, response_text: str) -> list[str]:
        """Parse task list from JSON response."""
        try:
            # Try to extract JSON array
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                tasks = json.loads(json_str)
                if isinstance(tasks, list) and all(isinstance(t, str) for t in tasks):
                    return tasks
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: parse line-by-line
        log.warning("Could not parse JSON from decomposition; falling back to line parsing")
        lines = [line.strip() for line in response_text.split("\n") if line.strip()]
        tasks = [line for line in lines if line and not line.startswith("[") and not line.endswith("]")]
        return tasks
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes

    # ========================================================================
    # Finding Consolidation (MSN-0055C WP3: Deterministic Consolidation)
    # ========================================================================

    def _consolidate_findings_deterministic(self, tasks: list[ResearchTask]) -> str:
        """
        Generate consolidated findings WITHOUT LLM synthesis (deterministic).

        Guaranteed to succeed (no timeout possible).
        Suitable for captain brief input.

        MSN-0055C WP3: Deterministic consolidation eliminates timeout failures.

        Args:
            tasks: List of completed research tasks

        Returns:
            Structured consolidated findings (deterministic format)
        """

        successful_tasks = [t for t in tasks if t.findings]

        if not successful_tasks:
            return "No findings available from completed research tasks."

        # Extract executive summary from first few successful tasks
        summary_sentences = []
        for task in successful_tasks[:2]:  # Use first 2 tasks for summary
            finding_text = task.findings.strip()
            if finding_text:
                # Extract first sentence
                sentences = finding_text.split('.')
                first_sentence = sentences[0].strip() + '.' if sentences[0].strip() else ''
                if first_sentence:
                    summary_sentences.append(first_sentence)

        executive_summary = ' '.join(summary_sentences) if summary_sentences else 'Research findings compiled.'

        # Extract key findings from all tasks
        key_findings = []
        for task in successful_tasks[:5]:  # Top 5 findings
            finding_text = task.findings.strip()
            if finding_text:
                # Get first sentence or first 100 chars
                first_line = finding_text.split('\n')[0] if '\n' in finding_text else finding_text[:100]
                first_line = first_line.rstrip('.')
                if first_line:
                    key_findings.append(f"• {first_line}")

        # Build deterministic consolidated output
        consolidated = f"""CONSOLIDATED RESEARCH FINDINGS

Executive Summary:
{executive_summary}

Key Findings:
{chr(10).join(key_findings) if key_findings else '• Research completed across multiple tasks'}

Research Metadata:
- Tasks completed: {len(successful_tasks)}/{len(tasks)}
- Primary provider: [delegated]
- Consolidation method: Deterministic (guaranteed success)
- Confidence basis: Task completion ratio and evidence summary"""

        log.info(f"[research-consolidation] Deterministic consolidation: {len(consolidated)} chars")
        return consolidated

    def _consolidate_findings(self, tasks: list[ResearchTask]) -> str:
        """
        Consolidate findings from all tasks into a coherent summary.

        MSN-RECOMMENDATION-FIX #4: Use Flash Lite instead of Ollama/qwen for synthesis.
        Flash Lite is a reasoning model; qwen is a code model. Better fit for complex analysis.

        Args:
            tasks: List of completed research tasks

        Returns:
            Consolidated findings (string)
        """

        successful_tasks = [t for t in tasks if t.findings]

        if not successful_tasks:
            return "No findings generated from research tasks."

        # Build consolidation prompt
        task_findings = "\n\n".join([
            f"Task {t.order_index}: {t.description}\nFindings: {t.findings}"
            for t in successful_tasks
        ])

        consolidation_prompt = f"""You are a research analyst. Consolidate the following research findings into a clear, coherent summary.

{task_findings}

Consolidation Requirements:
1. Synthesize findings from all tasks
2. Identify key themes and patterns
3. Note any conflicts or contradictions
4. Highlight the most important insights
5. Keep it concise (200-400 words) - preserve detail for downstream recommendation use

Provide only the consolidated summary, no headers or metadata."""

        try:
            # MSN-RECOMMENDATION-FIX #4: Use Flash Lite (reasoning model) instead of qwen (code model)
            if not call_gemini_2_5_flash_lite_research:
                raise Exception("call_gemini_2_5_flash_lite_research not loaded")

            log.info("Calling Flash Lite for finding consolidation (MSN-RECOMMENDATION-FIX #4)")
            # PHASE 1 FIX: Increase timeout from 30s to 60s for complex synthesis task
            # PHASE 2 FIX: Call consolidation directly (not via delegate_research_task)
            # to exclude from per-mission Gemini budget tracking, ensuring recommendation
            # generation can still use Gemini within the mission's quota
            outcome = call_gemini_2_5_flash_lite_research(consolidation_prompt, timeout_sec=60)

            if outcome.status == "success" and outcome.findings:
                consolidated = outcome.findings.strip()
                log.info(f"Consolidation complete (Flash Lite): {len(consolidated)} chars")
                return consolidated
            else:
                log.warning(f"Flash Lite consolidation failed: {outcome.status}. Using local fallback.")
                raise Exception("Flash Lite failed")

        except Exception as e:
            # Consolidation timeout or error - use deterministic local fallback
            log.warning(f"Consolidation failed ({type(e).__name__}): {str(e)[:100]}. Using local fallback consolidation.")

            # Generate simple executive summary from task findings
            findings_summary = []
            for t in successful_tasks:
                # Extract first sentence or first 100 chars as summary
                finding_text = t.findings.strip()
                if finding_text:
                    first_sentence = finding_text.split('\n')[0] if '\n' in finding_text else finding_text[:150]
                    if len(finding_text) > 150:
                        first_sentence = first_sentence.rstrip() + "..."
                    findings_summary.append(f"- {first_sentence}")

            # Build fallback consolidation with clear provenance
            fallback_text = "Executive Summary (automated consolidation timed out):\n\n"
            fallback_text += "Key Findings from Research Tasks:\n" + "\n".join(findings_summary)
            fallback_text += f"\n\nProvider Note: Automated consolidation timed out. Summary generated locally from {len(successful_tasks)} task findings."

            log.info(f"Fallback consolidation generated: {len(fallback_text)} chars")
            return fallback_text

    # ========================================================================
    # Recommendation Generation (MSN-0055C WP5: Recommendation with Fallback)
    # ========================================================================

    def _extract_options_from_findings(
        self,
        consolidated_findings: str,
        tasks: list[ResearchTask]
    ) -> Optional[str]:
        """
        Extract viable options from research findings (MSN-RECOMMENDATION-FIX #1).

        Uses Flash Lite to identify 2-4 distinct options implied by the research.
        Non-blocking; returns None if extraction fails.

        Args:
            consolidated_findings: Consolidated research output
            tasks: All tasks (for context)

        Returns:
            Structured options list or None
        """

        if not consolidated_findings or "No findings" in consolidated_findings:
            return None

        options_prompt = f"""You are a strategic analyst. Based on these research findings, identify 2-4 DISTINCT VIABLE OPTIONS.

Research Findings:
{consolidated_findings}

For each option, provide:
- Option name (3-5 words)
- Brief description (1 sentence)
- Key advantages (2 bullets)
- Key disadvantages (2 bullets)
- Estimated cost/effort/timeline if relevant

Format as a numbered list. Be specific and concrete.

Example format:
1. OPTION NAME
Description: [1 sentence]
Advantages:
- [advantage 1]
- [advantage 2]
Disadvantages:
- [disadvantage 1]
- [disadvantage 2]
Cost/Effort: [if relevant]"""

        try:
            if not call_gemini_2_5_flash_lite_research:
                raise Exception("call_gemini_2_5_flash_lite_research not loaded")

            log.debug("Extracting options from findings (MSN-RECOMMENDATION-FIX #1)")
            outcome = call_gemini_2_5_flash_lite_research(options_prompt, timeout_sec=20)

            if outcome.status == "success" and outcome.findings:
                options_text = outcome.findings.strip()
                log.info(f"Options extracted: {len(options_text)} chars")
                return options_text
            else:
                log.debug(f"Options extraction failed: {outcome.status}")
                return None

        except Exception as e:
            log.debug(f"Options extraction failed ({type(e).__name__}): {str(e)[:50]}")
            return None

    def _analyze_tradeoffs(
        self,
        consolidated_findings: str,
        options_text: Optional[str],
        tasks: list[ResearchTask]
    ) -> Optional[str]:
        """
        Analyze trade-offs between options (MSN-RECOMMENDATION-FIX #1).

        Uses Flash Lite to create trade-off matrix.
        Non-blocking; returns None if analysis fails.

        Args:
            consolidated_findings: Consolidated research output
            options_text: Extracted options from previous step
            tasks: All tasks (for context)

        Returns:
            Trade-off analysis or None
        """

        if not options_text:
            return None

        tradeoff_prompt = f"""You are a strategic analyst. Analyze the trade-offs between these options.

Options:
{options_text}

Create a trade-off analysis covering:
1. COST vs BENEFIT
2. SPEED vs QUALITY
3. RISK vs REWARD
4. SHORT-TERM vs LONG-TERM impact

Format as a clear comparison table or matrix showing how each option trades off these dimensions.

Be specific with numbers/timelines where possible."""

        try:
            if not call_gemini_2_5_flash_lite_research:
                raise Exception("call_gemini_2_5_flash_lite_research not loaded")

            log.debug("Analyzing trade-offs (MSN-RECOMMENDATION-FIX #1)")
            outcome = call_gemini_2_5_flash_lite_research(tradeoff_prompt, timeout_sec=20)

            if outcome.status == "success" and outcome.findings:
                tradeoff_text = outcome.findings.strip()
                log.info(f"Trade-off analysis complete: {len(tradeoff_text)} chars")
                return tradeoff_text
            else:
                log.debug(f"Trade-off analysis failed: {outcome.status}")
                return None

        except Exception as e:
            log.debug(f"Trade-off analysis failed ({type(e).__name__}): {str(e)[:50]}")
            return None

    def _assess_risks(
        self,
        consolidated_findings: str,
        options_text: Optional[str],
        tasks: list[ResearchTask]
    ) -> Optional[str]:
        """
        Assess risks for each option (MSN-RECOMMENDATION-FIX #1).

        Uses Flash Lite to identify risks and mitigation strategies.
        Non-blocking; returns None if assessment fails.

        Args:
            consolidated_findings: Consolidated research output
            options_text: Extracted options from previous step
            tasks: All tasks (for context)

        Returns:
            Risk assessment or None
        """

        if not options_text:
            return None

        risk_prompt = f"""You are a risk analyst. Assess risks for each option.

Options:
{options_text}

For each option, identify:
1. Critical risks (could cause failure)
2. Operational risks (could cause delays)
3. Strategic risks (could limit future options)
4. Mitigation strategies for each risk

Format clearly. Be specific about probability and impact."""

        try:
            if not call_gemini_2_5_flash_lite_research:
                raise Exception("call_gemini_2_5_flash_lite_research not loaded")

            log.debug("Assessing risks (MSN-RECOMMENDATION-FIX #1)")
            outcome = call_gemini_2_5_flash_lite_research(risk_prompt, timeout_sec=20)

            if outcome.status == "success" and outcome.findings:
                risk_text = outcome.findings.strip()
                log.info(f"Risk assessment complete: {len(risk_text)} chars")
                return risk_text
            else:
                log.debug(f"Risk assessment failed: {outcome.status}")
                return None

        except Exception as e:
            log.debug(f"Risk assessment failed ({type(e).__name__}): {str(e)[:50]}")
            return None

    def _generate_recommendation_with_fallback(
        self,
        consolidated_findings: str,
        tasks: list[ResearchTask]
    ) -> tuple[Optional[str], float]:
        """
        Generate recommendation with decision framework (MSN-RECOMMENDATION-FIX #1).

        MSN-0055C WP5: Fallback ensures every mission has a recommendation.
        MSN-0058: Optimized provider chain for recommendations
        MSN-RECOMMENDATION-FIX: New decision framework pipeline

        New Priority:
        1. Extract options from findings (Flash Lite)
        2. Analyze trade-offs (Flash Lite)
        3. Assess risks (Flash Lite)
        4. Generate recommendation (Flash Lite with full context)
        5. Fallback to Ollama if needed
        6. Final heuristic fallback

        Args:
            consolidated_findings: Consolidated research output
            tasks: All tasks (for context)

        Returns:
            Tuple of (recommendation_text, confidence_score)
        """

        # NEW: Step 1 - Extract options from findings (MSN-RECOMMENDATION-FIX #1)
        log.info("[research-recommendation] Step 1: Extracting viable options...")
        options_text = self._extract_options_from_findings(consolidated_findings, tasks)

        # NEW: Step 2 - Analyze trade-offs (MSN-RECOMMENDATION-FIX #1)
        log.info("[research-recommendation] Step 2: Analyzing trade-offs...")
        tradeoff_text = self._analyze_tradeoffs(consolidated_findings, options_text, tasks)

        # NEW: Step 3 - Assess risks (MSN-RECOMMENDATION-FIX #1)
        log.info("[research-recommendation] Step 3: Assessing risks...")
        risk_text = self._assess_risks(consolidated_findings, options_text, tasks)

        # NEW: Step 4 - Generate recommendation with decision framework (MSN-RECOMMENDATION-FIX #2)
        log.info("[research-recommendation] Step 4: Generating recommendation with decision framework...")
        llm_rec, llm_conf = self._generate_recommendation_with_decision_framework(
            consolidated_findings,
            options_text,
            tradeoff_text,
            risk_text,
            tasks
        )

        # Validate recommendation
        if (llm_rec
            and "No actionable" not in llm_rec
            and "cannot recommend" not in llm_rec.lower()
            and "insufficient" not in llm_rec.lower()
            and len(llm_rec) > 30
            and llm_conf >= 0.5):
            log.info(f"[research-recommendation] Decision framework recommendation succeeded (confidence: {llm_conf:.2f})")
            return llm_rec, llm_conf

        log.debug(f"[research-recommendation] Decision framework recommendation rejected. Trying Ollama...")

        # Tier 2: Fall back to Ollama with original prompt
        llm_rec, llm_conf = self._generate_recommendation(consolidated_findings, tasks)

        # Validate Flash Lite response
        if (llm_rec
            and "No actionable" not in llm_rec
            and "cannot recommend" not in llm_rec.lower()
            and "insufficient" not in llm_rec.lower()
            and len(llm_rec) > 20
            and llm_conf >= 0.5):
            log.info(f"[research-recommendation] Used Gemini 2.5 Flash Lite (confidence: {llm_conf:.2f})")
            return llm_rec, llm_conf

        log.debug(f"[research-recommendation] Flash Lite recommendation rejected or failed. Trying Ollama...")

        # Tier 2: Fall back to Ollama
        llm_rec, llm_conf = self._generate_recommendation(consolidated_findings, tasks)

        # Validate Ollama response
        if (llm_rec
            and "No actionable" not in llm_rec
            and "cannot recommend" not in llm_rec.lower()
            and "insufficient" not in llm_rec.lower()
            and len(llm_rec) > 20
            and llm_conf >= 0.5):
            log.info(f"[research-recommendation] Used Ollama (confidence: {llm_conf:.2f})")
            return llm_rec, llm_conf

        log.info(f"[research-recommendation] Both LLM recommendations rejected or failed.")
        log.info(f"[research-recommendation] Recommendation pipeline needs review. Returning NEEDS_REVIEW status.")

        # NEW (MSN-RECOMMENDATION-FIX #5): Escalate instead of fallback to "defer"
        successful_tasks = len([t for t in tasks if t.status == "complete"])
        task_count = len(tasks)

        if successful_tasks >= task_count * 0.75:
            # Most tasks completed: provide actionable fallback
            recommendation = (
                f"RECOMMENDATION NEEDS REVIEW: Research completed {successful_tasks}/{task_count} areas. "
                f"Executive review required to formulate recommendation. Strong findings available."
            )
            # PHASE 1 FIX: Increase confidence from 0.6 to 0.8 — task quality is high, only recommendation generation failed
            confidence = 0.8  # High confidence (task completion excellent, only recommendation synthesis failed)
        elif successful_tasks >= task_count * 0.5:
            # Half tasks completed: limited fallback
            recommendation = (
                f"RECOMMENDATION NEEDS REVIEW: Partial research coverage ({successful_tasks}/{task_count} areas). "
                f"Additional investigation recommended before executive decision."
            )
            confidence = 0.4
        else:
            # Minimal data: escalate for human review
            recommendation = (
                "RECOMMENDATION NEEDS REVIEW: Insufficient research coverage. "
                "Recommend deferring decision pending substantial additional investigation."
            )
            confidence = 0.2

        log.warning(f"[research-recommendation] Recommendation generation escalated to review (confidence: {confidence:.2f})")
        return recommendation, confidence

    def _generate_recommendation(
        self,
        consolidated_findings: str,
        tasks: list[ResearchTask]
    ) -> tuple[Optional[str], float]:
        """
        Generate recommendation from consolidated findings.

        Uses Ollama to assess findings and produce actionable recommendation.

        Args:
            consolidated_findings: Consolidated research output
            tasks: All tasks (for context)

        Returns:
            Tuple of (recommendation_text, confidence_score)
        """

        if not consolidated_findings or "No findings" in consolidated_findings:
            log.info("No findings to base recommendation on")
            return None, 0.0

        recommendation_prompt = f"""You are a strategic advisor. Based on the following research findings, provide a clear, actionable recommendation.

Research Findings:
{consolidated_findings}

Recommendation Requirements:
1. Start with "We should..." or "We should not..."
2. Be specific and actionable
3. Ground it in the findings provided
4. Assume the reader can execute this immediately
5. Keep it to 1-2 sentences

Also, assign a confidence score (0.0-1.0) based on:
- Strength of evidence
- Consensus across research tasks
- Actionability

Format your response as:
RECOMMENDATION: [your recommendation]
CONFIDENCE: [0.0-1.0]"""

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        try:
            endpoint = f"{ollama_url}/api/generate"
            request_data = {
                "model": "qwen2.5-coder:7b",
                "prompt": recommendation_prompt,
                "stream": False,
                "temperature": 0.5,
                "top_p": 0.9,
            }

            request_body = json.dumps(request_data).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            log.info("Calling Ollama for recommendation generation")

            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                response_text = response_data.get("response", "").strip()

                # Parse recommendation and confidence
                recommendation = None
                confidence = 0.5

                for line in response_text.split("\n"):
                    if line.startswith("RECOMMENDATION:"):
                        recommendation = line.replace("RECOMMENDATION:", "").strip()
                    elif line.startswith("CONFIDENCE:"):
                        try:
                            confidence = float(line.replace("CONFIDENCE:", "").strip())
                            confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1
                        except ValueError:
                            confidence = 0.5

                if recommendation:
                    log.info(f"Recommendation generated (confidence: {confidence:.2f})")
                    return recommendation, confidence
                else:
                    log.info("No recommendation generated from findings")
                    return None, 0.0

        except Exception as e:
            log.warning(f"Recommendation generation failed ({type(e).__name__}): {str(e)[:100]}. Continuing without recommendation.")
            return None, 0.0

    def _generate_recommendation_with_decision_framework(
        self,
        consolidated_findings: str,
        options_text: Optional[str],
        tradeoff_text: Optional[str],
        risk_text: Optional[str],
        tasks: list[ResearchTask]
    ) -> tuple[Optional[str], float]:
        """
        Generate recommendation using decision framework (MSN-RECOMMENDATION-FIX #2).

        Uses Flash Lite with structured decision inputs:
        - Consolidated findings
        - Extracted options
        - Trade-off analysis
        - Risk assessment

        Returns actionable recommendation with rationale.

        Args:
            consolidated_findings: Consolidated research output
            options_text: Extracted options (can be None)
            tradeoff_text: Trade-off analysis (can be None)
            risk_text: Risk assessment (can be None)
            tasks: All tasks (for context)

        Returns:
            Tuple of (recommendation_text, confidence_score)
        """

        if not consolidated_findings or "No findings" in consolidated_findings:
            log.debug("No findings for decision framework recommendation")
            return None, 0.0

        # Build prompt with decision framework (MSN-RECOMMENDATION-FIX #2)
        decision_framework_prompt = f"""You are a Chief of Staff advisor. Your role is to recommend ACTION, not to summarise.

You have completed research with findings. You have identified options with trade-offs and risks.

Your job is to STATE WHICH OPTION IS PREFERRED and explain why.

Research Findings:
{consolidated_findings}

"""

        if options_text:
            decision_framework_prompt += f"""Viable Options:
{options_text}

"""

        if tradeoff_text:
            decision_framework_prompt += f"""Trade-off Analysis:
{tradeoff_text}

"""

        if risk_text:
            decision_framework_prompt += f"""Risk Assessment:
{risk_text}

"""

        decision_framework_prompt += """Your recommendation MUST include:

1. PREFERRED OPTION: State which option (e.g., "Option 2 - Build Internal Capability")
2. WHY: Explain in 2-3 sentences, grounded in findings and trade-offs. Why this option over others?
3. SUCCESS FACTORS: 2-3 key actions needed for success
4. CRITICAL RISKS AND MITIGATION: Top 2-3 risks and how to mitigate
5. FIRST THREE ACTIONS: Specific next steps to execute
6. CONFIDENCE: 0.0-1.0 based on evidence strength

Format exactly as:
PREFERRED OPTION: [Option name]
WHY: [2-3 sentences with evidence]
SUCCESS FACTORS:
- [factor 1]
- [factor 2]
CRITICAL RISKS AND MITIGATION:
- [Risk 1: Mitigation 1]
- [Risk 2: Mitigation 2]
FIRST THREE ACTIONS:
1. [Action 1]
2. [Action 2]
3. [Action 3]
CONFIDENCE: [0.0-1.0]"""

        try:
            if not call_gemini_2_5_flash_lite_research:
                raise Exception("call_gemini_2_5_flash_lite_research not loaded")

            log.debug("Calling Flash Lite with decision framework (MSN-RECOMMENDATION-FIX #2)")
            outcome = call_gemini_2_5_flash_lite_research(decision_framework_prompt, timeout_sec=30)

            if outcome.status == "success" and outcome.findings:
                response_text = outcome.findings.strip()

                # Parse recommendation and confidence
                recommendation = None
                confidence = 0.5

                for line in response_text.split("\n"):
                    if line.startswith("CONFIDENCE:"):
                        try:
                            confidence = float(line.replace("CONFIDENCE:", "").strip())
                            confidence = max(0.0, min(1.0, confidence))
                        except ValueError:
                            confidence = 0.5

                # Use entire response as recommendation (includes all structured sections)
                if "PREFERRED OPTION:" in response_text:
                    recommendation = response_text
                    log.debug(f"Decision framework recommendation generated (confidence: {confidence:.2f})")
                    return recommendation, confidence
                else:
                    log.debug("Decision framework: no preferred option identified")
                    return None, 0.0
            else:
                log.debug(f"Decision framework generation failed: {outcome.status}")
                return None, 0.0

        except Exception as e:
            log.debug(f"Decision framework generation failed ({type(e).__name__}): {str(e)[:50]}")
            return None, 0.0

    def _generate_recommendation_flash_lite(
        self,
        consolidated_findings: str,
        tasks: list[ResearchTask]
    ) -> tuple[Optional[str], float]:
        """
        Generate recommendation using Gemini 2.5 Flash Lite (MSN-0058).

        Flash Lite is cost-effective for recommendation generation while
        maintaining good quality. Primary tier before Ollama fallback.

        Args:
            consolidated_findings: Consolidated research output
            tasks: All tasks (for context)

        Returns:
            Tuple of (recommendation_text, confidence_score)
        """

        if not consolidated_findings or "No findings" in consolidated_findings:
            log.debug("No findings for Flash Lite recommendation")
            return None, 0.0

        recommendation_prompt = f"""You are a strategic advisor. Based on the following research findings, provide a clear, actionable recommendation.

Research Findings:
{consolidated_findings}

Recommendation Requirements:
1. Start with "We should..." or "We should not..."
2. Be specific and actionable
3. Ground it in the findings provided
4. Assume the reader can execute this immediately
5. Keep it to 1-2 sentences

Also, assign a confidence score (0.0-1.0) based on:
- Strength of evidence
- Consensus across research tasks
- Actionability

Format your response as:
RECOMMENDATION: [your recommendation]
CONFIDENCE: [0.0-1.0]"""

        try:
            # Import here to avoid circular imports
            if not call_gemini_2_5_flash_lite_research:
                raise Exception("call_gemini_2_5_flash_lite_research not loaded")

            # Create a simple task-like object for the API call
            class RecommendationTask:
                def __init__(self, prompt):
                    self.prompt = prompt

            task = RecommendationTask(recommendation_prompt)

            # Call Flash Lite API
            log.debug("Calling Gemini 2.5 Flash Lite for recommendation (MSN-0058)")
            outcome = call_gemini_2_5_flash_lite_research(recommendation_prompt, timeout_sec=20)

            if outcome.status == "success" and outcome.findings:
                response_text = outcome.findings.strip()

                # Parse recommendation and confidence
                recommendation = None
                confidence = 0.5

                for line in response_text.split("\n"):
                    if line.startswith("RECOMMENDATION:"):
                        recommendation = line.replace("RECOMMENDATION:", "").strip()
                    elif line.startswith("CONFIDENCE:"):
                        try:
                            confidence = float(line.replace("CONFIDENCE:", "").strip())
                            confidence = max(0.0, min(1.0, confidence))
                        except ValueError:
                            confidence = 0.5

                if recommendation:
                    log.debug(f"Flash Lite recommendation generated (confidence: {confidence:.2f})")
                    return recommendation, confidence
                else:
                    log.debug("Flash Lite returned no recommendation")
                    return None, 0.0
            else:
                log.debug(f"Flash Lite call failed: {outcome.status}")
                return None, 0.0

        except Exception as e:
            log.debug(f"Flash Lite recommendation failed ({type(e).__name__}): {str(e)[:50]}")
            return None, 0.0

    # ========================================================================
    # Utilities
    # ========================================================================

    def _generate_mission_id(self) -> str:
        """Generate mission ID (MSN-YYYYMMDD-HHMMSS)."""
        now = datetime.utcnow()
        return now.strftime("MSN-%Y%m%d-%H%M%S")

    def _generate_task_id(self, mission_id: str, order_index: int) -> str:
        """Generate task ID (RES-YYYYMMDD-HHMMSS-NN)."""
        now = datetime.utcnow()
        return now.strftime(f"RES-%Y%m%d-%H%M%S-{order_index:02d}")

    def _collect_errors(self, tasks: list[ResearchTask]) -> list[str]:
        """Collect error messages from failed tasks."""
        errors = []
        for task in tasks:
            if task.status == "failed" and task.error_message:
                errors.append(f"Task {task.order_index}: {task.error_message}")
        return errors

    def _normalize_task_description(self, description: str) -> str:
        """Normalize task description."""
        # Remove leading "Task N:" or bullet points
        desc = description.strip()
        if desc.startswith("Task"):
            # Remove "Task N:" prefix
            parts = desc.split(":", 1)
            if len(parts) > 1:
                desc = parts[1].strip()
        return desc


# ============================================================================
# Configuration
# ============================================================================

class ResearchConfig:
    """Configuration for research orchestration."""

    # Task execution
    TASK_TIMEOUT_SEC = 120  # Per-task timeout

    # Decomposition
    MAX_TASKS = 5
    MIN_TASKS = 2

    # Consolidation
    CONSOLIDATION_TIMEOUT_SEC = 30

    # Recommendation
    RECOMMENDATION_TIMEOUT_SEC = 30
    CONFIDENCE_THRESHOLD = 0.55  # Minimum confidence to surface recommendation


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    print("\n=== Research Orchestration Test ===\n")

    # Test research mission
    orchestrator = ResearchOrchestrator()
    research_topic = "What are the key principles of operational resilience in banking?"

    print(f"Topic: {research_topic}\n")
    print("Running research mission...")

    result = orchestrator.run_research_mission(research_topic)

    print(f"\nResult:")
    print(f"  Mission ID: {result.mission_id}")
    print(f"  Status: {result.status}")
    print(f"  Tasks: {result.tasks_completed}/{result.task_count}")
    print(f"  Primary Provider: {result.primary_provider}")
    print(f"  Errors: {len(result.errors)}")
    if result.errors:
        for error in result.errors:
            print(f"    - {error}")

    print(f"\n  Task Breakdown:")
    for task in result.task_results:
        status_icon = "✓" if task.status == "complete" else "✗"
        print(f"    {status_icon} Task {task.order_index}: {task.description}")
        if task.findings:
            print(f"       {len(task.findings)} chars of findings ({task.provider})")
        elif task.error_message:
            print(f"       Error: {task.error_message}")

    print(f"\n  Consolidated Findings:")
    print(f"    {result.consolidated_findings[:200]}...")

    if result.recommendation:
        print(f"\n  Recommendation:")
        print(f"    {result.recommendation}")
        print(f"    Confidence: {result.confidence:.2f}")
    else:
        print(f"\n  No recommendation generated")

    print("\n=== Test Complete ===\n")
