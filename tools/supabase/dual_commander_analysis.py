#!/usr/bin/env python3
"""
MSN-0013A: Dual Commander Pattern Analyzer
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Analyze dual commander evaluation runs and generate recommendations
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import re


@dataclass
class DualCommanderAnalysis:
    """Result of analyzing dual commander evaluation runs."""

    total_runs: int
    qwen_wins: int
    deepseek_wins: int
    ties: int

    qwen_win_rate: float  # 0-1
    deepseek_win_rate: float  # 0-1
    tie_rate: float  # 0-1

    decision_types: Dict[str, Dict[str, float]]  # {'policy': {'qwen': 0.6, 'deepseek': 0.4}, ...}

    recommendation: str  # 'promote', 'demote', 'keep', 'specialize', 'insufficient_data'
    confidence: float  # 0-1 (how confident in recommendation)

    reasoning: str  # Human-readable explanation
    next_steps: List[str]  # Actionable next steps

    analysis_timestamp: datetime = None


class DualCommanderAnalyzer:
    """Analyze dual commander evaluation patterns."""

    # Decision type keywords
    DECISION_TYPES = {
        "policy": [
            "policy",
            "governance",
            "authorization",
            "approval",
            "authority",
            "permission",
        ],
        "technical": [
            "code",
            "architecture",
            "infrastructure",
            "api",
            "database",
            "deployment",
            "system",
        ],
        "operational": [
            "process",
            "workflow",
            "timing",
            "schedule",
            "resource",
            "capacity",
        ],
        "strategic": [
            "direction",
            "roadmap",
            "priority",
            "vision",
            "goal",
            "objective",
        ],
    }

    def analyze_dual_commander_runs(
        self,
        runs: List[Dict],  # From collaboration_logs table
        min_runs: int = 10,
    ) -> DualCommanderAnalysis:
        """
        Analyze dual commander evaluation runs.

        Args:
            runs: List of run records with captain_preferred_model, decision_text, captain_notes
            min_runs: Minimum runs for confidence (default 10)

        Returns:
            DualCommanderAnalysis with recommendation
        """

        if not runs or len(runs) < min_runs:
            return DualCommanderAnalysis(
                total_runs=len(runs),
                qwen_wins=0,
                deepseek_wins=0,
                ties=0,
                qwen_win_rate=0,
                deepseek_win_rate=0,
                tie_rate=0,
                decision_types={},
                recommendation="insufficient_data",
                confidence=0.0,
                reasoning=f"Need at least {min_runs} evaluation runs for confident recommendation. Currently have {len(runs)}.",
                next_steps=[
                    f"Run {min_runs - len(runs)} more dual commander evaluations",
                    "Ensure varied question types (policy, technical, operational, strategic)",
                    f"Re-analyze after reaching {min_runs} runs",
                ],
                analysis_timestamp=datetime.now(),
            )

        # Count wins
        qwen_wins = sum(
            1
            for r in runs
            if r.get("captain_preferred_model") == "qwen" or r.get("captain_preferred_model") == "qwen3:8b"
        )
        deepseek_wins = sum(
            1
            for r in runs
            if r.get("captain_preferred_model") == "deepseek"
            or r.get("captain_preferred_model") == "deepseek-r1:14b"
        )
        ties = len(runs) - qwen_wins - deepseek_wins

        total_runs = len(runs)
        qwen_rate = qwen_wins / total_runs if total_runs > 0 else 0
        deepseek_rate = deepseek_wins / total_runs if total_runs > 0 else 0
        tie_rate = ties / total_runs if total_runs > 0 else 0

        # Classify decision types
        decision_types = self._classify_decision_types(runs)

        # Generate recommendation
        recommendation, confidence = self._generate_recommendation(
            qwen_rate, deepseek_rate, total_runs, decision_types
        )

        # Build reasoning
        reasoning = self._build_reasoning(
            total_runs, qwen_wins, deepseek_wins, ties, recommendation, decision_types
        )

        # Next steps
        next_steps = self._generate_next_steps(
            recommendation, total_runs, decision_types
        )

        return DualCommanderAnalysis(
            total_runs=total_runs,
            qwen_wins=qwen_wins,
            deepseek_wins=deepseek_wins,
            ties=ties,
            qwen_win_rate=qwen_rate,
            deepseek_win_rate=deepseek_rate,
            tie_rate=tie_rate,
            decision_types=decision_types,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            next_steps=next_steps,
            analysis_timestamp=datetime.now(),
        )

    def _classify_decision_types(self, runs: List[Dict]) -> Dict[str, Dict[str, float]]:
        """Classify each run's decision by type; calculate win rates per type."""

        classification = {dtype: {"qwen": 0, "deepseek": 0, "tie": 0, "total": 0} for dtype in self.DECISION_TYPES.keys()}

        for run in runs:
            decision_text = (run.get("decision_text") or "") + " " + (run.get("captain_notes") or "")
            decision_text = decision_text.lower()

            # Classify (first match wins)
            dtype = "operational"  # default
            for dt, keywords in self.DECISION_TYPES.items():
                if any(kw in decision_text for kw in keywords):
                    dtype = dt
                    break

            # Record winner
            preferred = run.get("captain_preferred_model", "")
            if preferred and "qwen" in preferred.lower():
                classification[dtype]["qwen"] += 1
            elif preferred and "deepseek" in preferred.lower():
                classification[dtype]["deepseek"] += 1
            else:
                classification[dtype]["tie"] += 1

            classification[dtype]["total"] += 1

        # Convert to percentages
        result = {}
        for dtype, counts in classification.items():
            total = counts["total"]
            if total > 0:
                result[dtype] = {
                    "qwen": counts["qwen"] / total,
                    "deepseek": counts["deepseek"] / total,
                    "tie": counts["tie"] / total,
                }
            else:
                result[dtype] = {"qwen": 0, "deepseek": 0, "tie": 0}

        return result

    def _generate_recommendation(
        self,
        qwen_rate: float,
        deepseek_rate: float,
        total_runs: int,
        decision_types: Dict,
    ) -> tuple[str, float]:
        """
        Generate recommendation based on win rates and patterns.

        Returns: (recommendation, confidence) tuple
        """

        # Threshold-based decision
        if deepseek_rate > 0.65 and total_runs >= 20:
            return ("promote", 0.8)

        if deepseek_rate < 0.35 and total_runs >= 20:
            return ("demote", 0.7)

        if 0.4 <= deepseek_rate <= 0.6 and total_runs >= 20:
            # Check for specialization opportunity
            if self._has_complementary_strengths(decision_types):
                return ("specialize", 0.6)
            else:
                return ("keep", 0.5)

        if total_runs >= 10 and total_runs < 20:
            return ("insufficient_data", 0.3)

        return ("insufficient_data", 0.0)

    def _has_complementary_strengths(self, decision_types: Dict) -> bool:
        """Check if models have complementary strengths (one excels in different areas)."""

        # Look for >60% win rate in any single decision type
        for dtype, rates in decision_types.items():
            if rates.get("qwen", 0) > 0.60 or rates.get("deepseek", 0) > 0.60:
                return True

        return False

    def _build_reasoning(
        self,
        total_runs: int,
        qwen_wins: int,
        deepseek_wins: int,
        ties: int,
        recommendation: str,
        decision_types: Dict,
    ) -> str:
        """Build human-readable reasoning for recommendation."""

        parts = [f"After {total_runs} evaluations:"]

        # Win rate summary
        parts.append(
            f"Qwen won {qwen_wins} ({100*qwen_wins/total_runs:.0f}%), "
            f"DeepSeek won {deepseek_wins} ({100*deepseek_wins/total_runs:.0f}%), "
            f"Ties {ties} ({100*ties/total_runs:.0f}%)"
        )

        # Decision type analysis
        if any(
            rates.get("qwen", 0) > 0.60 or rates.get("deepseek", 0) > 0.60
            for rates in decision_types.values()
        ):
            parts.append("Complementary strengths detected:")
            for dtype, rates in decision_types.items():
                if rates.get("qwen", 0) > 0.60:
                    parts.append(f"  - Qwen excels on {dtype} decisions ({100*rates['qwen']:.0f}% win rate)")
                if rates.get("deepseek", 0) > 0.60:
                    parts.append(
                        f"  - DeepSeek excels on {dtype} decisions ({100*rates['deepseek']:.0f}% win rate)"
                    )

        # Recommendation explanation
        if recommendation == "promote":
            parts.append(
                "DeepSeek demonstrates clear superiority. Recommend promotion to primary model."
            )
        elif recommendation == "demote":
            parts.append(
                "Qwen demonstrates clear superiority. DeepSeek should remain secondary."
            )
        elif recommendation == "specialize":
            parts.append(
                "Both models show complementary strengths. Recommend specialization: "
                "route decisions by type to model that excels in that area."
            )
        elif recommendation == "keep":
            parts.append("No significant difference between models. Continue current configuration.")
        else:
            parts.append(f"Insufficient data ({total_runs} runs) for confident recommendation.")

        return " ".join(parts)

    def _generate_next_steps(
        self, recommendation: str, total_runs: int, decision_types: Dict
    ) -> List[str]:
        """Generate actionable next steps based on recommendation."""

        steps = []

        if recommendation == "promote":
            steps = [
                "Run 5 more evaluations to confirm consistency",
                "Schedule model migration planning",
                "Archive Qwen evaluation after promotion",
            ]
        elif recommendation == "demote":
            steps = [
                "Archive DeepSeek candidate evaluation",
                "Continue with Qwen as primary model",
                "Revisit model selection in Q1 2027",
            ]
        elif recommendation == "specialize":
            steps = [
                "Implement decision-type classification in command layer",
                "Route technical decisions to DeepSeek",
                "Route policy decisions to Qwen",
                "Run 5 more evaluations with specialized routing to validate",
                "Monitor decision quality metrics before permanent change",
            ]
        elif recommendation == "keep":
            steps = [
                "Continue current primary model (Qwen)",
                "Run 5 more evaluations for additional confidence",
                "Re-evaluate in 2 weeks with larger dataset",
            ]
        else:  # insufficient_data
            steps = [
                f"Run {20 - total_runs} more evaluations",
                "Ensure varied question types across policy, technical, operational, strategic",
                f"Target completion: {(datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')}",
                "Re-analyze after reaching 20 runs",
            ]

        return steps


def analyze_runs_from_db(runs: List[Dict]) -> DualCommanderAnalysis:
    """Convenience function to analyze dual commander runs."""
    analyzer = DualCommanderAnalyzer()
    return analyzer.analyze_dual_commander_runs(runs)


if __name__ == "__main__":
    # Example usage
    analyzer = DualCommanderAnalyzer()

    test_runs = [
        {
            "decision_text": "Approve Kubernetes migration to Q3",
            "captain_preferred_model": "qwen",
            "captain_notes": "Qwen's risk analysis was better.",
        },
        {
            "decision_text": "Deploy microservices architecture",
            "captain_preferred_model": "deepseek",
            "captain_notes": "DeepSeek's technical depth was superior.",
        },
        {
            "decision_text": "Establish approval process for security",
            "captain_preferred_model": "qwen",
            "captain_notes": "Qwen better understood policy implications.",
        },
        {
            "decision_text": "Choose between Istio and Linkerd",
            "captain_preferred_model": "deepseek",
            "captain_notes": "DeepSeek's architectural comparison was thorough.",
        },
        {
            "decision_text": "Defer workflow automation to Q4",
            "captain_preferred_model": "qwen",
            "captain_notes": "Qwen better understood capacity constraints.",
        },
    ] * 4  # Repeat 4x to get 20 runs

    analysis = analyzer.analyze_dual_commander_runs(test_runs)

    print(f"Total Runs: {analysis.total_runs}")
    print(f"Qwen Wins: {analysis.qwen_wins} ({100*analysis.qwen_win_rate:.0f}%)")
    print(f"DeepSeek Wins: {analysis.deepseek_wins} ({100*analysis.deepseek_win_rate:.0f}%)")
    print(f"Ties: {analysis.ties} ({100*analysis.tie_rate:.0f}%)")
    print(f"\nRecommendation: {analysis.recommendation.upper()}")
    print(f"Confidence: {100*analysis.confidence:.0f}%")
    print(f"\nReasoning:\n{analysis.reasoning}")
    print(f"\nNext Steps:")
    for i, step in enumerate(analysis.next_steps, 1):
        print(f"  {i}. {step}")
