#!/usr/bin/env python3
"""
MSN-0060B Phase B1A: Decision Capture Test Harness

Comprehensive test suite for learning loop decision capture functionality.
Tests: record_decision(), get_decision(), get_decisions_for_mission()
       Provider metadata capture, audit trail, data persistence

Authority: MSN-0060B-LEARNING-LOOP-IMPLEMENTATION.md Phase B1A
"""

import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'slack-bot'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from slack_bot.lib.learning_loop_service import (
    LearningLoopService,
    DecisionRecord,
    ProviderMetadata,
)

log = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for testing."""
    client = Mock()
    client.insert = Mock(return_value=Mock(data=None))
    client.select = Mock(return_value=Mock(data=[]))
    client.query = Mock(return_value=[])
    return client


@pytest.fixture
def learning_loop_service(mock_supabase_client):
    """Initialize learning loop service with mock client."""
    return LearningLoopService(supabase_client=mock_supabase_client)


@pytest.fixture
def sample_provider_metadata():
    """Sample provider metadata for testing."""
    return ProviderMetadata(
        provider_name="google",
        model_name="gemini-2.5-flash",
        provider_route="primary",
        research_execution_id="RES-20260610-150000",
    )


# =============================================================================
# TEST SUITE 1: BASIC DECISION RECORDING (B1A Requirement)
# =============================================================================

class TestDecisionRecording:
    """Test basic decision recording functionality."""

    def test_record_decision_minimal_required_fields(self, learning_loop_service, mock_supabase_client):
        """
        B1A Requirement: Decision can be recorded via API
        Test: Record decision with only required fields
        """
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        assert decision is not None
        assert decision.mission_id == "MSN-0055B"
        assert decision.recommendation_id == "REC-20260610-150000"
        assert decision.human_decision == "Accepted"
        assert decision.decision_maker == "U12345678"
        assert decision.id.startswith("DEC-REC-")

        # Verify Supabase insert was called
        mock_supabase_client.insert.assert_called_once_with(
            "decision_records",
            pytest.approx(
                {
                    "id": decision.id,
                    "mission_id": "MSN-0055B",
                    "recommendation_id": "REC-20260610-150000",
                    "recommendation_text": "Recommended Option A",
                    "human_decision": "Accepted",
                    "decision_maker": "U12345678",
                    "decision_reason": "",
                    "captured_timestamp": pytest.approx(
                        decision.captured_timestamp,
                        abs=timedelta(seconds=1)
                    ),
                    "metadata": None,
                },
                exclude_keys=["id", "decision_timestamp", "captured_timestamp"],
            )
        )

    def test_record_decision_with_reason(self, learning_loop_service):
        """Test: Record decision with explanation."""
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Modified to Option B",
            decision_maker="Captain TJR",
            decision_reason="Budget constraints require lower-cost alternative",
        )

        assert decision is not None
        assert decision.decision_reason == "Budget constraints require lower-cost alternative"

    def test_record_decision_with_provider_metadata(self, learning_loop_service, sample_provider_metadata):
        """
        B1A Requirement: Provider metadata captured when available
        Test: Record decision with full provider provenance
        """
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
            decision_reason="Aligned with strategic goals",
            provider_metadata=sample_provider_metadata,
        )

        assert decision is not None
        assert decision.metadata is not None
        assert decision.metadata["provider_name"] == "google"
        assert decision.metadata["model_name"] == "gemini-2.5-flash"
        assert decision.metadata["provider_route"] == "primary"
        assert decision.metadata["research_execution_id"] == "RES-20260610-150000"

    def test_record_decision_with_custom_timestamp(self, learning_loop_service):
        """Test: Record decision with explicit timestamp."""
        custom_time = datetime(2026, 6, 10, 15, 0, 0)
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
            decision_timestamp=custom_time,
        )

        assert decision is not None
        assert decision.decision_timestamp == custom_time.isoformat()

    def test_record_decision_invalid_mission_id(self, learning_loop_service):
        """Test: Reject decision with missing mission_id."""
        with pytest.raises(ValueError, match="Missing required decision fields"):
            learning_loop_service.record_decision(
                mission_id="",  # Empty mission_id
                recommendation_id="REC-20260610-150000",
                recommendation_text="Recommended Option A",
                human_decision="Accepted",
                decision_maker="U12345678",
            )

    def test_record_decision_service_disabled(self):
        """Test: Graceful degradation when service disabled."""
        service = LearningLoopService(supabase_client=None)
        decision = service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        assert decision is None  # Gracefully returns None


# =============================================================================
# TEST SUITE 2: LINKAGE VALIDATION (B1A Requirements)
# =============================================================================

class TestDecisionLinkage:
    """Test decision linkage to missions and recommendations."""

    def test_decision_linked_to_mission(self, learning_loop_service):
        """
        B1A Requirement: Decision linked to mission and recommendation
        Test: Verify mission_id linkage
        """
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        assert decision.mission_id == "MSN-0055B"

    def test_decision_linked_to_recommendation(self, learning_loop_service):
        """
        B1A Requirement: Decision linked to recommendation
        Test: Verify recommendation_id and text preservation
        """
        rec_text = "Recommended Option A based on comprehensive analysis"
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text=rec_text,
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        assert decision.recommendation_id == "REC-20260610-150000"
        assert decision.recommendation_text == rec_text

    def test_decision_preserves_recommendation_text(self, learning_loop_service):
        """
        B1A Requirement: Audit trail - preserve recommendation text
        Test: Recommendation text saved for historical review
        """
        rec_text = "Option A: Vendor X, estimated cost $100k, delivery 3 months"
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text=rec_text,
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        # Recommendation text should be stored even if original recommendation is deleted
        assert decision.recommendation_text == rec_text


# =============================================================================
# TEST SUITE 3: AUDIT TRAIL & PERSISTENCE (B1A Requirements)
# =============================================================================

class TestAuditTrail:
    """Test audit trail completeness and data persistence."""

    def test_decision_has_timestamps(self, learning_loop_service):
        """Test: All timestamps present and valid."""
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        assert decision.decision_timestamp is not None
        assert decision.captured_timestamp is not None

        # captured_timestamp should be after or equal to decision_timestamp
        captured = datetime.fromisoformat(decision.captured_timestamp)
        decided = datetime.fromisoformat(decision.decision_timestamp)
        assert captured >= decided

    def test_decision_has_unique_id(self, learning_loop_service):
        """Test: Each decision gets unique canonical ID."""
        decision1 = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        decision2 = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150100",
            recommendation_text="Recommended Option B",
            human_decision="Rejected",
            decision_maker="U12345678",
        )

        assert decision1.id != decision2.id
        assert decision1.id.startswith("DEC-REC-")
        assert decision2.id.startswith("DEC-REC-")

    def test_decision_record_immutable(self, learning_loop_service):
        """Test: Decision record fields are correct type (audit-safe)."""
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        # All critical fields should be strings or serializable
        assert isinstance(decision.id, str)
        assert isinstance(decision.mission_id, str)
        assert isinstance(decision.recommendation_id, str)
        assert isinstance(decision.recommendation_text, str)
        assert isinstance(decision.human_decision, str)
        assert isinstance(decision.decision_maker, str)
        assert isinstance(decision.decision_timestamp, str)
        assert isinstance(decision.captured_timestamp, str)


# =============================================================================
# TEST SUITE 4: RETRIEVAL (B1A Validation)
# =============================================================================

class TestDecisionRetrieval:
    """Test decision retrieval from storage."""

    def test_get_decision_by_id(self, learning_loop_service, mock_supabase_client):
        """Test: Retrieve decision by ID."""
        # First record a decision
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        # Mock the select response
        mock_supabase_client.select.return_value = Mock(
            data=[
                {
                    "id": decision.id,
                    "mission_id": decision.mission_id,
                    "recommendation_id": decision.recommendation_id,
                    "recommendation_text": decision.recommendation_text,
                    "human_decision": decision.human_decision,
                    "decision_maker": decision.decision_maker,
                    "decision_reason": decision.decision_reason,
                    "decision_timestamp": decision.decision_timestamp,
                    "captured_timestamp": decision.captured_timestamp,
                    "metadata": decision.metadata,
                }
            ]
        )

        # Now retrieve it
        retrieved = learning_loop_service.get_decision(decision.id)
        assert retrieved is not None
        assert retrieved.id == decision.id
        assert retrieved.mission_id == decision.mission_id

    def test_get_decisions_for_mission(self, learning_loop_service, mock_supabase_client):
        """
        B1A Requirement: Get decisions for mission
        Test: Retrieve all decisions for a mission
        """
        # Mock the select response
        mock_supabase_client.select.return_value = Mock(
            data=[
                {
                    "id": "DEC-REC-20260610-150000",
                    "mission_id": "MSN-0055B",
                    "recommendation_id": "REC-20260610-150000",
                    "recommendation_text": "Recommended Option A",
                    "human_decision": "Accepted",
                    "decision_maker": "U12345678",
                    "decision_reason": "Aligned with strategy",
                    "decision_timestamp": "2026-06-10T15:00:00",
                    "captured_timestamp": "2026-06-10T15:00:01",
                    "metadata": None,
                },
                {
                    "id": "DEC-REC-20260610-150100",
                    "mission_id": "MSN-0055B",
                    "recommendation_id": "REC-20260610-150100",
                    "recommendation_text": "Recommended Option B",
                    "human_decision": "Rejected",
                    "decision_maker": "U12345678",
                    "decision_reason": "Budget too high",
                    "decision_timestamp": "2026-06-10T15:01:00",
                    "captured_timestamp": "2026-06-10T15:01:01",
                    "metadata": None,
                },
            ]
        )

        decisions = learning_loop_service.get_decisions_for_mission("MSN-0055B")
        assert len(decisions) == 2
        assert all(d.mission_id == "MSN-0055B" for d in decisions)


# =============================================================================
# TEST SUITE 5: PROVIDER METADATA CAPTURE (B1A Requirement)
# =============================================================================

class TestProviderMetadata:
    """Test provider metadata capture and storage."""

    def test_metadata_capture_google(self, learning_loop_service):
        """Test: Capture Google provider metadata."""
        metadata = ProviderMetadata(
            provider_name="google",
            model_name="gemini-2.5-flash",
            provider_route="primary",
            research_execution_id="RES-20260610-150000",
        )

        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
            provider_metadata=metadata,
        )

        assert decision.metadata["provider_name"] == "google"
        assert decision.metadata["model_name"] == "gemini-2.5-flash"

    def test_metadata_capture_openrouter(self, learning_loop_service):
        """Test: Capture OpenRouter provider metadata."""
        metadata = ProviderMetadata(
            provider_name="openrouter",
            model_name="mistral-small",
            provider_route="fallback",
            research_execution_id="RES-20260610-150100",
        )

        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
            provider_metadata=metadata,
        )

        assert decision.metadata["provider_name"] == "openrouter"
        assert decision.metadata["provider_route"] == "fallback"

    def test_metadata_capture_ollama_local(self, learning_loop_service):
        """Test: Capture Ollama (local) provider metadata."""
        metadata = ProviderMetadata(
            provider_name="ollama",
            model_name="qwen3:8b",
            provider_route="local_fallback",
            research_execution_id="RES-20260610-150200",
        )

        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
            provider_metadata=metadata,
        )

        assert decision.metadata["provider_name"] == "ollama"
        assert decision.metadata["model_name"] == "qwen3:8b"
        assert decision.metadata["provider_route"] == "local_fallback"

    def test_metadata_optional(self, learning_loop_service):
        """Test: Provider metadata is optional (graceful handling)."""
        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
            provider_metadata=None,  # Optional
        )

        assert decision.metadata is None  # Should be None, not error

    def test_metadata_to_dict(self, sample_provider_metadata):
        """Test: Metadata converts to JSON-serializable dict."""
        metadata_dict = sample_provider_metadata.to_dict()

        assert isinstance(metadata_dict, dict)
        assert "provider_name" in metadata_dict
        assert "model_name" in metadata_dict
        assert "provider_route" in metadata_dict
        assert "research_execution_id" in metadata_dict
        assert metadata_dict["provider_name"] == "google"


# =============================================================================
# TEST SUITE 6: ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Test error handling and resilience."""

    def test_supabase_insert_failure(self, learning_loop_service, mock_supabase_client):
        """Test: Graceful handling of Supabase errors."""
        mock_supabase_client.insert.side_effect = Exception("Network error")

        decision = learning_loop_service.record_decision(
            mission_id="MSN-0055B",
            recommendation_id="REC-20260610-150000",
            recommendation_text="Recommended Option A",
            human_decision="Accepted",
            decision_maker="U12345678",
        )

        assert decision is None  # Should return None on error, not raise

    def test_missing_required_fields_mission_id(self, learning_loop_service):
        """Test: Reject record with missing mission_id."""
        with pytest.raises(ValueError):
            learning_loop_service.record_decision(
                mission_id="",
                recommendation_id="REC-20260610-150000",
                recommendation_text="Recommended Option A",
                human_decision="Accepted",
                decision_maker="U12345678",
            )

    def test_missing_required_fields_recommendation_id(self, learning_loop_service):
        """Test: Reject record with missing recommendation_id."""
        with pytest.raises(ValueError):
            learning_loop_service.record_decision(
                mission_id="MSN-0055B",
                recommendation_id="",
                recommendation_text="Recommended Option A",
                human_decision="Accepted",
                decision_maker="U12345678",
            )

    def test_missing_required_fields_human_decision(self, learning_loop_service):
        """Test: Reject record with missing human_decision."""
        with pytest.raises(ValueError):
            learning_loop_service.record_decision(
                mission_id="MSN-0055B",
                recommendation_id="REC-20260610-150000",
                recommendation_text="Recommended Option A",
                human_decision="",
                decision_maker="U12345678",
            )

    def test_missing_required_fields_decision_maker(self, learning_loop_service):
        """Test: Reject record with missing decision_maker."""
        with pytest.raises(ValueError):
            learning_loop_service.record_decision(
                mission_id="MSN-0055B",
                recommendation_id="REC-20260610-150000",
                recommendation_text="Recommended Option A",
                human_decision="Accepted",
                decision_maker="",
            )


# =============================================================================
# TEST EXECUTION & REPORTING
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
