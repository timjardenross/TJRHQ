#!/usr/bin/env python3
"""
Unit tests for GeminiXODecomposer

Tests mission decomposition logic, validation, and error handling.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock

from gemini_xo_decomposer import (
    GeminiXODecomposer,
    MissionRequest,
    ResearchMission,
    DecompositionError,
    ValidationError,
)
from research_provider import ResearchTask


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def decomposer():
    """Create decomposer instance with mock client."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        decomposer = GeminiXODecomposer(api_key="test-key")
        decomposer.client = MagicMock()
        return decomposer


@pytest.fixture
def simple_request():
    """Simple query for testing."""
    return MissionRequest(
        mission_id="test-001",
        user_query="What is APRA CPS 230?",
    )


@pytest.fixture
def complex_request():
    """Complex query requiring multiple tasks."""
    return MissionRequest(
        mission_id="test-002",
        user_query="Does hybrid work improve productivity and team cohesion?",
        context="We're evaluating hybrid work policies for 2026",
        priority="high",
        max_tasks=4,
    )


@pytest.fixture
def mock_gemini_response_simple():
    """Mock Gemini response for simple query."""
    return """{
  "tasks": [
    {
      "task_id": "tsk-001",
      "description": "Provide overview of APRA CPS 230 and its regulatory purpose",
      "focus_area": "Regulatory overview",
      "priority": 1,
      "max_tokens": 2000
    },
    {
      "task_id": "tsk-002",
      "description": "List key requirements of APRA CPS 230",
      "focus_area": "Technical requirements",
      "priority": 2,
      "max_tokens": 2000
    },
    {
      "task_id": "tsk-003",
      "description": "Compare APRA CPS 230 to other regulatory frameworks",
      "focus_area": "Comparative analysis",
      "priority": 3,
      "max_tokens": 2000
    }
  ],
  "synthesis_instructions": "Combine into comprehensive overview",
  "confidence": 0.95
}"""


@pytest.fixture
def mock_gemini_response_complex():
    """Mock Gemini response for complex query."""
    return """{
  "tasks": [
    {
      "task_id": "tsk-001",
      "description": "Find recent peer-reviewed studies on hybrid work productivity metrics",
      "focus_area": "Productivity impact",
      "priority": 1,
      "max_tokens": 2000
    },
    {
      "task_id": "tsk-002",
      "description": "Research hybrid work impact on team collaboration and culture",
      "focus_area": "Team cohesion",
      "priority": 2,
      "max_tokens": 2000
    },
    {
      "task_id": "tsk-003",
      "description": "Identify industry best practices for hybrid work policies",
      "focus_area": "Policy context",
      "priority": 3,
      "max_tokens": 2000
    }
  ],
  "synthesis_instructions": "Address productivity and cohesion separately, note contradictions",
  "confidence": 0.85
}"""


# =====================================================================
# Test 1: Simple Query Decomposition
# =====================================================================


def test_decompose_simple_query(
    decomposer, simple_request, mock_gemini_response_simple
):
    """Test decomposition of simple query."""
    # Mock Gemini response
    mock_response = MagicMock()
    mock_response.text = mock_gemini_response_simple
    decomposer.client.generate_content.return_value = mock_response

    # Decompose
    mission = decomposer.decompose_mission(simple_request)

    # Verify structure
    assert mission.mission_id == "test-001"
    assert mission.user_query == "What is APRA CPS 230?"
    assert len(mission.tasks) == 3
    assert mission.confidence == 0.95

    # Verify tasks
    assert mission.tasks[0].task_id == "tsk-001"
    assert mission.tasks[0].priority == 1
    assert "APRA CPS 230" in mission.tasks[0].description

    # Verify synthesis instructions
    assert "comprehensive" in mission.synthesis_instructions.lower()


def test_decompose_complex_query(
    decomposer, complex_request, mock_gemini_response_complex
):
    """Test decomposition of complex query."""
    # Mock Gemini response
    mock_response = MagicMock()
    mock_response.text = mock_gemini_response_complex
    decomposer.client.generate_content.return_value = mock_response

    # Decompose
    mission = decomposer.decompose_mission(complex_request)

    # Verify structure
    assert mission.mission_id == "test-002"
    assert len(mission.tasks) == 3
    assert len(mission.tasks) <= complex_request.max_tasks

    # Verify focus areas are distinct
    focus_areas = [task.focus_area for task in mission.tasks]
    assert len(focus_areas) == len(set(focus_areas))

    # Verify tasks have unique IDs
    task_ids = [task.task_id for task in mission.tasks]
    assert len(task_ids) == len(set(task_ids))


# =====================================================================
# Test 2: Task Validation
# =====================================================================


def test_validate_tasks_success(decomposer):
    """Test validation of valid tasks."""
    tasks = [
        ResearchTask("t1", "Research X with specifics", "Focus A", 1),
        ResearchTask("t2", "Research Y with details", "Focus B", 2),
        ResearchTask("t3", "Research Z with context", "Focus C", 3),
    ]

    # Should not raise
    result = decomposer.validate_tasks(tasks)
    assert result is True


def test_validate_tasks_duplicate_ids(decomposer):
    """Test validation fails on duplicate task IDs."""
    tasks = [
        ResearchTask("t1", "Research X with details", "Focus A", 1),
        ResearchTask("t1", "Research Y with context", "Focus B", 2),  # Duplicate
    ]

    with pytest.raises(ValidationError, match="Duplicate task ID"):
        decomposer.validate_tasks(tasks)


def test_validate_tasks_duplicate_focus_areas(decomposer):
    """Test validation fails on duplicate focus areas."""
    tasks = [
        ResearchTask("t1", "Research X with details", "Focus A", 1),
        ResearchTask("t2", "Research Y with context", "Focus A", 2),  # Duplicate
    ]

    with pytest.raises(ValidationError, match="Duplicate focus area"):
        decomposer.validate_tasks(tasks)


def test_validate_tasks_vague_description(decomposer):
    """Test validation fails on vague descriptions."""
    tasks = [
        ResearchTask("t1", "X", "Focus A", 1),  # Too short
    ]

    with pytest.raises(ValidationError, match="vague description"):
        decomposer.validate_tasks(tasks)


def test_validate_tasks_empty(decomposer):
    """Test validation fails on empty task list."""
    with pytest.raises(ValidationError, match="No tasks"):
        decomposer.validate_tasks([])


def test_validate_tasks_too_many(decomposer):
    """Test validation fails when too many tasks."""
    tasks = [
        ResearchTask(f"t{i}", f"Research task {i} with details", f"Focus {i}", i)
        for i in range(15)  # More than max
    ]

    with pytest.raises(ValidationError, match="Too many tasks"):
        decomposer.validate_tasks(tasks)


# =====================================================================
# Test 3: Time Estimation
# =====================================================================


def test_estimate_execution_time_simple(decomposer, simple_request, mock_gemini_response_simple):
    """Test time estimation for simple query."""
    mock_response = MagicMock()
    mock_response.text = mock_gemini_response_simple
    decomposer.client.generate_content.return_value = mock_response

    mission = decomposer.decompose_mission(simple_request)
    time_estimate = decomposer.estimate_execution_time(mission)

    # Should be reasonable for 3 tasks
    assert 60 <= time_estimate <= 300  # 1-5 minutes


def test_estimate_execution_time_complex(decomposer, complex_request, mock_gemini_response_complex):
    """Test time estimation for complex query."""
    mock_response = MagicMock()
    mock_response.text = mock_gemini_response_complex
    decomposer.client.generate_content.return_value = mock_response

    mission = decomposer.decompose_mission(complex_request)
    time_estimate = decomposer.estimate_execution_time(mission)

    # Should account for task complexity
    assert 60 <= time_estimate <= 300


def test_estimate_execution_time_empty_mission(decomposer):
    """Test time estimation for empty mission."""
    mission = ResearchMission(
        mission_id="test",
        user_query="Test",
        tasks=[],
        synthesis_instructions="Test",
        confidence=0.9,
    )

    time_estimate = decomposer.estimate_execution_time(mission)
    assert time_estimate >= 30  # Minimum


# =====================================================================
# Test 4: Error Handling
# =====================================================================


def test_decompose_missing_client(simple_request):
    """Test decomposition fails when client not initialized."""
    decomposer = GeminiXODecomposer(api_key="invalid")
    decomposer.client = None

    with pytest.raises(DecompositionError, match="not initialized"):
        decomposer.decompose_mission(simple_request)


def test_decompose_api_error(decomposer, simple_request):
    """Test decomposition handles API errors gracefully."""
    decomposer.client.generate_content.side_effect = Exception("API Error")

    with pytest.raises(DecompositionError, match="Decomposition failed"):
        decomposer.decompose_mission(simple_request)


def test_decompose_invalid_json(decomposer, simple_request):
    """Test decomposition handles invalid JSON response."""
    mock_response = MagicMock()
    mock_response.text = "Not valid JSON"
    decomposer.client.generate_content.return_value = mock_response

    with pytest.raises(DecompositionError, match="parse"):
        decomposer.decompose_mission(simple_request)


def test_decompose_empty_response(decomposer, simple_request):
    """Test decomposition handles empty response."""
    mock_response = MagicMock()
    mock_response.text = None
    decomposer.client.generate_content.return_value = mock_response

    with pytest.raises(DecompositionError, match="empty response"):
        decomposer.decompose_mission(simple_request)


# =====================================================================
# Test 5: Health Check
# =====================================================================


def test_health_check_success(decomposer):
    """Test health check succeeds when API is available."""
    mock_response = MagicMock()
    decomposer.client.generate_content.return_value = mock_response

    result = decomposer.health_check()
    assert result is True


def test_health_check_api_error(decomposer):
    """Test health check fails when API errors."""
    decomposer.client.generate_content.side_effect = Exception("API Error")

    result = decomposer.health_check()
    assert result is False


def test_health_check_no_client(simple_request):
    """Test health check fails when client not initialized."""
    decomposer = GeminiXODecomposer(api_key="invalid")
    decomposer.client = None

    result = decomposer.health_check()
    assert result is False


def test_health_check_no_api_key(simple_request):
    """Test health check fails when API key not configured."""
    with patch.dict(os.environ, {}, clear=True):
        decomposer = GeminiXODecomposer(api_key=None)

    result = decomposer.health_check()
    assert result is False


# =====================================================================
# Test 6: Markdown Response Handling
# =====================================================================


def test_decompose_markdown_json_response(decomposer, simple_request):
    """Test decomposition handles Gemini's markdown-wrapped JSON."""
    # Gemini sometimes wraps JSON in markdown
    mock_response = MagicMock()
    mock_response.text = """Here's the decomposition:

```json
{
  "tasks": [
    {
      "task_id": "tsk-001",
      "description": "Overview of APRA CPS 230",
      "focus_area": "Regulatory overview",
      "priority": 1,
      "max_tokens": 2000
    }
  ],
  "synthesis_instructions": "Combine findings",
  "confidence": 0.9
}
```

This breaks down the topic."""
    decomposer.client.generate_content.return_value = mock_response

    # Should extract JSON from markdown
    mission = decomposer.decompose_mission(simple_request)
    assert len(mission.tasks) == 1
    assert mission.confidence == 0.9


# =====================================================================
# Run Tests
# =====================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
