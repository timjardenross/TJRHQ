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

log = logging.getLogger(__name__)

# Import existing research_delegator
# Dynamically discover and import from slack_bot/lib using importlib
import importlib.util

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
        _delegator_module = importlib.util.module_from_spec(_spec)
        # Register in sys.modules BEFORE exec_module to avoid dataclass issues
        sys.modules["research_delegator"] = _delegator_module
        _spec.loader.exec_module(_delegator_module)
        delegate_research_task = _delegator_module.delegate_research_task
        ResearchOutcome = _delegator_module.ResearchOutcome
        log.debug(f"Loaded research_delegator from {_research_delegator_file}")
    else:
        log.error(f"Could not create spec for research_delegator at {_research_delegator_file}")
except (ImportError, AttributeError, FileNotFoundError) as e:
    log.error(f"Failed to import research_delegator: {e}")


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["task_results"] = [t.to_dict() for t in self.task_results]
        return result


# ============================================================================
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
    ) -> ResearchMissionResult:
        """
        Execute complete research mission.

        Args:
            research_topic: What to research (10-1000 chars)
            mission_id: Optional mission ID; generated if not provided

        Returns:
            ResearchMissionResult with all findings and metadata
        """

        # Generate mission ID if not provided
        if not mission_id:
            mission_id = self._generate_mission_id()

        log.info(f"Starting research mission {mission_id}: {research_topic[:80]}...")

        # Step 1: Decompose into tasks
        log.info("Step 1: Task decomposition (Ollama)")
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

            outcome = delegate_research_task(
                task.description,
                timeout_sec=self.config.TASK_TIMEOUT_SEC
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

        # Step 5: Generate recommendation (non-blocking, skipped if consolidation failed)
        log.info("Step 4: Recommendation generation")
        recommendation = None
        confidence = 0.0
        try:
            recommendation, confidence = self._generate_recommendation(consolidated, tasks)
        except Exception as rec_error:
            log.warning(f"Recommendation generation failed: {rec_error}. Continuing without recommendation.")
            recommendation = None
            confidence = 0.0

        if recommendation:
            log.info(f"  Recommendation: {recommendation[:100]}... (confidence: {confidence:.2f})")
        else:
            log.info("  No actionable recommendation")

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
        )

        log.info(f"Research mission {mission_id} complete: {status}")
        return result

    # ========================================================================
    # Task Decomposition
    # ========================================================================

    def _decompose_research_topic(self, research_topic: str) -> list[str]:
        """
        Decompose research topic into tasks using Ollama.

        Uses qwen2.5-coder for structured task breakdown.

        Args:
            research_topic: Research request

        Returns:
            List of task descriptions (2-5 tasks typically)
        """

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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

        try:
            endpoint = f"{ollama_url}/api/generate"
            request_data = {
                "model": "qwen2.5-coder:7b",
                "prompt": decompose_prompt,
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

            log.info("Calling Ollama (qwen2.5-coder) for task decomposition")

            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                response_text = response_data.get("response", "")

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

    # ========================================================================
    # Finding Consolidation
    # ========================================================================

    def _consolidate_findings(self, tasks: list[ResearchTask]) -> str:
        """
        Consolidate findings from all tasks into a coherent summary.

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
5. Keep it concise (150-300 words)

Provide only the consolidated summary, no headers or metadata."""

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        try:
            endpoint = f"{ollama_url}/api/generate"
            request_data = {
                "model": "qwen2.5-coder:7b",
                "prompt": consolidation_prompt,
                "stream": False,
                "temperature": 0.6,
                "top_p": 0.9,
            }

            request_body = json.dumps(request_data).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            log.info("Calling Ollama for finding consolidation")

            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                consolidated = response_data.get("response", "").strip()
                log.info(f"Consolidation complete: {len(consolidated)} chars")
                return consolidated

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
    # Recommendation Generation
    # ========================================================================

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
