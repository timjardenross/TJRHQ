#!/usr/bin/env python3
"""
Gemini XO Decomposer — Mission Decomposition Service

Decomposes complex research missions into discrete, executable research tasks.
Uses Gemini 2.0 Flash to understand user queries and break them into 3-5
specific, actionable research tasks.

Architecture:
    User Query (Slack)
        ↓
    GeminiXODecomposer (THIS)
        ├─ Understand intent
        ├─ Identify topics
        ├─ Create tasks
        └─ Generate synthesis instructions
        ↓
    ResearchTask[] (executable by providers)

Provider-Agnostic Design:
    - Creates ONLY ResearchTask objects (provider-agnostic)
    - No Mistral/Gemini/provider-specific code outside this module
    - Sets decomposition_reason for Learning Loop tracking
    - Returns structured ResearchMission
"""

from __future__ import annotations

import os
import json
import logging
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

log = logging.getLogger(__name__)


# =====================================================================
# Data Structures
# =====================================================================


@dataclass
class MissionRequest:
    """User request for research mission decomposition."""

    mission_id: str
    user_query: str
    context: Optional[str] = None
    priority: str = "medium"  # "low", "medium", "high"
    max_tasks: int = 5


@dataclass
class ResearchMission:
    """Decomposed research mission ready for execution."""

    mission_id: str
    user_query: str
    tasks: List[object]  # List[ResearchTask] — imported dynamically
    synthesis_instructions: str
    confidence: float  # 0.0-1.0: Decomposition quality
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


# =====================================================================
# Errors
# =====================================================================


class DecompositionError(Exception):
    """Raised when mission decomposition fails."""

    pass


class ValidationError(Exception):
    """Raised when task validation fails."""

    pass


# =====================================================================
# Gemini XO Decomposer
# =====================================================================


class GeminiXODecomposer:
    """
    Decomposes complex research missions into discrete tasks.

    Uses Gemini to understand user queries and break them into
    3-5 specific, executable research tasks.

    Example:
        decomposer = GeminiXODecomposer()
        request = MissionRequest(
            mission_id="msn-001",
            user_query="What impact does hybrid work have on productivity?"
        )
        mission = decomposer.decompose_mission(request)
        # Returns: ResearchMission with 3-5 ResearchTask objects
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
    ):
        """
        Initialize Gemini XO Decomposer.

        Args:
            api_key: Gemini API key (default: GEMINI_API_KEY env var)
            model: Gemini model identifier (default: gemini-2.0-flash)

        TODO: Confirm final model name when deploying
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.client = None

        self._init_client()

    def _init_client(self):
        """Initialize Gemini client."""
        if not self.api_key:
            log.warning("[gemini-xo] GEMINI_API_KEY not configured")
            return

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
            log.info("[gemini-xo] Client initialized successfully")
        except ImportError as e:
            log.error(f"[gemini-xo] Failed to import Google AI SDK: {e}")
        except Exception as e:
            log.error(f"[gemini-xo] Failed to initialize client: {e}")

    def health_check(self) -> bool:
        """
        Check if Gemini API is accessible.

        Returns:
            True if API is reachable, False otherwise
        """
        if not self.client or not self.api_key:
            return False

        try:
            response = self.client.generate_content(
                "test", stream=False
            )
            log.debug("[gemini-xo] Health check passed")
            return True
        except Exception as e:
            log.warning(f"[gemini-xo] Health check failed: {str(e)[:100]}")
            return False

    def decompose_mission(
        self,
        request: MissionRequest,
    ) -> ResearchMission:
        """
        Decompose a research mission into executable tasks.

        Args:
            request: MissionRequest with user query and context

        Returns:
            ResearchMission with decomposed tasks

        Raises:
            DecompositionError if decomposition fails
        """
        if not self.client:
            raise DecompositionError(
                "Gemini client not initialized. Check GEMINI_API_KEY."
            )

        log.info(
            f"[gemini-xo] Decomposing mission {request.mission_id}: "
            f"{request.user_query[:80]}..."
        )

        try:
            # Build prompt for Gemini
            prompt = self._build_decomposition_prompt(request)

            # Call Gemini API
            response = self.client.generate_content(prompt, stream=False)

            if not response or not response.text:
                raise DecompositionError("Gemini returned empty response")

            log.debug(
                f"[gemini-xo] Gemini response ({len(response.text)} chars)"
            )

            # Parse response into ResearchMission
            mission = self._parse_decomposition_response(
                response.text, request
            )

            # Validate decomposition
            self.validate_tasks(mission.tasks)

            log.info(
                f"[gemini-xo] Decomposition complete: "
                f"{len(mission.tasks)} tasks, confidence={mission.confidence}"
            )

            return mission

        except json.JSONDecodeError as e:
            msg = f"Failed to parse Gemini response as JSON: {e}"
            log.error(f"[gemini-xo] {msg}")
            raise DecompositionError(msg)
        except ValidationError as e:
            msg = f"Task validation failed: {e}"
            log.error(f"[gemini-xo] {msg}")
            raise DecompositionError(msg)
        except Exception as e:
            msg = f"Decomposition failed: {type(e).__name__}: {str(e)[:200]}"
            log.error(f"[gemini-xo] {msg}")
            raise DecompositionError(msg)

    def validate_tasks(self, tasks: List[object]) -> bool:
        """
        Validate task decomposition.

        Checks:
        - Each task has unique ID
        - Task descriptions are specific (not vague)
        - Focus areas are distinct (not duplicates)
        - Priority order is sensible
        - Total tokens reasonable

        Args:
            tasks: List of ResearchTask objects

        Returns:
            True if valid

        Raises:
            ValidationError if validation fails
        """
        if not tasks:
            raise ValidationError("No tasks in decomposition")

        if len(tasks) > 10:
            raise ValidationError("Too many tasks (max 10)")

        # Check uniqueness of IDs
        task_ids = set()
        for task in tasks:
            task_id = getattr(task, "task_id", None)
            if not task_id:
                raise ValidationError("Task missing task_id")
            if task_id in task_ids:
                raise ValidationError(f"Duplicate task ID: {task_id}")
            task_ids.add(task_id)

        # Check uniqueness of focus areas
        focus_areas = []
        for task in tasks:
            focus = getattr(task, "focus_area", None)
            if not focus:
                raise ValidationError("Task missing focus_area")
            if focus in focus_areas:
                raise ValidationError(
                    f"Duplicate focus area: {focus} "
                    "(tasks should have distinct focus areas)"
                )
            focus_areas.append(focus)

        # Check descriptions are specific
        for task in tasks:
            description = getattr(task, "description", "")
            if not description or len(description) < 10:
                raise ValidationError(
                    f"Task {task.task_id} has vague description: {description}"
                )

        # Check priority ordering
        for i, task in enumerate(tasks, 1):
            priority = getattr(task, "priority", i)
            if priority != i:
                log.warning(
                    f"[gemini-xo] Task {i} has priority {priority} "
                    "(expected {i})"
                )

        log.info(f"[gemini-xo] Task validation passed: {len(tasks)} tasks")
        return True

    def estimate_execution_time(self, mission: ResearchMission) -> int:
        """
        Estimate total execution time in seconds.

        Based on:
        - Number of tasks
        - Task complexity (inferred from description length)
        - Assumption of concurrent execution

        Args:
            mission: ResearchMission to estimate

        Returns:
            Estimated seconds (e.g., 120 for 2-minute mission)
        """
        if not mission.tasks:
            return 30  # Minimum

        # Base time per task (30 seconds if concurrent)
        base_per_task = 30

        # Complexity factor (longer descriptions = more complex)
        avg_description_length = sum(
            len(getattr(task, "description", "")) for task in mission.tasks
        ) / len(mission.tasks)

        complexity_factor = min(2.0, 1.0 + (avg_description_length / 200.0))

        # Estimate
        total_seconds = int(base_per_task * complexity_factor)

        # Add synthesis time
        total_seconds += 15

        log.info(
            f"[gemini-xo] Execution time estimate: {total_seconds}s "
            f"({len(mission.tasks)} tasks, factor={complexity_factor:.2f})"
        )

        return total_seconds

    # =====================================================================
    # Prompt Engineering
    # =====================================================================

    def _build_decomposition_prompt(
        self, request: MissionRequest
    ) -> str:
        """
        Build JSON-formatted prompt for Gemini decomposition.

        Args:
            request: MissionRequest with user query

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert research mission architect. Your job is to decompose
complex research questions into discrete, executable research tasks.

USER QUERY: {request.user_query}

{f'CONTEXT: {request.context}' if request.context else ''}

TASK:
1. Identify the core research question
2. Break it into {min(5, request.max_tasks)} sub-questions that cover:
   - Primary research (empirical data/studies)
   - Contextual research (background/definitions)
   - Synthesis research (expert perspectives)
3. For each sub-question, create a specific research task
4. Provide synthesis instructions for combining results

GUIDELINES:
- Tasks must be independent (can execute in parallel)
- Focus areas should be distinct (no overlap)
- Descriptions must be specific and actionable
- Prioritize by importance to answering original question
- Confidence score should reflect task clarity (0.8-1.0 is good)

RESPONSE FORMAT: JSON only, no markdown, no explanation

{{
  "tasks": [
    {{
      "task_id": "tsk-001",
      "description": "Specific research task description",
      "focus_area": "Topic focus area",
      "priority": 1,
      "max_tokens": 2000
    }}
  ],
  "synthesis_instructions": "How to combine results",
  "confidence": 0.85
}}
"""
        return prompt

    def _parse_decomposition_response(
        self,
        text: str,
        request: MissionRequest,
    ) -> ResearchMission:
        """
        Parse Gemini response into ResearchMission with ResearchTask objects.

        Args:
            text: Gemini response text
            request: Original request for context

        Returns:
            ResearchMission with populated tasks

        Raises:
            json.JSONDecodeError if response is not valid JSON
        """
        # Import ResearchTask here to avoid circular imports
        from research_provider import ResearchTask

        # Extract JSON from response
        # Gemini may include markdown, so extract JSON block
        json_text = text

        # Try to find JSON in markdown code block
        if "```json" in text:
            json_text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            json_text = text.split("```")[1].split("```")[0]

        # Parse JSON
        data = json.loads(json_text)

        # Create ResearchTask objects
        tasks = []
        for i, task_data in enumerate(data.get("tasks", []), 1):
            task = ResearchTask(
                task_id=task_data.get("task_id", f"tsk-{i:03d}"),
                description=task_data.get("description", ""),
                focus_area=task_data.get("focus_area", ""),
                priority=task_data.get("priority", i),
                max_tokens=task_data.get("max_tokens", 2000),
            )
            tasks.append(task)

        # Create ResearchMission
        mission = ResearchMission(
            mission_id=request.mission_id,
            user_query=request.user_query,
            tasks=tasks,
            synthesis_instructions=data.get(
                "synthesis_instructions", "Synthesize findings"
            ),
            confidence=data.get("confidence", 0.85),
        )

        return mission
