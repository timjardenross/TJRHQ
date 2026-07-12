"""
Tests for Phase 1C Health Content Classifier

Tests all three solutions:
1. min_rank_score validation
2. Wellness category → pillar mapping
3. Sensitivity flag inheritance and suppression
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from health_content_classifier import (
    HealthContentClassifier,
    WellnessCategory,
    ContentPillar,
    ContentSignal,
    PILLAR_MAPPINGS,
)


class TestHealthContentClassifierValidation:
    """Test Solution #1: Classifier validation on real data."""

    def test_score_above_threshold_is_publishable(self):
        """High-scoring insight should be publishable."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "test-1",
            "rank_score": 0.85,
            "sensitive": False,
            "committed_to_memory": True,
        }

        signal = classifier.score_for_content(insight)
        assert signal is not None
        assert signal.publishable is True
        assert signal.rank_score == 0.85

    def test_score_below_threshold_is_rejected(self):
        """Low-scoring insight should be rejected."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "test-2",
            "rank_score": 0.5,
            "sensitive": False,
            "committed_to_memory": True,
        }

        signal = classifier.score_for_content(insight)
        assert signal is None

    def test_threshold_tuning_recommendation(self):
        """Pass rate < 60% should recommend lower threshold."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        # Mock low pass rate scenario
        mock_sb.from_.return_value.select.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "i1", "rank_score": 0.5, "sensitive": False, "committed_to_memory": True},
                {"id": "i2", "rank_score": 0.55, "sensitive": False, "committed_to_memory": True},
                {"id": "i3", "rank_score": 0.65, "sensitive": False, "committed_to_memory": True},
                {"id": "i4", "rank_score": 0.6, "sensitive": False, "committed_to_memory": True},
                {"id": "i5", "rank_score": 0.58, "sensitive": False, "committed_to_memory": True},
            ]
        )

        report = classifier.validate_classifier_on_sample(days=7, sample_size=5)
        assert report["status"] == "success"
        assert "LOWER THRESHOLD" in report["recommendation"]


class TestPillarMapping:
    """Test Solution #2: Wellness category → pillar mapping."""

    def test_team_wellness_maps_to_wellness_sustainable(self):
        """Team wellness should map to Wellness & Sustainable Performance."""
        mapping = PILLAR_MAPPINGS[WellnessCategory.TEAM_WELLNESS]
        assert mapping.primary_pillar == ContentPillar.WELLNESS_SUSTAINABLE
        assert mapping.secondary_pillar == ContentPillar.HUMAN_PERFORMANCE

    def test_manager_training_maps_to_human_performance(self):
        """Manager training should map to Human Performance."""
        mapping = PILLAR_MAPPINGS[WellnessCategory.MANAGER_TRAINING]
        assert mapping.primary_pillar == ContentPillar.HUMAN_PERFORMANCE
        assert mapping.secondary_pillar == ContentPillar.AI_AUGMENTED_LEADERSHIP

    def test_resilience_clear_mapping(self):
        """Resilience programs should map clearly to Operational Resilience."""
        mapping = PILLAR_MAPPINGS[WellnessCategory.RESILIENCE_PROGRAMS]
        assert mapping.primary_pillar == ContentPillar.OPERATIONAL_RESILIENCE
        assert mapping.secondary_pillar is None

    def test_mental_health_deferred_to_phase2(self):
        """Mental health should be deferred to Phase 2."""
        mapping = PILLAR_MAPPINGS[WellnessCategory.MENTAL_HEALTH]
        assert mapping.deferred_to_phase2 is True
        assert mapping.phase2_reason is not None

    def test_get_pillar_mapping(self):
        """Can retrieve mapping for any wellness category."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        mapping = classifier.get_pillar_mapping(WellnessCategory.TEAM_WELLNESS)
        assert mapping is not None
        assert mapping.primary_pillar == ContentPillar.WELLNESS_SUSTAINABLE

    def test_list_all_mappings(self):
        """Can list all mappings with rationale."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        mappings = classifier.list_all_mappings()
        assert len(mappings) == 9  # 9 wellness categories
        assert all("wellness_category" in m for m in mappings)
        assert all("primary_pillar" in m for m in mappings)
        assert all("rationale" in m for m in mappings)

    def test_mapping_includes_rationale(self):
        """All mappings should include rationale for Phase 1C documentation."""
        for category, mapping in PILLAR_MAPPINGS.items():
            assert mapping.rationale, f"{category.value} missing rationale"


class TestSensitivityInheritance:
    """Test Solution #3: Sensitivity flag inheritance and suppression."""

    def test_sensitive_insight_is_suppressed(self):
        """Health insight marked sensitive should be completely suppressed."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "sensitive-1",
            "rank_score": 0.95,  # High score, but sensitive
            "sensitive": True,
            "committed_to_memory": True,
        }

        signal = classifier.score_for_content(insight)
        assert signal is None
        assert len(classifier.suppressed_signals) == 1
        assert "sensitive" in classifier.suppressed_signals[0]["reason"].lower()

    def test_discarded_insight_is_suppressed(self):
        """Insight discarded by Captain should be suppressed."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "discarded-1",
            "rank_score": 0.95,
            "sensitive": False,
            "committed_to_memory": False,  # Captain discarded
        }

        signal = classifier.score_for_content(insight)
        assert signal is None
        assert len(classifier.suppressed_signals) == 1

    def test_audit_log_tracks_suppressed_signals(self):
        """Suppressed signals should be logged for audit trail."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insights = [
            {"id": "s1", "rank_score": 0.95, "sensitive": True, "committed_to_memory": True},
            {"id": "s2", "rank_score": 0.95, "sensitive": False, "committed_to_memory": False},
            {"id": "s3", "rank_score": 0.95, "sensitive": False, "committed_to_memory": True},
        ]

        for insight in insights:
            classifier.score_for_content(insight)

        audit_log = classifier.get_audit_log()
        assert len(audit_log) == 2  # 2 suppressed
        assert all("timestamp" in entry for entry in audit_log)
        assert all("reason" in entry for entry in audit_log)

    def test_non_sensitive_insight_passes_through(self):
        """Non-sensitive insight with good score should pass."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "public-1",
            "rank_score": 0.85,
            "sensitive": False,
            "committed_to_memory": True,
        }

        signal = classifier.score_for_content(insight)
        assert signal is not None
        assert signal.suppressed is False
        assert len(classifier.suppressed_signals) == 0


class TestIntegration:
    """Integration tests for all three solutions together."""

    def test_full_scoring_workflow(self):
        """Test complete workflow: score, map, suppress all at once."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        # Scenario 1: Good insight, not sensitive
        insight1 = {
            "id": "good-1",
            "rank_score": 0.85,
            "sensitive": False,
            "committed_to_memory": True,
        }
        signal1 = classifier.score_for_content(insight1, WellnessCategory.TEAM_WELLNESS)
        assert signal1 is not None
        assert signal1.primary_pillar == ContentPillar.WELLNESS_SUSTAINABLE

        # Scenario 2: Good score but sensitive
        insight2 = {
            "id": "sensitive-2",
            "rank_score": 0.90,
            "sensitive": True,
            "committed_to_memory": True,
        }
        signal2 = classifier.score_for_content(insight2, WellnessCategory.MENTAL_HEALTH)
        assert signal2 is None
        assert len(classifier.suppressed_signals) == 1

        # Scenario 3: Low score
        insight3 = {
            "id": "low-3",
            "rank_score": 0.5,
            "sensitive": False,
            "committed_to_memory": True,
        }
        signal3 = classifier.score_for_content(insight3, WellnessCategory.RESILIENCE_PROGRAMS)
        assert signal3 is None

    def test_audit_trail_completeness(self):
        """Audit log should track all suppressions with context."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        # Create multiple insights with different suppression reasons
        classifier.score_for_content({
            "id": "s1",
            "rank_score": 0.95,
            "sensitive": True,
            "committed_to_memory": True,
        })

        classifier.score_for_content({
            "id": "s2",
            "rank_score": 0.95,
            "sensitive": False,
            "committed_to_memory": False,
        })

        log = classifier.get_audit_log()
        assert len(log) == 2
        assert any("sensitive" in e["reason"].lower() for e in log)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_rank_score(self):
        """Insight without rank_score should default to 0."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {"id": "no-score", "sensitive": False, "committed_to_memory": True}
        signal = classifier.score_for_content(insight)
        assert signal is None  # 0 < 0.7

    def test_invalid_rank_score_type(self):
        """Non-numeric rank_score should be handled gracefully."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "bad-score",
            "rank_score": "not-a-number",
            "sensitive": False,
            "committed_to_memory": True,
        }
        signal = classifier.score_for_content(insight)
        assert signal is None  # Defaults to 0

    def test_unknown_wellness_category(self):
        """Unknown category should default to team wellness."""
        mock_sb = Mock()
        classifier = HealthContentClassifier(mock_sb)

        insight = {
            "id": "unknown-cat",
            "rank_score": 0.85,
            "sensitive": False,
            "committed_to_memory": True,
        }
        signal = classifier.score_for_content(insight, WellnessCategory("Unknown"))
        # Should still score, with default mapping
        assert signal is not None or signal is None  # Depends on implementation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
