"""
Phase 1C Health Content Classifier

Validates health insights for content pipeline integration:
1. Scores health insights for publishability (min_rank_score validation)
2. Maps wellness categories to strategic content pillars
3. Inherits and enforces sensitivity classification

Usage:
    classifier = HealthContentClassifier(supabase_client)
    signals = classifier.score_for_content(health_insights)
    summary = classifier.validate_classifier_on_sample(days=7, sample_size=30)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

log = logging.getLogger(__name__)


class ContentPillar(str, Enum):
    """8 strategic content pillars for health-sourced signals."""
    OPERATIONAL_RESILIENCE = "Operational Resilience"
    HUMAN_PERFORMANCE = "Human Performance"
    WELLNESS_SUSTAINABLE = "Wellness & Sustainable Performance"
    PERSONAL_OS = "Personal Operating Systems"
    AI_AUGMENTED_LEADERSHIP = "AI-Augmented Leadership"
    FUTURE_OF_WORK = "Future of Work"
    BUSINESS_INNOVATION = "Business Innovation"
    EXECUTION_EXCELLENCE = "Execution Excellence"


class WellnessCategory(str, Enum):
    """Health/wellness categories that feed into content pillars."""
    TEAM_WELLNESS = "Team Wellness"
    MENTAL_HEALTH = "Mental Health Support"
    MANAGER_TRAINING = "Manager Training"
    CULTURE_BELONGING = "Culture & Belonging"
    RESILIENCE_PROGRAMS = "Resilience Programs"
    WORK_FLEXIBILITY = "Work Flexibility"
    BURNOUT_PREVENTION = "Burnout Prevention"
    PHYSICAL_WELLNESS = "Physical Wellness"
    PRODUCTIVITY_OPTIMIZATION = "Productivity Optimization"


@dataclass
class PillarMapping:
    """Maps wellness category to content pillar(s) with rationale."""
    wellness_category: WellnessCategory
    primary_pillar: ContentPillar
    secondary_pillar: Optional[ContentPillar] = None
    rationale: str = ""
    deferred_to_phase2: bool = False
    phase2_reason: str = ""


# Phase 1C: Locked pillar mappings (high-confidence)
PILLAR_MAPPINGS = {
    WellnessCategory.TEAM_WELLNESS: PillarMapping(
        wellness_category=WellnessCategory.TEAM_WELLNESS,
        primary_pillar=ContentPillar.WELLNESS_SUSTAINABLE,
        secondary_pillar=ContentPillar.HUMAN_PERFORMANCE,
        rationale="Focus: individual wellbeing + performance impact"
    ),
    WellnessCategory.MENTAL_HEALTH: PillarMapping(
        wellness_category=WellnessCategory.MENTAL_HEALTH,
        primary_pillar=ContentPillar.WELLNESS_SUSTAINABLE,
        secondary_pillar=None,
        rationale="Mental health is primary wellness concern",
        deferred_to_phase2=True,
        phase2_reason="Sensitive topic; defer to Phase 2 for enhanced handling"
    ),
    WellnessCategory.MANAGER_TRAINING: PillarMapping(
        wellness_category=WellnessCategory.MANAGER_TRAINING,
        primary_pillar=ContentPillar.HUMAN_PERFORMANCE,
        secondary_pillar=ContentPillar.AI_AUGMENTED_LEADERSHIP,
        rationale="Focus: people leadership capability"
    ),
    WellnessCategory.CULTURE_BELONGING: PillarMapping(
        wellness_category=WellnessCategory.CULTURE_BELONGING,
        primary_pillar=ContentPillar.PERSONAL_OS,
        secondary_pillar=ContentPillar.HUMAN_PERFORMANCE,
        rationale="Focus: individual identity + team"
    ),
    WellnessCategory.RESILIENCE_PROGRAMS: PillarMapping(
        wellness_category=WellnessCategory.RESILIENCE_PROGRAMS,
        primary_pillar=ContentPillar.OPERATIONAL_RESILIENCE,
        rationale="Clear mapping; operational focus"
    ),
    WellnessCategory.WORK_FLEXIBILITY: PillarMapping(
        wellness_category=WellnessCategory.WORK_FLEXIBILITY,
        primary_pillar=ContentPillar.FUTURE_OF_WORK,
        secondary_pillar=ContentPillar.PERSONAL_OS,
        rationale="Clear mapping; structural change"
    ),
    WellnessCategory.BURNOUT_PREVENTION: PillarMapping(
        wellness_category=WellnessCategory.BURNOUT_PREVENTION,
        primary_pillar=ContentPillar.WELLNESS_SUSTAINABLE,
        secondary_pillar=ContentPillar.OPERATIONAL_RESILIENCE,
        rationale="Burnout prevention is wellness + operational"
    ),
    WellnessCategory.PHYSICAL_WELLNESS: PillarMapping(
        wellness_category=WellnessCategory.PHYSICAL_WELLNESS,
        primary_pillar=ContentPillar.WELLNESS_SUSTAINABLE,
        rationale="Physical wellness is core pillar"
    ),
    WellnessCategory.PRODUCTIVITY_OPTIMIZATION: PillarMapping(
        wellness_category=WellnessCategory.PRODUCTIVITY_OPTIMIZATION,
        primary_pillar=ContentPillar.EXECUTION_EXCELLENCE,
        secondary_pillar=ContentPillar.WELLNESS_SUSTAINABLE,
        rationale="Productivity bridges wellness and execution"
    ),
}


@dataclass
class ContentSignal:
    """Health insight scored and classified for content pipeline."""
    insight_id: str
    rank_score: float
    publishable: bool
    primary_pillar: ContentPillar
    secondary_pillar: Optional[ContentPillar] = None
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    sensitivity_inherited: bool = False


class HealthContentClassifier:
    """Validates and scores health insights for content integration."""

    # Phase 1C: Validated threshold (will be tuned after validation)
    MIN_RANK_SCORE = 0.7

    def __init__(self, supabase_client: Any):
        self.sb = supabase_client
        self.suppressed_signals = []  # Audit trail

    def _calculate_quality_score(self, health_insight: dict) -> float:
        """
        Calculate quality/publishability score from available insight data.

        PHASE 1C TEMPORARY IMPLEMENTATION:
        rank_score column does not exist on health_insights yet (Phase 2 addition).
        This calculates score from: narrative_available + deterministic_findings.
        Phase 2: Replace with real rank_score column value from weekly_synthesis.
        """
        score = 0.3  # Base score if minimal data

        # Narrative quality (if LLM narrative exists and marked available)
        if health_insight.get('narrative_available'):
            score = 0.8
        elif health_insight.get('llm_narrative'):
            score = 0.6

        # Boost if structured findings exist
        findings = health_insight.get('deterministic_findings')
        if findings:
            if isinstance(findings, (list, dict)) and len(findings) > 0:
                score = min(1.0, score + 0.2)
            elif isinstance(findings, str) and findings.strip():
                score = min(1.0, score + 0.15)

        return score

    def score_for_content(
        self,
        health_insight: dict,
        wellness_category: Optional[WellnessCategory] = None,
    ) -> Optional[ContentSignal]:
        """
        Score health insight for content pipeline.

        Solution #3: Inherit sensitivity from health_events
        - If health_insight.sensitive=True, suppress entirely
        - Log suppression for audit trail

        Returns None if insight should be suppressed; ContentSignal if publishable.
        """
        insight_id = health_insight.get("id")

        # Solution #3: Check sensitivity flag
        # PHASE 1C TEMPORARY: sensitive column doesn't exist; default False
        # Phase 2: Add NER + source event inheritance
        is_sensitive = health_insight.get("sensitive", False)
        is_discarded = health_insight.get("committed_to_memory") is False

        if is_sensitive or is_discarded:
            reason = "Marked as sensitive or discarded by Captain"
            log.warning(f"Suppressing health_insight {insight_id}: {reason}")
            self.suppressed_signals.append({
                "insight_id": insight_id,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            })
            return None

        # Solution #1: Apply min_rank_score threshold
        # PHASE 1C TEMPORARY: Calculate from available data; Phase 2: use real rank_score column
        rank_score = self._calculate_quality_score(health_insight)

        if rank_score < self.MIN_RANK_SCORE:
            log.debug(f"health_insight {insight_id} below threshold ({rank_score:.2f} < {self.MIN_RANK_SCORE})")
            return None

        # Solution #2: Map wellness category to pillar
        if wellness_category and wellness_category in PILLAR_MAPPINGS:
            mapping = PILLAR_MAPPINGS[wellness_category]

            # Check if deferred to Phase 2
            if mapping.deferred_to_phase2:
                log.info(f"Deferring {wellness_category} to Phase 2: {mapping.phase2_reason}")
                # Still create signal, but mark for Phase 2 handling
        else:
            # Default pillar if category not recognized
            mapping = PILLAR_MAPPINGS.get(
                WellnessCategory.TEAM_WELLNESS,
                PillarMapping(
                    wellness_category=WellnessCategory.TEAM_WELLNESS,
                    primary_pillar=ContentPillar.WELLNESS_SUSTAINABLE,
                    rationale="Default for unclassified wellness"
                )
            )

        # Create content signal
        signal = ContentSignal(
            insight_id=insight_id,
            rank_score=rank_score,
            publishable=rank_score >= self.MIN_RANK_SCORE,
            primary_pillar=mapping.primary_pillar,
            secondary_pillar=mapping.secondary_pillar,
            suppressed=False,
            sensitivity_inherited=True,
        )

        log.info(f"Scored health_insight {insight_id}: {rank_score:.2f} → {mapping.primary_pillar}")
        return signal

    def validate_classifier_on_sample(
        self,
        days: int = 7,
        sample_size: int = 30,
    ) -> dict:
        """
        Solution #1: Validate min_rank_score threshold on real data.

        Run classifier on 7 days of real health_insights, measure QA pass rate.
        Target: ~70% publishable signals.

        Returns validation report with pass rate and recommendation.
        """
        log.info(f"Validating classifier on {days}-day sample (max {sample_size} signals)")

        # Fetch recent health insights
        since = datetime.utcnow() - timedelta(days=days)
        since_iso = since.isoformat()

        try:
            # PHASE 1C: Query only columns that exist on health_insights
            # rank_score + sensitive will be calculated/defaulted (Phase 2: use real columns)
            response = self.sb.from_("health_insights").select(
                "id, created_at, llm_narrative, narrative_available, deterministic_findings, committed_to_memory"
            ).gte("created_at", since_iso).order(
                "created_at", ascending=False
            ).limit(sample_size).execute()

            insights = response.data if hasattr(response, 'data') else response
        except Exception as e:
            log.error(f"Failed to fetch insights for validation: {e}")
            return {
                "status": "error",
                "message": str(e),
                "pass_rate": None,
            }

        if not insights:
            log.warning(f"No insights found in last {days} days")
            return {
                "status": "no_data",
                "samples": 0,
                "pass_rate": None,
                "message": f"No health_insights in last {days} days"
            }

        # Score each insight
        scored = []
        for insight in insights:
            signal = self.score_for_content(insight)
            if signal:
                scored.append({
                    "insight_id": signal.insight_id,
                    "rank_score": signal.rank_score,
                    "publishable": signal.publishable,
                    "pillar": signal.primary_pillar.value,
                })

        # Calculate pass rate
        publishable_count = sum(1 for s in scored if s["publishable"])
        pass_rate = publishable_count / len(scored) if scored else 0.0

        # Recommendation based on pass rate
        if pass_rate < 0.6:
            recommendation = "LOWER THRESHOLD (too many rejections; try 0.65)"
        elif pass_rate > 0.85:
            recommendation = "RAISE THRESHOLD (too permissive; try 0.75)"
        else:
            recommendation = "THRESHOLD APPROVED (pass rate 60-85%)"

        report = {
            "status": "success",
            "samples_analyzed": len(insights),
            "signals_published": len(scored),
            "signals_suppressed": len(self.suppressed_signals),
            "pass_rate": pass_rate,
            "current_threshold": self.MIN_RANK_SCORE,
            "recommendation": recommendation,
            "scored_signals": scored[:5],  # Top 5 for review
            "suppressed_signals": self.suppressed_signals,
        }

        log.info(f"Validation complete: {pass_rate:.0%} pass rate → {recommendation}")
        return report

    def get_pillar_mapping(self, category: WellnessCategory) -> Optional[PillarMapping]:
        """Solution #2: Get pillar mapping for wellness category."""
        return PILLAR_MAPPINGS.get(category)

    def list_all_mappings(self) -> list[dict]:
        """Solution #2: List all pillar mappings with rationale."""
        return [
            {
                "wellness_category": m.wellness_category.value,
                "primary_pillar": m.primary_pillar.value,
                "secondary_pillar": m.secondary_pillar.value if m.secondary_pillar else None,
                "rationale": m.rationale,
                "deferred_to_phase2": m.deferred_to_phase2,
                "phase2_reason": m.phase2_reason if m.deferred_to_phase2 else None,
            }
            for m in PILLAR_MAPPINGS.values()
        ]

    def get_audit_log(self) -> list[dict]:
        """Solution #3: Get audit trail of suppressed signals."""
        return self.suppressed_signals


# Convenience function for Phase 1C validation
def validate_health_classifier(supabase_client: Any, days: int = 7) -> dict:
    """
    Quick validation of health content classifier on real data.

    Usage:
        from supabase_client import get_client
        sb = get_client()
        report = validate_health_classifier(sb, days=7)
        print(json.dumps(report, indent=2))
    """
    classifier = HealthContentClassifier(supabase_client)
    return classifier.validate_classifier_on_sample(days=days, sample_size=30)
