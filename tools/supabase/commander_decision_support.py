#!/usr/bin/env python3
"""
MSN-0013A: Commander Decision Support / Recommendation Engine
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Synthesize analysis + quality scores into actionable recommendations
"""

from dataclasses import dataclass
from typing import List
from datetime import datetime, timedelta
from dual_commander_analysis import DualCommanderAnalysis
from decision_quality_scorer import DecisionQualityScore


@dataclass
class ModelRecommendation:
    """Recommendation on which Commander model to use."""

    primary_model_current: str  # e.g., "qwen3:8b"
    recommended_action: str  # 'promote', 'demote', 'keep', 'specialize', 'insufficient_data'

    action_reasoning: str  # Why this action
    trial_period_days: int  # If promoting, how long to test
    success_criteria: List[str]  # What to measure during trial

    confidence: float  # 0-1 (overall confidence in recommendation)

    summary: str  # 1-paragraph executive summary for Captain
    detailed_recommendation: str  # More detailed explanation

    quality_metrics: dict  # Average scores, trends
    next_actions: List[str]  # Tactical next steps

    recommendation_timestamp: datetime = None


class CommanderDecisionSupport:
    """Generate model recommendations based on analysis."""

    def generate_model_recommendation(
        self,
        current_primary_model: str,  # e.g., "qwen3:8b"
        analysis: DualCommanderAnalysis,
        quality_scores: List[DecisionQualityScore],
    ) -> ModelRecommendation:
        """
        Synthesize analysis + quality scores into actionable recommendation.

        Args:
            current_primary_model: Current primary model name
            analysis: DualCommanderAnalysis result
            quality_scores: List of DecisionQualityScore objects

        Returns:
            ModelRecommendation for Captain TJR
        """

        # Calculate quality metrics
        avg_quality = (
            sum(s.total_score for s in quality_scores) / len(quality_scores)
            if quality_scores
            else 0
        )
        avg_clarity = (
            sum(s.clarity for s in quality_scores) / len(quality_scores)
            if quality_scores
            else 0
        )

        quality_metrics = {
            "avg_quality_score": round(avg_quality, 2),
            "avg_clarity": round(avg_clarity, 2),
            "total_decisions_scored": len(quality_scores),
        }

        # Generate action-specific recommendation
        action = analysis.recommendation
        reasoning, trial_period, success_criteria, next_actions = self._detail_action(
            action, current_primary_model, analysis, avg_quality
        )

        # Build summary
        summary = self._build_summary(
            action, current_primary_model, analysis, avg_quality
        )

        # Build detailed explanation
        detailed = self._build_detailed_recommendation(action, analysis)

        # Overall confidence
        confidence = self._calculate_confidence(analysis, avg_quality)

        return ModelRecommendation(
            primary_model_current=current_primary_model,
            recommended_action=action,
            action_reasoning=reasoning,
            trial_period_days=trial_period,
            success_criteria=success_criteria,
            confidence=confidence,
            summary=summary,
            detailed_recommendation=detailed,
            quality_metrics=quality_metrics,
            next_actions=next_actions,
            recommendation_timestamp=datetime.now(),
        )

    def _detail_action(
        self,
        action: str,
        current_primary: str,
        analysis: DualCommanderAnalysis,
        avg_quality: float,
    ) -> tuple[str, int, List[str], List[str]]:
        """Detail the recommended action with criteria and next steps."""

        if action == "promote":
            reasoning = (
                f"DeepSeek has won {analysis.deepseek_win_rate*100:.0f}% of {analysis.total_runs} "
                f"evaluations with an average decision quality of {avg_quality:.1f}/4.0. "
                "Recommend promotion to primary model with a trial period."
            )
            trial_period = 14  # 2 weeks
            success_criteria = [
                f"Maintain >60% win rate on technical decisions",
                f"Achieve average quality score >{avg_quality}",
                "Zero critical incidents during trial period",
                "Captain approval after day 7 review",
            ]
            next_actions = [
                "Set COMMANDER_PRIMARY_MODEL=deepseek-r1:14b in .env",
                "Test with 5 real decisions before full cutover",
                "Monitor logs and decision outcomes daily",
                f"Schedule review on {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}",
                f"Final decision on {(datetime.now() + timedelta(days=trial_period)).strftime('%Y-%m-%d')}",
            ]

        elif action == "demote":
            reasoning = (
                f"DeepSeek has won only {analysis.deepseek_win_rate*100:.0f}% of {analysis.total_runs} "
                "evaluations, indicating Qwen remains superior. Archive DeepSeek candidate."
            )
            trial_period = 0
            success_criteria = [
                "Archive dual commander evaluation",
                "Revert to Qwen-only Commander",
                "Document decision rationale",
            ]
            next_actions = [
                "Archive DeepSeek candidate evaluation",
                "Continue with current Qwen configuration",
                "Revisit model selection in Q1 2027",
                "Document lessons learned from evaluation",
            ]

        elif action == "specialize":
            reasoning = (
                "Both models show complementary strengths in different decision types. "
                "Recommend specialization: route decisions by type to model that excels. "
                "This leverages each model's strengths without full promotion."
            )
            trial_period = 14  # 2 weeks with specialized routing
            success_criteria = [
                "Decision-type classification >85% accurate",
                "DeepSeek wins 70%+ on technical decisions",
                "Qwen wins 70%+ on policy decisions",
                "Overall quality score maintained or improved",
            ]
            next_actions = [
                "Implement decision-type classifier in command layer",
                "Configure routing rules (technical→deepseek, policy→qwen)",
                "Test with 10 diverse decisions",
                f"Evaluate after {trial_period} days",
                "Promote specialized routing if successful",
            ]

        elif action == "keep":
            reasoning = (
                f"After {analysis.total_runs} evaluations, both models show similar "
                "performance. Current configuration is stable. Continue monitoring."
            )
            trial_period = 0
            success_criteria = [
                "Continue current primary model (Qwen)",
                "Monitor for performance drift",
            ]
            next_actions = [
                "Maintain current Qwen configuration",
                "Run 5 more evaluations in 2 weeks",
                "Re-evaluate decision patterns monthly",
                "Flag for re-evaluation if quality drops",
            ]

        else:  # insufficient_data
            reasoning = (
                f"After {analysis.total_runs} evaluations, insufficient data for "
                f"confident recommendation. Need {20 - analysis.total_runs} more runs."
            )
            trial_period = 0
            success_criteria = [
                f"Collect {20 - analysis.total_runs} more evaluation runs",
                "Ensure varied decision types",
                f"Target completion by {(datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')}",
            ]
            next_actions = [
                f"Run {20 - analysis.total_runs} more dual commander evaluations",
                "Prioritize varied question types (policy, technical, operational, strategic)",
                f"Schedule re-analysis for {(datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')}",
            ]

        return reasoning, trial_period, success_criteria, next_actions

    def _build_summary(
        self,
        action: str,
        current_primary: str,
        analysis: DualCommanderAnalysis,
        avg_quality: float,
    ) -> str:
        """Build 1-paragraph executive summary for Captain."""

        if action == "promote":
            return (
                f"Based on {analysis.total_runs} evaluations, DeepSeek demonstrates superior performance "
                f"(winning {analysis.deepseek_win_rate*100:.0f}% of decisions) with an average decision quality "
                f"of {avg_quality:.1f}/4.0. Recommend a 14-day trial promotion to primary model. If trial succeeds, "
                "transition permanently; if not, revert to Qwen."
            )

        elif action == "demote":
            return (
                f"After {analysis.total_runs} evaluations, Qwen remains superior "
                f"(DeepSeek won only {analysis.deepseek_win_rate*100:.0f}% of decisions). Archive DeepSeek evaluation "
                "and continue with current Qwen configuration."
            )

        elif action == "specialize":
            return (
                f"Both models show complementary strengths: DeepSeek excels on technical decisions "
                f"({analysis.decision_types.get('technical', {}).get('deepseek', 0)*100:.0f}% win rate), "
                f"Qwen on policy ({analysis.decision_types.get('policy', {}).get('qwen', 0)*100:.0f}%). "
                "Rather than promoting one, recommend specialized routing by decision type. Trial period: 14 days."
            )

        elif action == "keep":
            return (
                f"After {analysis.total_runs} evaluations, both models show similar performance. "
                f"Current Qwen configuration is stable with average decision quality {avg_quality:.1f}/4.0. "
                "Continue current setup; monitor for drift."
            )

        else:
            return (
                f"After {analysis.total_runs} evaluations, insufficient data for confident recommendation. "
                f"Need {20 - analysis.total_runs} more runs with varied decision types. Target: {(datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')}."
            )

    def _build_detailed_recommendation(
        self, action: str, analysis: DualCommanderAnalysis
    ) -> str:
        """Build detailed multi-sentence explanation."""

        lines = [f"**Recommended Action: {action.upper()}**"]
        lines.append("")

        if action == "promote":
            lines.append(
                f"DeepSeek has demonstrated consistent superiority over {analysis.total_runs} evaluations. "
            )
            lines.append(f"It won {analysis.deepseek_wins} decisions vs. Qwen's {analysis.qwen_wins}. ")
            lines.append(
                "A 14-day trial promotion is recommended to validate this pattern on real production decisions. "
            )
            lines.append(
                "If trial metrics hold, make permanent. If not, revert to Qwen with lessons documented."
            )

        elif action == "demote":
            lines.append(
                f"Qwen remains the superior model after {analysis.total_runs} evaluations. "
            )
            lines.append(
                f"DeepSeek won only {analysis.deepseek_wins} decisions ({analysis.deepseek_win_rate*100:.0f}%), "
                "indicating the candidate model does not meet promotion threshold."
            )
            lines.append("Archive the dual commander evaluation and continue with Qwen.")

        elif action == "specialize":
            for dtype, rates in analysis.decision_types.items():
                if rates.get("deepseek", 0) > 0.60:
                    lines.append(
                        f"DeepSeek excels on {dtype} decisions ({rates['deepseek']*100:.0f}% win rate). "
                    )
                if rates.get("qwen", 0) > 0.60:
                    lines.append(
                        f"Qwen excels on {dtype} decisions ({rates['qwen']*100:.0f}% win rate). "
                    )
            lines.append(
                "Rather than promoting one model universally, implement decision-type routing "
                "to leverage each model's strengths."
            )

        elif action == "keep":
            lines.append(
                f"After {analysis.total_runs} evaluations, performance is within 10 percentage points. "
            )
            lines.append("Current Qwen configuration is stable. Continue monitoring.")

        else:
            lines.append(
                f"More data needed. After {analysis.total_runs} runs, "
                "recommend running 10-20 more evaluations to establish confident patterns."
            )

        return "\n".join(lines)

    def _calculate_confidence(self, analysis: DualCommanderAnalysis, avg_quality: float) -> float:
        """Calculate overall confidence in recommendation (0-1)."""

        base_confidence = min(analysis.total_runs / 20.0, 1.0)  # 0-1 based on run count

        if analysis.recommendation == "insufficient_data":
            return 0.2

        if analysis.recommendation == "specialize":
            return 0.5 + (0.1 if base_confidence > 0.8 else 0)

        if abs(analysis.qwen_win_rate - analysis.deepseek_win_rate) > 0.3:
            return min(base_confidence + 0.2, 1.0)

        return base_confidence


def generate_recommendation(
    current_primary: str,
    analysis: DualCommanderAnalysis,
    quality_scores: List[DecisionQualityScore],
) -> ModelRecommendation:
    """Convenience function to generate recommendation."""
    support = CommanderDecisionSupport()
    return support.generate_model_recommendation(current_primary, analysis, quality_scores)


if __name__ == "__main__":
    # Example usage
    from dual_commander_analysis import DualCommanderAnalysis

    # Mock analysis
    analysis = DualCommanderAnalysis(
        total_runs=20,
        qwen_wins=7,
        deepseek_wins=13,
        ties=0,
        qwen_win_rate=0.35,
        deepseek_win_rate=0.65,
        tie_rate=0.0,
        decision_types={
            "technical": {"qwen": 0.40, "deepseek": 0.60, "tie": 0.0},
            "policy": {"qwen": 0.80, "deepseek": 0.20, "tie": 0.0},
        },
        recommendation="specialize",
        confidence=0.6,
        reasoning="Models show complementary strengths",
        next_steps=["Implement routing", "Test 10 decisions", "Evaluate"],
    )

    # Mock quality scores
    quality_scores = [
        DecisionQualityScore(
            decision_id=i,
            decision_text="Test decision",
            outcome_status="success",
            clarity=0.8,
            timeliness=0.7,
            accuracy=1.0,
            actionability=0.8,
            total_score=3.3,
            reasoning="Good decision",
        )
        for i in range(5)
    ]

    support = CommanderDecisionSupport()
    rec = support.generate_model_recommendation("qwen3:8b", analysis, quality_scores)

    print(f"Recommended Action: {rec.recommended_action.upper()}")
    print(f"Confidence: {rec.confidence*100:.0f}%")
    print(f"\nSummary:\n{rec.summary}")
    print(f"\nSuccess Criteria:")
    for criterion in rec.success_criteria:
        print(f"  - {criterion}")
    print(f"\nNext Actions:")
    for action in rec.next_actions:
        print(f"  - {action}")
